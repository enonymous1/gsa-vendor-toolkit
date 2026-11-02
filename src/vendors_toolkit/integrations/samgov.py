"""SAM.gov API client (scaffold for vendor enrichment).

Covers the three read endpoints the pipeline will use to enrich vendor
records: entity lookup, exclusion screening, and opportunity search. The
client is inert without a key: every call raises
:class:`SamGovNotConfiguredError` until ``SAM_API_KEY`` is set, so a missing
key fails loudly instead of burning the free tier or erroring obscurely.

Auth is the ``api_key`` query parameter (no header). Free tiers: 10
requests/day with a basic SAM.gov account, 1,000/day with a SAM entity role;
keys expire every 90 days and must be regenerated.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from vendors_toolkit.config import SamGovConfig

logger = logging.getLogger(__name__)


def _retry_after_seconds(response: Any) -> int:
    """Seconds to wait after a 429, from ``Retry-After`` if usable.

    Falls back to 1s when the header is absent or unparseable, and caps
    at 60s so a hostile or mistaken header cannot stall a run for hours.
    """
    try:
        value = int(response.headers.get("Retry-After", ""))
    except (AttributeError, TypeError, ValueError):
        return 1
    return max(0, min(value, 60))


class SamGovNotConfiguredError(RuntimeError):
    """Raised when a SAM.gov call is attempted without an API key."""


class SamGovClient:
    """Thin client over the SAM.gov public APIs."""

    def __init__(self, cfg: SamGovConfig, *, api_key: str | None = None) -> None:
        self._cfg = cfg
        self._api_key = api_key or os.environ.get(cfg.api_key_env_var)

    @property
    def is_configured(self) -> bool:
        """True once an API key is available (env var or explicit)."""
        return bool(self._api_key)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET one SAM.gov endpoint, with a budget-aware retry policy.

        Auth is the ``api_key`` query parameter. Only 429, 5xx, and
        connection errors are retried — a 4xx other than 429 fails
        immediately, because retrying a bad key or a forbidden call
        would burn the free tier's daily budget for nothing. On 429
        the ``Retry-After`` header is honored (capped at 60s); other
        retries sleep a fixed 1s. No sleep is taken after the final
        attempt. A non-JSON body is wrapped in the same ``RuntimeError``
        shape as a failed request, instead of leaking a bare
        ``ValueError`` from ``response.json()``.
        """
        if not self._api_key:
            raise SamGovNotConfiguredError(
                "SAM.gov API key not configured. Get a free key from a SAM.gov "
                'account (Account Details → "Public API Key") and set '
                f"{self._cfg.api_key_env_var}."
            )
        url = f"{self._cfg.base_url}{path}"
        query = {**params, "api_key": self._api_key}
        last_error = ""
        attempts = self._cfg.max_retries + 1
        for attempt in range(attempts):
            try:
                response = requests.get(url, params=query, timeout=self._cfg.timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("SAM.gov returned a non-object response.")
                return payload
            except requests.HTTPError as exc:
                last_error = str(exc)
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and status != 429 and status < 500:
                    raise RuntimeError(f"SAM.gov request failed: {last_error}") from exc
                sleep = _retry_after_seconds(exc.response)
            except requests.RequestException as exc:
                last_error = str(exc)
                sleep = 1
            except ValueError as exc:
                raise RuntimeError(f"SAM.gov returned an invalid JSON response: {exc}") from exc
            if attempt < attempts - 1:
                time.sleep(sleep)
        raise RuntimeError(f"SAM.gov request failed after retries: {last_error}")

    def get_entity_by_uei(self, uei: str) -> dict[str, Any]:
        """Look up one entity by its 12-character SAM Unique Entity ID."""
        return self._get("/entity-information/v3/entities", {"ueiSAM": uei})

    def get_entity_by_cage(self, cage: str) -> dict[str, Any]:
        """Look up one entity by its 5-character CAGE code."""
        return self._get("/entity-information/v3/entities", {"cageCode": cage})

    def search_entities(
        self,
        *,
        legal_name: str | None = None,
        state: str | None = None,
        naics: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search registered entities by name, state, and/or NAICS code."""
        params: dict[str, Any] = {"size": limit}
        if legal_name is not None:
            params["legalBusinessName"] = legal_name
        if state is not None:
            params["state"] = state
        if naics is not None:
            params["naicsCode"] = naics
        return self._get("/entity-information/v3/entities", params)

    def check_exclusions(
        self, *, uei: str | None = None, cage: str | None = None
    ) -> dict[str, Any]:
        """Check the exclusion (suspension/debarment) list by UEI or CAGE."""
        params: dict[str, Any] = {}
        if uei is not None:
            params["ueiSAM"] = uei
        if cage is not None:
            params["cageCode"] = cage
        if not params:
            raise ValueError("check_exclusions needs a uei or a cage.")
        return self._get("/entity-information/v3/exclusions", params)

    def search_opportunities(
        self,
        *,
        keywords: str | None = None,
        naics: str | None = None,
        state: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search active contract opportunities by keyword, NAICS, and/or state."""
        params: dict[str, Any] = {"limit": limit}
        if keywords is not None:
            params["title"] = keywords
        if naics is not None:
            params["ncode"] = naics
        if state is not None:
            params["state"] = state
        return self._get("/prod/opportunities/v2/search", params)
