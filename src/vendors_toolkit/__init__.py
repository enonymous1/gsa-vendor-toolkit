"""vendors_toolkit: GSA vendor price-list data pipeline.

Refactored from the organically grown ``ss-gsaVendors`` script collection into an
installable package with centralized configuration, standardized logging, and a
single CLI entry point (``vendors-toolkit``).

Pipeline stages (see ``vendors_toolkit.cli`` for the command surface):

- ``sanitize``  -- clean the raw vendor CSV (unifies ``data_sanitizer`` + ``sanitize_541611``)
- ``download``  -- fetch vendor price lists (unifies ``download_price_lists`` + ``download_541611``)
- ``organize``  -- file price lists by State/City (unifies ``organize_price_lists`` + ``organize_541611``)
- ``merge``     -- merge Excel "Price List" sheets into master CSVs (unifies ``merge_*``)
- ``filter``    -- filter merged data by SIN (generalizes ``filter_sin_54151s``)
- ``metrics``   -- per-title pricing metrics (unifies ``analyze_it_pricing`` + ``analyze_541611_pricing``)
- ``audit``     -- data audit (``data_audit``)
- ``export``    -- vendor exports, regional summaries, unique titles
                  (``export_vendors`` + ``extract_unique_titles`` + ``analyze_master_data``)
- ``national``  -- national IT merge (``merge_national_it``)
- ``report``    -- HTML dashboards + Markdown executive summaries
                  (``generate_pricing_reports`` + ``generate_541611_reports``)

Standalone (not pipeline stages):

- ``sam``       -- SAM.gov API enrichment (scaffold; needs ``SAM_API_KEY``)
- ``integrity`` -- offline SAM.gov Responsibility and Integrity Records
                  export analysis (folded in from ``mp-sam-data-bank``)
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
