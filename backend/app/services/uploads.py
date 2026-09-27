"""Parsing, column mapping and validation for merchant-supplied CSV files.

Uploaded content is untrusted. Everything here treats it that way: sizes are
capped before parsing, headers are normalised rather than trusted, types are
checked rather than coerced, and **nothing is ever silently repaired**. A file
with a problem comes back with the problem described, row numbers included, so
the merchant can fix it and upload again.

The canonical schemas are the ones the analytics layer already uses
(`backend/app/models/schemas.py`). One difference: `merchant_id` is never asked
for. A merchant should not have to paste an internal id into every row of their
own spreadsheet, so it is injected from the selected workspace.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.app.config import settings

SALES = "sales"
CUSTOMERS = "customers"
UPLOAD_TYPES = (SALES, CUSTOMERS)

# Rows shown back to the user so they can confirm the mapping looks right.
PREVIEW_ROWS = 8
# Cap on how many bad rows are reported. Beyond this the file needs rebuilding,
# not row-by-row correction.
MAX_REPORTED_ERRORS = 200


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # "date" | "text" | "int" | "float"
    required: bool
    description: str


SALES_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("date", "date", True, "Business date, e.g. 2026-09-15."),
    FieldSpec("product", "text", True, "Product name."),
    FieldSpec("category", "text", True, "Category the product belongs to."),
    FieldSpec("orders", "int", True, "Orders containing this product that day."),
    FieldSpec("units_sold", "int", True, "Units of this product sold that day."),
    FieldSpec("revenue", "float", True, "Gross revenue for this product that day."),
    FieldSpec("expenses", "float", True, "Cost of goods sold for this product that day."),
    FieldSpec("inventory", "int", True, "Closing stock in units after the day's sales."),
)

CUSTOMER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("date", "date", True, "Business date, e.g. 2026-09-15."),
    FieldSpec("customers", "int", True, "Distinct customers that day."),
    FieldSpec("new_customers", "int", True, "First-time customers that day."),
    FieldSpec("repeat_customers", "int", True, "Returning customers that day."),
)


def fields_for(upload_type: str) -> tuple[FieldSpec, ...]:
    return SALES_FIELDS if upload_type == SALES else CUSTOMER_FIELDS


# Header spellings seen in real exports, normalised to the canonical name.
# Matching is done on a squashed form (lowercase, alphanumerics only), so
# "Units Sold", "units-sold" and "UNITS_SOLD" all land on the same key.
_SYNONYMS: dict[str, str] = {
    # date
    "date": "date", "businessdate": "date", "orderdate": "date", "day": "date",
    "transactiondate": "date", "saledate": "date", "invoicedate": "date", "dt": "date",
    # product
    "product": "product", "productname": "product", "item": "product",
    "itemname": "product", "sku": "product", "productsku": "product", "title": "product",
    # category
    "category": "category", "productcategory": "category", "type": "category",
    "department": "category", "group": "category", "itemcategory": "category",
    # orders
    "orders": "orders", "ordercount": "orders", "numorders": "orders",
    "nooforders": "orders", "totalorders": "orders", "transactions": "orders",
    "billcount": "orders", "invoices": "orders",
    # units
    "unitssold": "units_sold", "units": "units_sold", "quantity": "units_sold",
    "qty": "units_sold", "quantitysold": "units_sold", "unitsold": "units_sold",
    "totalunits": "units_sold", "pieces": "units_sold",
    # revenue
    "revenue": "revenue", "sales": "revenue", "salesamount": "revenue",
    "totalrevenue": "revenue", "amount": "revenue", "grosssales": "revenue",
    "netsales": "revenue", "totalamount": "revenue", "turnover": "revenue",
    "totalsales": "revenue", "saleamount": "revenue",
    # expenses
    "expenses": "expenses", "cost": "expenses", "cogs": "expenses",
    "costofgoodssold": "expenses", "costprice": "expenses", "totalcost": "expenses",
    "purchasecost": "expenses", "expense": "expenses", "costs": "expenses",
    # inventory
    "inventory": "inventory", "stock": "inventory", "closingstock": "inventory",
    "stockonhand": "inventory", "onhand": "inventory", "balance": "inventory",
    "closinginventory": "inventory", "availablestock": "inventory",
    # customers
    "customers": "customers", "customercount": "customers", "totalcustomers": "customers",
    "footfall": "customers", "visitors": "customers", "uniquecustomers": "customers",
    "buyers": "customers", "shoppers": "customers",
    "newcustomers": "new_customers", "new": "new_customers",
    "firsttimecustomers": "new_customers", "newbuyers": "new_customers",
    "acquired": "new_customers",
    "repeatcustomers": "repeat_customers", "repeat": "repeat_customers",
    "returningcustomers": "repeat_customers", "returning": "repeat_customers",
    "existingcustomers": "repeat_customers", "repeatbuyers": "repeat_customers",
}


def _squash(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).strip().lower())


@dataclass
class RowError:
    row: int  # 1-based line number in the uploaded file, header excluded
    column: str
    value: str
    problem: str

    def as_dict(self) -> dict[str, Any]:
        return {"row": self.row, "column": self.column, "value": self.value, "problem": self.problem}


@dataclass
class UploadCheck:
    """Everything the UI needs to show a mapping step and a validation result."""

    upload_type: str
    ok: bool = False
    headers: list[str] = field(default_factory=list)
    mapping: dict[str, str | None] = field(default_factory=dict)
    unmapped_required: list[str] = field(default_factory=list)
    row_count: int = 0
    preview: list[dict[str, Any]] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    date_start: str | None = None
    date_end: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "upload_type": self.upload_type,
            "ok": self.ok,
            "headers": self.headers,
            "mapping": self.mapping,
            "unmapped_required": self.unmapped_required,
            "row_count": self.row_count,
            "preview": self.preview,
            "errors": [e.as_dict() for e in self.errors[:MAX_REPORTED_ERRORS]],
            "error_count": len(self.errors),
            "messages": self.messages,
            "warnings": self.warnings,
            "date_start": self.date_start,
            "date_end": self.date_end,
        }


class UploadError(Exception):
    """A problem that stops the file being read at all."""


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def read_csv_bytes(content: bytes, filename: str = "upload.csv") -> pd.DataFrame:
    """Parse raw bytes into a DataFrame with every cell left as text.

    Reading as text is the same decision the demo loader makes: coercing on read
    would turn a corrupted value into NaN before anything could report it.
    """
    if not content:
        raise UploadError("The file is empty.")

    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise UploadError(f"The file is larger than the {limit_mb:.0f} MB limit.")

    if not filename.lower().endswith(".csv"):
        raise UploadError("Only .csv files are supported.")

    # A NUL byte means this is not the text CSV it claims to be.
    if b"\x00" in content[:4096]:
        raise UploadError("The file does not look like a text CSV.")

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            frame = pd.read_csv(
                io.BytesIO(content),
                dtype=str,
                keep_default_na=False,
                na_values=[""],
                encoding=encoding,
                skip_blank_lines=True,
            )
            break
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError as exc:
            raise UploadError("The file has no rows.") from exc
        except pd.errors.ParserError as exc:
            raise UploadError(
                "The file could not be parsed as CSV. Check for stray quotes or "
                "rows with a different number of columns."
            ) from exc
    else:
        raise UploadError("The file's text encoding could not be read.")

    if frame.empty:
        raise UploadError("The file has a header but no data rows.")

    if len(frame) > settings.max_upload_rows:
        raise UploadError(
            f"The file has {len(frame):,} rows, above the {settings.max_upload_rows:,} row limit."
        )

    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def suggest_mapping(headers: list[str], upload_type: str) -> dict[str, str | None]:
    """Guess which uploaded column feeds each canonical field.

    Exact canonical names win, then known synonyms. A header is never used
    twice, and anything unmatched is left as None for the user to map by hand.
    """
    specs = fields_for(upload_type)
    mapping: dict[str, str | None] = {spec.name: None for spec in specs}
    taken: set[str] = set()

    # Pass 1: a header that already is the canonical name.
    for spec in specs:
        for header in headers:
            if header in taken:
                continue
            if _squash(header) == _squash(spec.name):
                mapping[spec.name] = header
                taken.add(header)
                break

    # Pass 2: known synonyms.
    for header in headers:
        if header in taken:
            continue
        canonical = _SYNONYMS.get(_squash(header))
        if canonical and canonical in mapping and mapping[canonical] is None:
            mapping[canonical] = header
            taken.add(header)

    return mapping


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
_INT_PATTERN = re.compile(r"^-?\d+$")


def _clean_number(text: str) -> str:
    """Strip presentation from a number without changing its value.

    Spreadsheet exports carry currency symbols, thousands separators and
    parenthesised negatives. Removing those is formatting, not repair — the
    magnitude and sign are preserved exactly, and anything still unparseable is
    reported rather than guessed at.
    """
    value = str(text).strip()
    if not value:
        return value
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1]
    value = re.sub(r"[₹$€£¥,\s]", "", value)
    if value.endswith("%"):
        value = value[:-1]
    return f"-{value}" if negative and value else value


def check_upload(
    frame: pd.DataFrame,
    upload_type: str,
    mapping: dict[str, str | None] | None = None,
) -> UploadCheck:
    """Validate an uploaded frame against the canonical schema.

    Returns a report rather than raising, because the UI needs to show the user
    every problem at once instead of the first one.
    """
    if upload_type not in UPLOAD_TYPES:
        raise UploadError(f"Unknown upload type '{upload_type}'.")

    specs = fields_for(upload_type)
    headers = list(frame.columns)
    resolved = dict(mapping) if mapping else suggest_mapping(headers, upload_type)

    check = UploadCheck(upload_type=upload_type, headers=headers, mapping=resolved)

    # A mapping that points at a column the file does not have is a client bug
    # or a stale mapping; either way it must not be silently ignored.
    for canonical, source in list(resolved.items()):
        if source is not None and source not in headers:
            check.messages.append(
                f"The file has no column named '{source}', which was mapped to '{canonical}'."
            )
            resolved[canonical] = None

    missing = [s.name for s in specs if s.required and not resolved.get(s.name)]
    if missing:
        check.unmapped_required = missing
        check.messages.append(
            "These required columns could not be matched: " + ", ".join(missing) + "."
        )
        return check

    check.row_count = len(frame)

    # ---- per-cell type checks ------------------------------------------
    parsed: dict[str, pd.Series] = {}
    for spec in specs:
        source = resolved[spec.name]
        column = frame[source]

        blank = column.isna() | (column.astype(str).str.strip() == "")
        for position in frame.index[blank][: MAX_REPORTED_ERRORS]:
            check.errors.append(
                RowError(int(position) + 2, source, "", f"{spec.name} is required but empty")
            )

        if spec.kind == "date":
            values = pd.to_datetime(column, errors="coerce", format="mixed", dayfirst=False)
            bad = values.isna() & ~blank
            for position in frame.index[bad][: MAX_REPORTED_ERRORS]:
                check.errors.append(
                    RowError(
                        int(position) + 2,
                        source,
                        str(column.iloc[position])[:40],
                        "could not be read as a date",
                    )
                )
            parsed[spec.name] = values

        elif spec.kind in ("int", "float"):
            cleaned = column.astype(str).map(_clean_number)
            values = pd.to_numeric(cleaned, errors="coerce")
            bad = values.isna() & ~blank
            for position in frame.index[bad][: MAX_REPORTED_ERRORS]:
                check.errors.append(
                    RowError(
                        int(position) + 2,
                        source,
                        str(column.iloc[position])[:40],
                        "is not a number",
                    )
                )

            negative = values.notna() & (values < 0)
            for position in frame.index[negative][: MAX_REPORTED_ERRORS]:
                check.errors.append(
                    RowError(
                        int(position) + 2,
                        source,
                        str(column.iloc[position])[:40],
                        "cannot be negative",
                    )
                )

            if spec.kind == "int":
                fractional = values.notna() & (values % 1 != 0)
                for position in frame.index[fractional][: MAX_REPORTED_ERRORS]:
                    check.errors.append(
                        RowError(
                            int(position) + 2,
                            source,
                            str(column.iloc[position])[:40],
                            "must be a whole number",
                        )
                    )
            parsed[spec.name] = values

        else:
            parsed[spec.name] = column.astype(str).str.strip()

    # ---- cross-column and cross-row checks ------------------------------
    dates = parsed.get("date")
    if dates is not None and dates.notna().any():
        check.date_start = dates.min().date().isoformat()
        check.date_end = dates.max().date().isoformat()

    if upload_type == SALES:
        key = pd.DataFrame({"date": dates, "product": parsed["product"]})
        duplicated = key.duplicated(keep="first") & dates.notna()
        for position in frame.index[duplicated][: MAX_REPORTED_ERRORS]:
            check.errors.append(
                RowError(
                    int(position) + 2,
                    "date, product",
                    f"{key['date'].iloc[position]}, {key['product'].iloc[position]}"[:60],
                    "duplicates an earlier row for the same product and day",
                )
            )

        orders, units = parsed["orders"], parsed["units_sold"]
        invalid = orders.notna() & units.notna() & (orders > units)
        for position in frame.index[invalid][: MAX_REPORTED_ERRORS]:
            check.errors.append(
                RowError(
                    int(position) + 2,
                    "orders",
                    str(orders.iloc[position]),
                    "orders cannot exceed units_sold",
                )
            )

        no_orders = orders.notna() & units.notna() & (units > 0) & (orders == 0)
        for position in frame.index[no_orders][: MAX_REPORTED_ERRORS]:
            check.errors.append(
                RowError(
                    int(position) + 2,
                    "orders",
                    "0",
                    "units were sold, so orders cannot be zero",
                )
            )

        thin = parsed["revenue"].notna() & parsed["expenses"].notna() & (
            parsed["expenses"] > parsed["revenue"]
        )
        if bool(thin.any()):
            check.warnings.append(
                f"{int(thin.sum())} row(s) have expenses above revenue, which means a "
                "loss on those lines. Check this is intended — it is kept as supplied."
            )
    else:
        duplicated = dates.duplicated(keep="first") & dates.notna()
        for position in frame.index[duplicated][: MAX_REPORTED_ERRORS]:
            check.errors.append(
                RowError(
                    int(position) + 2,
                    "date",
                    str(key_value(dates, position)),
                    "duplicates an earlier row for the same day",
                )
            )

        total, new, repeat = parsed["customers"], parsed["new_customers"], parsed["repeat_customers"]
        mismatch = total.notna() & new.notna() & repeat.notna() & ((new + repeat) != total)
        for position in frame.index[mismatch][: MAX_REPORTED_ERRORS]:
            check.errors.append(
                RowError(
                    int(position) + 2,
                    "customers",
                    str(total.iloc[position]),
                    "new_customers + repeat_customers must equal customers",
                )
            )

    # ---- preview --------------------------------------------------------
    preview_frame = pd.DataFrame(
        {spec.name: parsed[spec.name] for spec in specs}
    ).head(PREVIEW_ROWS)
    check.preview = [
        {
            key: (value.date().isoformat() if isinstance(value, pd.Timestamp) else _plain(value))
            for key, value in row.items()
        }
        for row in preview_frame.to_dict(orient="records")
    ]

    check.ok = not check.errors
    if check.ok:
        span = ""
        if check.date_start and check.date_end:
            span = f" covering {check.date_start} to {check.date_end}"
        check.messages.append(f"{check.row_count:,} row(s) read{span}. No problems found.")

    return check


def key_value(series: pd.Series, position: int) -> Any:
    value = series.iloc[position]
    return value.date().isoformat() if isinstance(value, pd.Timestamp) else value


def _plain(value: Any) -> Any:
    """Convert pandas/NumPy scalars to something json can serialise."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return str(value)
    return value


# --------------------------------------------------------------------------
# Canonical conversion
# --------------------------------------------------------------------------
def to_canonical(
    frame: pd.DataFrame,
    upload_type: str,
    mapping: dict[str, str | None],
    merchant_id: str,
) -> pd.DataFrame:
    """Rename, type and order an uploaded frame into the canonical schema.

    `merchant_id` is injected here rather than read from the file, so a merchant
    never has to know or type an internal identifier.
    """
    specs = fields_for(upload_type)
    out = pd.DataFrame()

    for spec in specs:
        source = mapping.get(spec.name)
        if not source:
            raise UploadError(f"Required column '{spec.name}' is not mapped.")
        column = frame[source]

        if spec.kind == "date":
            out[spec.name] = pd.to_datetime(column, errors="coerce", format="mixed").dt.strftime(
                "%Y-%m-%d"
            )
        elif spec.kind == "int":
            out[spec.name] = pd.to_numeric(column.astype(str).map(_clean_number)).astype("int64")
        elif spec.kind == "float":
            out[spec.name] = pd.to_numeric(column.astype(str).map(_clean_number)).astype("float64")
        else:
            out[spec.name] = column.astype(str).str.strip()

    out.insert(1, "merchant_id", merchant_id)

    order = (
        ["date", "merchant_id", "product", "category", "orders", "units_sold", "revenue",
         "expenses", "inventory"]
        if upload_type == SALES
        else ["date", "merchant_id", "customers", "new_customers", "repeat_customers"]
    )
    return out[order]


def errors_to_csv(errors: list[RowError]) -> str:
    """Render reported problems as a CSV the merchant can open alongside the file."""
    lines = ["row,column,value,problem"]
    for error in errors:
        cells = [str(error.row), error.column, error.value, error.problem]
        lines.append(",".join('"' + c.replace('"', '""') + '"' for c in cells))
    return "\n".join(lines)
