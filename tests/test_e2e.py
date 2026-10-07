"""End-to-end pipeline smoke test: every CLI stage on synthetic data.

The downloader is simulated by placing vendor workbooks directly in the
download directories (no network); every other stage runs for real, for both
variants, through the actual CLI entry point.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from vendors_toolkit import cli

PRICE_COL = "GSA Price with IFF"


def _workbook(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["Title", "Description", PRICE_COL, "SIN"]).to_excel(
        path, sheet_name="Price List", index=False
    )


def _vendor_rows(vendors: list[tuple]) -> list[dict]:
    return [
        {
            "Vendor": v,
            "Contact #": c,
            "Price List": pl,
            "Category": cat,
            "State": st,
            "City": city,
            "Has_Price_List_Flag": flag,
        }
        for v, c, pl, cat, st, city, flag in vendors
    ]


def test_full_pipeline_end_to_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VENDORS_ROOT", str(tmp_path))
    root = tmp_path
    (root / "ext_res").mkdir()

    pd.DataFrame(
        _vendor_rows(
            [
                ("Acme", "101", "http://x", "54151S", "VA", "Arlington", "Yes"),
                ("Beta", "202", "http://y", "54151S", "VA", "Richmond", "Yes"),
                ("Gamma", "303", "", "54151S", "DC", "Washington", ""),
            ]
        )
    ).to_csv(root / "ext_res" / "2026_02_12_04_10_24.csv", index=False)
    pd.DataFrame(
        _vendor_rows(
            [
                ("Delta", "404", "http://z", "541611", "VA", "Fairfax", "Yes"),
                ("Epsilon", "505", "", "541611", "MD", "Bethesda", ""),
            ]
        )
    ).to_csv(root / "ext_res" / "2026_03_02_08_18_31.csv", index=False)

    assert cli.main(["sanitize"]) == 0

    # simulated downloads (what the downloader would have fetched)
    _workbook(
        root / "output" / "downloads" / "price_lists" / "Acme_101.xlsx",
        [
            ("Analyst", "Does analysis", "$100", "54151S"),
            ("Analyst", "More analysis", "200", "54151S"),
            ("Clerk", "", "75", "54151S"),
        ],
    )
    _workbook(
        root / "output" / "downloads" / "price_lists" / "Beta_202.xlsx",
        [
            ("Manager", "Manages", "$1,000", "54151S"),
        ],
    )
    _workbook(
        root / "output" / "downloads" / "541611_price_lists" / "Delta_404.xlsx",
        [
            ("Consultant", "Advises", "$500", "541611"),
            ("Consultant", "Advises well", "600", "541611"),
        ],
    )
    # manifest (normally written by the downloader) for the national stage
    (root / "output" / "summaries").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"Vendor": "Acme", "Contact #": "101", "Download_Status": "Success"},
            {"Vendor": "Beta", "Contact #": "202", "Download_Status": "Success"},
        ]
    ).to_csv(root / "output" / "summaries" / "download_manifest.csv", index=False)

    assert cli.main(["organize"]) == 0
    assert cli.main(["merge", "--states", "VA"]) == 0
    assert cli.main(["filter", "--states", "VA"]) == 0
    assert cli.main(["metrics", "--states", "VA"]) == 0
    assert cli.main(["audit", "--states", "VA"]) == 0
    assert cli.main(["export"]) == 0
    assert cli.main(["--variant", "54151S", "national"]) == 0
    assert cli.main(["report", "--states", "VA"]) == 0

    for rel in [
        "output/merged/VA_Master_Price_List.csv",
        "output/541611_analysis/VA_541611_Master_List.csv",
        "output/merged_filtered/VA_SIN_54151S_Only.csv",
        "output/it_title_analysis/VA_IT_Role_Metrics.csv",
        "output/541611_metrics/VA_541611_Metrics.csv",
        "output/merged_national/National_IT_Master_Price_List.csv",
        "output/reports/VA_IT_Pricing_Full_Report.html",
        "output/reports/VA_IT_Pricing_Executive_Summary.md",
        "output/541611_reports/VA_541611_Pricing_Full_Report.html",
        "output/unique_titles/VA_Unique_IT_Titles.json",
    ]:
        assert (root / rel).exists(), rel

    metrics = pd.read_csv(root / "output/it_title_analysis/VA_IT_Role_Metrics.csv")
    analyst = metrics[metrics["Title_Key"] == "ANALYST"].iloc[0]
    assert analyst["Count"] == 2 and analyst["Mean_Price"] == 150.0
    national = pd.read_csv(root / "output/merged_national/National_IT_Master_Price_List.csv")
    assert len(national) == 4
    html = (root / "output/reports/VA_IT_Pricing_Full_Report.html").read_text()
    assert "VA IT Pricing Benchmark" in html
