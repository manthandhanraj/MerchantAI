"""Parsing, column mapping and validation of merchant-supplied CSV files.

The behaviour these tests protect: a file with a problem is *reported*, never
repaired. Every case below checks both that the problem is caught and that no
value was quietly changed to make it go away.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.app.config import settings
from backend.app.services import uploads as up

SALES_CSV = """date,product,category,orders,units_sold,revenue,expenses,inventory
2026-01-01,Widget A,Tools,5,6,600,300,44
2026-01-01,Widget B,Parts,3,3,150,75,27
2026-01-02,Widget A,Tools,4,5,500,250,39
2026-01-02,Widget B,Parts,2,2,100,50,25
"""

CUSTOMERS_CSV = """date,customers,new_customers,repeat_customers
2026-01-01,6,6,0
2026-01-02,5,2,3
"""


def check(csv: str, upload_type: str, mapping=None) -> up.UploadCheck:
    frame = up.read_csv_bytes(csv.encode(), "file.csv")
    return up.check_upload(frame, upload_type, mapping)


# ---------------------------------------------------------------- reading
def test_valid_sales_file_passes():
    result = check(SALES_CSV, up.SALES)
    assert result.ok
    assert result.row_count == 4
    assert result.date_start == "2026-01-01"
    assert result.date_end == "2026-01-02"
    assert not result.errors


def test_valid_customer_file_passes():
    result = check(CUSTOMERS_CSV, up.CUSTOMERS)
    assert result.ok
    assert result.row_count == 2


def test_empty_file_is_rejected():
    with pytest.raises(up.UploadError, match="empty"):
        up.read_csv_bytes(b"", "file.csv")


def test_header_only_file_is_rejected():
    with pytest.raises(up.UploadError, match="no data rows"):
        up.read_csv_bytes(b"date,product\n", "file.csv")


def test_non_csv_extension_is_rejected():
    with pytest.raises(up.UploadError, match="Only .csv"):
        up.read_csv_bytes(SALES_CSV.encode(), "books.xlsx")


def test_binary_content_is_rejected():
    with pytest.raises(up.UploadError, match="text CSV"):
        up.read_csv_bytes(b"PK\x03\x04\x00\x00" + b"\x00" * 100, "file.csv")


def test_oversized_file_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 32)
    with pytest.raises(up.UploadError, match="larger than"):
        up.read_csv_bytes(SALES_CSV.encode(), "file.csv")


def test_too_many_rows_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_rows", 2)
    with pytest.raises(up.UploadError, match="row limit"):
        up.read_csv_bytes(SALES_CSV.encode(), "file.csv")


def test_utf8_bom_is_handled():
    result = check("﻿" + SALES_CSV, up.SALES)
    assert result.ok


# ---------------------------------------------------------------- mapping
def test_exact_headers_map_to_themselves():
    mapping = up.suggest_mapping(
        ["date", "product", "category", "orders", "units_sold", "revenue", "expenses", "inventory"],
        up.SALES,
    )
    assert mapping["units_sold"] == "units_sold"
    assert all(value is not None for value in mapping.values())


def test_common_export_spellings_are_recognised():
    mapping = up.suggest_mapping(
        ["Order Date", "Item Name", "Department", "Bill Count", "Qty", "Total Sales", "COGS", "Stock"],
        up.SALES,
    )
    assert mapping["date"] == "Order Date"
    assert mapping["product"] == "Item Name"
    assert mapping["category"] == "Department"
    assert mapping["orders"] == "Bill Count"
    assert mapping["units_sold"] == "Qty"
    assert mapping["revenue"] == "Total Sales"
    assert mapping["expenses"] == "COGS"
    assert mapping["inventory"] == "Stock"


def test_a_header_is_never_used_for_two_fields():
    mapping = up.suggest_mapping(["date", "sales", "amount"], up.SALES)
    used = [value for value in mapping.values() if value]
    assert len(used) == len(set(used))


def test_unmatched_required_columns_are_reported():
    result = check("date,product\n2026-01-01,Widget A\n", up.SALES)
    assert not result.ok
    assert "category" in result.unmapped_required
    assert "revenue" in result.unmapped_required


def test_manual_mapping_overrides_the_guess():
    csv = """when,thing,kind,n_orders,n_units,money_in,money_out,left
2026-01-01,Widget A,Tools,5,6,600,300,44
"""
    mapping = {
        "date": "when",
        "product": "thing",
        "category": "kind",
        "orders": "n_orders",
        "units_sold": "n_units",
        "revenue": "money_in",
        "expenses": "money_out",
        "inventory": "left",
    }
    result = check(csv, up.SALES, mapping)
    assert result.ok, result.messages
    assert result.row_count == 1


def test_mapping_to_a_column_that_does_not_exist_is_reported():
    result = check(SALES_CSV, up.SALES, {**up.suggest_mapping(
        ["date", "product", "category", "orders", "units_sold", "revenue", "expenses", "inventory"],
        up.SALES), "revenue": "not_a_column"})
    assert not result.ok
    assert any("not_a_column" in message for message in result.messages)


# ---------------------------------------------------------------- values
def test_unreadable_date_is_reported_with_its_row():
    csv = SALES_CSV.replace("2026-01-02,Widget A", "not-a-date,Widget A")
    result = check(csv, up.SALES)
    assert not result.ok
    problem = next(e for e in result.errors if "date" in e.problem)
    assert problem.row == 4  # header is line 1
    assert problem.value == "not-a-date"


def test_non_numeric_value_is_reported():
    csv = SALES_CSV.replace(",600,300,44", ",six hundred,300,44")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("not a number" in e.problem for e in result.errors)


def test_negative_value_is_reported():
    csv = SALES_CSV.replace(",600,300,44", ",-600,300,44")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("negative" in e.problem for e in result.errors)


def test_fractional_count_is_reported():
    csv = SALES_CSV.replace("2026-01-01,Widget A,Tools,5,6", "2026-01-01,Widget A,Tools,5.5,6")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("whole number" in e.problem for e in result.errors)


def test_blank_required_cell_is_reported():
    csv = SALES_CSV.replace("2026-01-01,Widget B,Parts", "2026-01-01,,Parts")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("required but empty" in e.problem for e in result.errors)


def test_currency_formatting_is_read_not_rejected():
    """Symbols and separators are presentation. The value must survive exactly."""
    csv = SALES_CSV.replace(",600,300,44", ',"₹1,600.50","₹300",44')
    result = check(csv, up.SALES)
    assert result.ok, result.errors
    frame = up.read_csv_bytes(csv.encode(), "f.csv")
    canonical = up.to_canonical(frame, up.SALES, result.mapping, "M001")
    assert canonical["revenue"].iloc[0] == pytest.approx(1600.50)


def test_parenthesised_negative_is_read_as_negative_and_then_rejected():
    csv = SALES_CSV.replace(",600,300,44", ",600,(300),44")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("negative" in e.problem for e in result.errors)


# ---------------------------------------------------------- cross-row rules
def test_duplicate_product_day_is_reported():
    csv = SALES_CSV + "2026-01-01,Widget A,Tools,1,1,10,5,43\n"
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("duplicates an earlier row" in e.problem for e in result.errors)


def test_duplicate_customer_day_is_reported():
    csv = CUSTOMERS_CSV + "2026-01-01,9,9,0\n"
    result = check(csv, up.CUSTOMERS)
    assert not result.ok
    assert any("duplicates an earlier row" in e.problem for e in result.errors)


def test_orders_above_units_is_reported():
    csv = SALES_CSV.replace("2026-01-01,Widget A,Tools,5,6", "2026-01-01,Widget A,Tools,9,6")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("cannot exceed units_sold" in e.problem for e in result.errors)


def test_units_without_orders_is_reported():
    csv = SALES_CSV.replace("2026-01-01,Widget B,Parts,3,3", "2026-01-01,Widget B,Parts,0,3")
    result = check(csv, up.SALES)
    assert not result.ok
    assert any("orders cannot be zero" in e.problem for e in result.errors)


def test_customer_split_that_does_not_add_up_is_reported():
    csv = CUSTOMERS_CSV.replace("2026-01-02,5,2,3", "2026-01-02,5,2,9")
    result = check(csv, up.CUSTOMERS)
    assert not result.ok
    assert any("must equal customers" in e.problem for e in result.errors)


def test_loss_making_rows_warn_but_do_not_block():
    """Selling below cost is unusual, not invalid. It is flagged, not rejected."""
    csv = SALES_CSV.replace(",600,300,44", ",600,900,44")
    result = check(csv, up.SALES)
    assert result.ok
    assert any("expenses above revenue" in warning for warning in result.warnings)


# ---------------------------------------------------------------- canonical
def test_canonical_conversion_injects_the_merchant_id():
    """A merchant never types an internal id into their own spreadsheet."""
    frame = up.read_csv_bytes(SALES_CSV.encode(), "f.csv")
    result = up.check_upload(frame, up.SALES)
    canonical = up.to_canonical(frame, up.SALES, result.mapping, "merchant-uuid")

    assert list(canonical.columns)[:3] == ["date", "merchant_id", "product"]
    assert set(canonical["merchant_id"]) == {"merchant-uuid"}
    assert canonical["date"].iloc[0] == "2026-01-01"


def test_canonical_customers_shape():
    frame = up.read_csv_bytes(CUSTOMERS_CSV.encode(), "f.csv")
    result = up.check_upload(frame, up.CUSTOMERS)
    canonical = up.to_canonical(frame, up.CUSTOMERS, result.mapping, "m1")
    assert list(canonical.columns) == [
        "date", "merchant_id", "customers", "new_customers", "repeat_customers",
    ]


def test_error_csv_is_escaped():
    errors = [up.RowError(2, "revenue", 'say "hi"', "is not a number")]
    csv = up.errors_to_csv(errors)
    assert 'say ""hi""' in csv
    assert csv.splitlines()[0] == "row,column,value,problem"


def test_unknown_upload_type_is_rejected():
    with pytest.raises(up.UploadError):
        up.check_upload(pd.DataFrame({"date": ["2026-01-01"]}), "inventory-levels")
