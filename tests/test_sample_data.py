"""Sample-data fixtures ship with the repo and power the README quick start.

Guards against bit-rot: if a fixture is renamed or a column changes, the
quick-start commands in the README break for every new reader.
"""

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1] / "sample-data"


def test_sample_data_present() -> None:
    assert (ROOT / "ext_res" / "2026_02_12_04_10_24.csv").is_file()
    assert (ROOT / "ext_res" / "2026_03_02_08_18_31.csv").is_file()
    assert (ROOT / "output" / "downloads" / "price_lists" / "Acme_101.xlsx").is_file()
    assert (ROOT / "output" / "downloads" / "price_lists" / "Beta_202.xlsx").is_file()
    assert (ROOT / "output" / "downloads" / "541611_price_lists" / "Delta_404.xlsx").is_file()


def test_sample_data_columns_match_pipeline_contract() -> None:
    frame = pd.read_csv(ROOT / "ext_res" / "2026_02_12_04_10_24.csv")
    assert list(frame.columns) == [
        "Vendor",
        "Contact #",
        "Price List",
        "Category",
        "State",
        "City",
        "Has_Price_List_Flag",
    ]
    # VA vendors with price lists, as the README worked example assumes.
    va = frame[(frame["State"] == "VA") & (frame["Price List"].notna())]
    assert sorted(va["Vendor"]) == ["Acme", "Beta"]


def test_sample_workbooks_have_price_list_sheet() -> None:
    book = pd.read_excel(
        ROOT / "output" / "downloads" / "price_lists" / "Acme_101.xlsx",
        sheet_name="Price List",
    )
    assert "GSA Price with IFF" in book.columns
    assert len(book) == 3


@pytest.mark.parametrize(
    "csv_name",
    ["2026_02_12_04_10_24.csv", "2026_03_02_08_18_31.csv"],
)
def test_sample_csvs_parse(csv_name: str) -> None:
    frame = pd.read_csv(ROOT / "ext_res" / csv_name)
    assert len(frame) > 0
