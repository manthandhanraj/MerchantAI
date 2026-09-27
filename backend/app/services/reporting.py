"""Business analysis report as a PDF.

Written directly as PDF bytes with no third-party renderer. That is a deliberate
trade: a reporting library would add tens of megabytes to a serverless bundle
that is already carrying pandas and NumPy, to lay out a document that is entirely
headings, paragraphs and simple tables.

Every figure comes from a stored `analysis_runs` row — the same verified output
the dashboard renders. Nothing is recomputed here, so the report and the screen
cannot disagree.

Deliberately excluded from the output: access tokens, API keys, storage paths,
user ids and merchant ids. A report is a business document, not a debug dump.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Page geometry, in PDF points (72 per inch). A4.
PAGE_W, PAGE_H = 595.28, 841.89
MARGIN_X = 56.0
TOP_Y = PAGE_H - 64.0
BOTTOM_Y = 70.0

# The application's palette, darkened where needed to stay readable on paper.
FOREST = (0.078, 0.204, 0.165)
SAGE = (0.310, 0.478, 0.200)
GOLD = (0.604, 0.420, 0.082)
INK = (0.122, 0.141, 0.129)
MUTED = (0.353, 0.420, 0.376)
RULE = (0.788, 0.847, 0.753)
ALERT = (0.690, 0.290, 0.184)


def _esc(text: str) -> str:
    """Escape a string for a PDF literal, and drop anything non-Latin-1.

    The base-14 fonts used here are single-byte. Rupee and en-dash are mapped to
    ASCII equivalents rather than silently vanishing.
    """
    replacements = {
        "₹": "Rs.", "—": "-", "–": "-", "’": "'", "‘": "'",
        "“": '"', "”": '"', "·": "-", "…": "...", "→": "->",
        "↑": "+", "↓": "-", "≥": ">=", "≤": "<=", "×": "x",
        "σ": "sigma", "✅": "", "⚠": "!",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


# Widths for Helvetica at size 1, enough for wrapping to be accurate to a
# character or two. Anything unlisted falls back to the average.
_W_DEFAULT = 0.52
_W = {
    " ": 0.278, ".": 0.278, ",": 0.278, ":": 0.278, ";": 0.278, "!": 0.278, "|": 0.26,
    "i": 0.222, "j": 0.222, "l": 0.222, "'": 0.191, "(": 0.333, ")": 0.333, "-": 0.333,
    "f": 0.278, "t": 0.278, "r": 0.333, "I": 0.278, "/": 0.278,
    "m": 0.833, "w": 0.722, "M": 0.833, "W": 0.944,
    "0": 0.556, "1": 0.556, "2": 0.556, "3": 0.556, "4": 0.556,
    "5": 0.556, "6": 0.556, "7": 0.556, "8": 0.556, "9": 0.556,
}


def _width(text: str, size: float, bold: bool = False) -> float:
    total = sum(_W.get(c, _W_DEFAULT) for c in text)
    return total * size * (1.04 if bold else 1.0)


def _wrap(text: str, size: float, max_width: float, bold: bool = False) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _width(candidate, size, bold) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


@dataclass
class _Page:
    ops: list[str] = field(default_factory=list)


class _Doc:
    """A tiny PDF writer: pages of text, rules and filled rectangles."""

    def __init__(self) -> None:
        self.pages: list[_Page] = []
        self.page = _Page()
        self.pages.append(self.page)
        self.y = TOP_Y

    # ---------------------------------------------------------------- pages
    def new_page(self) -> None:
        self.page = _Page()
        self.pages.append(self.page)
        self.y = TOP_Y

    def space(self, amount: float) -> None:
        self.y -= amount

    def need(self, amount: float) -> None:
        if self.y - amount < BOTTOM_Y:
            self.new_page()

    # ---------------------------------------------------------------- draw
    def rect(self, x: float, y: float, w: float, h: float, colour: tuple) -> None:
        r, g, b = colour
        self.page.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1: float, y: float, x2: float, colour: tuple = RULE, width: float = 0.7) -> None:
        r, g, b = colour
        self.page.ops.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {width} w {x1:.2f} {y:.2f} m {x2:.2f} {y:.2f} l S"
        )

    def text(
        self,
        value: str,
        x: float,
        y: float,
        size: float = 9.5,
        colour: tuple = INK,
        bold: bool = False,
    ) -> None:
        r, g, b = colour
        font = "F2" if bold else "F1"
        self.page.ops.append(
            f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"{x:.2f} {y:.2f} Td ({_esc(value)}) Tj ET"
        )

    # ---------------------------------------------------------------- blocks
    def heading(self, value: str, size: float = 15.0) -> None:
        self.need(size + 22)
        self.space(size + 8)
        self.text(value, MARGIN_X, self.y, size, FOREST, bold=True)
        self.space(6)
        self.line(MARGIN_X, self.y, PAGE_W - MARGIN_X, SAGE, 1.0)
        self.space(12)

    def subheading(self, value: str) -> None:
        self.need(28)
        self.space(14)
        self.text(value, MARGIN_X, self.y, 11.0, SAGE, bold=True)
        self.space(13)

    def paragraph(self, value: str, size: float = 9.5, colour: tuple = INK) -> None:
        width = PAGE_W - 2 * MARGIN_X
        for line in _wrap(value, size, width):
            self.need(size + 4)
            self.text(line, MARGIN_X, self.y, size, colour)
            self.space(size + 3.5)
        self.space(4)

    def bullet(self, value: str, colour: tuple = INK) -> None:
        size = 9.5
        width = PAGE_W - 2 * MARGIN_X - 14
        for index, line in enumerate(_wrap(value, size, width)):
            self.need(size + 4)
            if index == 0:
                self.text("-", MARGIN_X + 2, self.y, size, SAGE, bold=True)
            self.text(line, MARGIN_X + 14, self.y, size, colour)
            self.space(size + 3.5)

    def key_values(self, rows: list[tuple[str, str]]) -> None:
        """Two-column facts, banded so long lists stay readable."""
        label_w = 190.0
        value_w = PAGE_W - 2 * MARGIN_X - label_w - 12
        for index, (label, value) in enumerate(rows):
            lines = _wrap(str(value), 9.5, value_w)
            height = max(len(lines) * 13.0, 16.0)
            self.need(height + 4)
            if index % 2 == 1:
                self.rect(
                    MARGIN_X - 4, self.y - height + 11, PAGE_W - 2 * MARGIN_X + 8, height,
                    (0.965, 0.976, 0.957),
                )
            self.text(str(label), MARGIN_X, self.y, 9.5, MUTED)
            for offset, line in enumerate(lines):
                self.text(line, MARGIN_X + label_w, self.y - offset * 13.0, 9.5, INK, bold=True)
            self.space(height)
        self.space(6)

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        total = sum(widths)
        available = PAGE_W - 2 * MARGIN_X
        cols = [w / total * available for w in widths]

        def header_row() -> None:
            self.need(24)
            self.rect(MARGIN_X, self.y - 5, available, 18, FOREST)
            x = MARGIN_X + 5
            for index, head in enumerate(headers):
                self.text(head, x, self.y, 8.8, (1, 1, 1), bold=True)
                x += cols[index]
            self.space(22)

        header_row()
        for row_index, row in enumerate(rows):
            wrapped = [
                _wrap(str(cell), 8.8, cols[i] - 10) for i, cell in enumerate(row)
            ]
            height = max(len(w) for w in wrapped) * 11.5 + 5
            if self.y - height < BOTTOM_Y:
                self.new_page()
                header_row()
            if row_index % 2 == 1:
                self.rect(MARGIN_X, self.y - height + 12, available, height, (0.965, 0.976, 0.957))
            x = MARGIN_X + 5
            for index, cell_lines in enumerate(wrapped):
                for offset, line in enumerate(cell_lines):
                    self.text(line, x, self.y - offset * 11.5, 8.8, INK)
                x += cols[index]
            self.space(height)
        self.space(8)

    # ---------------------------------------------------------------- output
    def build(self, title: str) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_regular = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )
        font_bold = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
        )

        pages_id = len(objects) + 1 + 2 * len(self.pages) + 1
        page_ids: list[int] = []

        for index, page in enumerate(self.pages):
            footer = (
                f"BT /F1 8 Tf 0.353 0.420 0.376 rg {MARGIN_X:.2f} 44 Td "
                f"(Page {index + 1} of {len(self.pages)}"
                f"   -   Generated by MerchantAI) Tj ET"
            )
            stream = "\n".join([*page.ops, footer]).encode("latin-1", "replace")
            compressed = zlib.compress(stream)
            content_id = add(
                b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(compressed)
                + compressed
                + b"\nendstream"
            )
            page_id = add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_id, PAGE_W, PAGE_H, font_regular, font_bold, content_id)
            )
            page_ids.append(page_id)

        kids = " ".join(f"{pid} 0 R" for pid in page_ids).encode()
        add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids)))
        catalog_id = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
        info_id = add(
            b"<< /Title (%s) /Producer (MerchantAI) /Creator (MerchantAI) >>"
            % _esc(title).encode("latin-1", "replace")
        )

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

        xref_at = len(out)
        out += b"xref\n0 %d\n" % (len(objects) + 1)
        out += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            out += b"%010d 00000 n \n" % offset
        out += (
            b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog_id, info_id, xref_at)
        )
        return bytes(out)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def _money(value: Any, currency: str = "INR") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number != number:
        return "-"
    prefix = "Rs." if currency == "INR" else f"{currency} "
    return f"{prefix}{number:,.2f}"


def _count(value: Any) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "-"


def _pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number != number:
        return "-"
    return f"{number * 100:.1f}%"


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------
def build_report_pdf(merchant: dict, analysis: dict) -> bytes:
    """Render one stored analysis as a business report.

    `merchant` and `analysis` are database rows. Only business fields are read;
    ids, owner ids and storage paths are deliberately never printed.
    """
    currency = merchant.get("currency") or "INR"
    name = merchant.get("name") or "Your business"
    summary = analysis.get("summary") or {}
    insights = analysis.get("insights") or {}
    plan = analysis.get("action_plan") or {}
    forecast = analysis.get("forecast") or {}
    products = analysis.get("products") or []
    categories = analysis.get("categories") or []
    inventory = analysis.get("inventory") or []

    period_start = analysis.get("date_start") or summary.get("period_start") or "-"
    period_end = analysis.get("date_end") or summary.get("period_end") or "-"
    generated = datetime.now(timezone.utc).strftime("%d %B %Y")

    doc = _Doc()

    # ---- cover band -----------------------------------------------------
    doc.rect(0, PAGE_H - 200, PAGE_W, 200, FOREST)
    doc.text("MERCHANTAI", MARGIN_X, PAGE_H - 74, 10.5, (0.898, 0.741, 0.459), bold=True)
    doc.text("Business Analysis Report", MARGIN_X, PAGE_H - 116, 24.0, (1, 1, 1), bold=True)
    doc.text(name[:60], MARGIN_X, PAGE_H - 146, 14.0, (0.722, 0.894, 0.616))
    doc.text(
        f"{period_start} to {period_end}", MARGIN_X, PAGE_H - 172, 10.5, (0.85, 0.90, 0.86)
    )
    doc.y = PAGE_H - 232

    doc.key_values(
        [
            ("Business", name),
            ("Business type", merchant.get("business_type") or "Not specified"),
            ("Analysis period", f"{period_start} to {period_end}"),
            ("Days covered", _count(summary.get("days"))),
            ("Currency", currency),
            ("Report generated", generated),
            ("Data source", "Uploaded by the business owner"),
        ]
    )

    # ---- executive summary ----------------------------------------------
    doc.heading("Executive summary")
    doc.paragraph(_executive_summary(name, summary, insights, plan, forecast, currency))

    # ---- headline figures -----------------------------------------------
    doc.heading("Business performance")
    doc.key_values(
        [
            ("Revenue", _money(summary.get("total_revenue"), currency)),
            ("Gross profit", _money(summary.get("total_profit"), currency)),
            ("Profit margin", _pct(summary.get("profit_margin"))),
            ("Orders", _count(summary.get("total_orders"))),
            ("Units sold", _count(summary.get("total_units_sold"))),
            ("Average order value", _money(summary.get("average_order_value"), currency)),
        ]
    )
    doc.paragraph(
        "Gross profit is revenue minus the cost of goods sold. Overheads such as rent, "
        "salaries and utilities are not included, so this is not net profit.",
        8.5,
        MUTED,
    )

    doc.subheading("Customers")
    doc.key_values(
        [
            ("Customer visits", _count(summary.get("total_customers"))),
            ("New", _count(summary.get("new_customers"))),
            ("Returning", _count(summary.get("repeat_customers"))),
            ("Returning share", _pct(summary.get("repeat_customer_rate"))),
            ("Revenue per visit", _money(summary.get("revenue_per_customer"), currency)),
        ]
    )
    doc.paragraph(
        "Customer counts are distinct shoppers per day. Summed across several days they "
        "describe visits rather than unique people.",
        8.5,
        MUTED,
    )

    # ---- products and categories ----------------------------------------
    if products:
        doc.heading("Product performance")
        rows = [
            [
                str(p.get("product", ""))[:34],
                _money(p.get("revenue"), currency),
                _count(p.get("units_sold")),
                _pct(p.get("revenue_share")),
                _pct(p.get("profit_margin")),
            ]
            for p in products[:12]
        ]
        doc.table(
            ["Product", "Revenue", "Units", "Share", "Margin"], rows, [2.5, 1.5, 1.0, 1.0, 1.0]
        )

    if categories:
        doc.subheading("Categories")
        rows = [
            [
                str(c.get("category", ""))[:34],
                _money(c.get("revenue"), currency),
                _pct(c.get("revenue_share")),
                _pct(c.get("profit_margin")),
            ]
            for c in categories[:10]
        ]
        doc.table(["Category", "Revenue", "Share", "Margin"], rows, [2.5, 1.5, 1.0, 1.0])

    # ---- inventory -------------------------------------------------------
    risky = [
        item
        for item in inventory
        if str(item.get("stock_status", "")).lower() in ("critical", "low")
    ]
    if risky:
        doc.heading("Inventory risks")
        rows = [
            [
                str(item.get("product", ""))[:34],
                _count(item.get("inventory")),
                (
                    f"{float(item['days_of_inventory_cover']):.1f}"
                    if isinstance(item.get("days_of_inventory_cover"), (int, float))
                    and item["days_of_inventory_cover"] == item["days_of_inventory_cover"]
                    else "unknown"
                ),
                str(item.get("stock_status", "")).title(),
            ]
            for item in risky[:12]
        ]
        doc.table(["Product", "Units left", "Days of cover", "Status"], rows, [2.5, 1.2, 1.3, 1.2])
        doc.paragraph(
            "Stock levels are inferred from the sales history you uploaded, not read from a "
            "live inventory system.",
            8.5,
            MUTED,
        )

    # ---- insights --------------------------------------------------------
    findings = insights.get("findings") or []
    doc.heading("Key insights")
    if not findings:
        doc.paragraph(
            "Nothing in this period moved far enough to flag. Revenue, orders, customers "
            "and stock are all within their normal range."
        )
    else:
        basis = insights.get("comparison_basis")
        if basis == "previous_period":
            doc.paragraph("Each finding compares this period with the period immediately before it.")
        elif basis == "within_period":
            doc.paragraph(
                "No earlier period was available, so each finding compares the second half "
                "of this period with the first."
            )
        for finding in findings[:10]:
            severity = str(finding.get("severity", "")).upper()
            colour = ALERT if severity == "HIGH" else (GOLD if severity == "MEDIUM" else MUTED)
            doc.need(40)
            doc.text(f"[{severity}] {finding.get('category', '')}", MARGIN_X, doc.y, 8.5, colour, bold=True)
            doc.space(13)
            doc.paragraph(str(finding.get("title", "")), 10.0)
            doc.paragraph(str(finding.get("description", "")), 9.0, MUTED)
            doc.paragraph(f"Why this was flagged: {finding.get('reason', '')}", 8.5, MUTED)
            doc.space(4)

    # ---- recommendations -------------------------------------------------
    doc.heading("Prioritised recommendations")
    items = [*(plan.get("high") or []), *(plan.get("medium") or []), *(plan.get("low") or [])]
    if not items:
        doc.paragraph(
            "Nothing needs attention in this period. Revenue, orders and stock are all "
            "within their normal range."
        )
    else:
        for item in items:
            priority = str(item.get("priority", ""))
            colour = ALERT if priority == "High" else (GOLD if priority == "Medium" else MUTED)
            doc.need(46)
            doc.text(
                f"{item.get('rank', '')}. {priority} priority - {item.get('category', '')}",
                MARGIN_X, doc.y, 8.5, colour, bold=True,
            )
            doc.space(13)
            doc.paragraph(str(item.get("title", "")), 10.0)
            doc.paragraph(str(item.get("action", "")), 9.0)
            doc.paragraph(f"Why: {item.get('reason', '')}", 8.5, MUTED)
            doc.space(4)
        for note in plan.get("notes") or []:
            doc.paragraph(str(note), 8.5, MUTED)

    # ---- forecast --------------------------------------------------------
    doc.heading("Short-term forecast")
    if not forecast.get("available"):
        doc.paragraph(
            str(forecast.get("reason") or "A forecast could not be produced for this period.")
        )
    else:
        period = forecast.get("forecast_period") or {}
        backtest = forecast.get("backtest") or {}
        doc.key_values(
            [
                ("Method", str(forecast.get("method", "")).replace("_", " ")),
                ("Forecast period", f"{period.get('start', '-')} to {period.get('end', '-')}"),
                ("Days projected", _count(period.get("days"))),
                ("Trend", str(forecast.get("trend_direction", "")).title()),
                ("Projected total revenue", _money(forecast.get("forecast_total"), currency)),
                ("Recent daily average", _money(forecast.get("history_daily_mean"), currency)),
                (
                    "Typical error (measured)",
                    _pct(backtest.get("mean_absolute_percentage_error"))
                    if backtest.get("mean_absolute_percentage_error") is not None
                    else "Not measured",
                ),
            ]
        )
        for note in forecast.get("limitations") or []:
            doc.bullet(str(note), MUTED)

    # ---- methodology -----------------------------------------------------
    doc.heading("Methodology and limitations")
    doc.paragraph(
        "Every figure in this report was computed from the data you uploaded, by the same "
        "analytics that produce your dashboard. No number here was estimated, rounded up or "
        "produced by a language model."
    )
    doc.subheading("How findings are chosen")
    doc.paragraph(
        "A change is reported only when it crosses a documented threshold: 5% for a low "
        "finding, 10% for medium and 20% for high on a total such as revenue; 1.5, 3.0 and "
        "5.0 percentage points on a rate such as the returning-customer share. Stock cover "
        "below 3 days is critical and below 7 days is low. Smaller movements are treated as "
        "normal variation and are not reported."
    )
    doc.subheading("What this report cannot tell you")
    for note in [
        "It reports what changed, not why. Your data contains no marketing spend, weather, "
        "competitor activity or local events, so no cause can be established from it.",
        "Gross profit excludes overheads such as rent, salaries and utilities.",
        "Customer counts are visits. A shopper who returns on three days is counted three times.",
        "Stock levels are inferred from sales history rather than a live inventory feed.",
        "The forecast is a short-term statistical projection of the trend and weekly pattern "
        "already present in your data. It reports its measured historical error and gives no "
        "confidence interval, because the method cannot honestly support one.",
    ]:
        doc.bullet(note, MUTED)

    doc.space(10)
    doc.need(30)
    doc.line(MARGIN_X, doc.y, PAGE_W - MARGIN_X)
    doc.space(12)
    doc.text(
        f"Generated by MerchantAI on {generated} from data uploaded by the business owner.",
        MARGIN_X, doc.y, 8.5, MUTED,
    )

    return doc.build(f"MerchantAI report - {name}")


def _executive_summary(
    name: str, summary: dict, insights: dict, plan: dict, forecast: dict, currency: str
) -> str:
    """One paragraph, assembled only from figures that are actually present."""
    revenue = summary.get("total_revenue")
    orders = summary.get("total_orders")
    if not revenue and not orders:
        return (
            f"No trading activity was recorded for {name} in this period, so there is "
            "nothing to summarise."
        )

    parts = [
        f"{name} recorded {_money(revenue, currency)} of revenue across "
        f"{_count(orders)} orders in this period, with a gross profit of "
        f"{_money(summary.get('total_profit'), currency)} "
        f"({_pct(summary.get('profit_margin'))} margin)."
    ]

    visits = summary.get("total_customers")
    if visits:
        parts.append(
            f"There were {_count(visits)} customer visits, "
            f"{_pct(summary.get('repeat_customer_rate'))} of them from returning customers."
        )

    counts = insights.get("severity_counts") or {}
    high, medium = counts.get("HIGH", 0), counts.get("MEDIUM", 0)
    if high or medium:
        parts.append(
            f"The analysis flagged {high} high-severity and {medium} medium-severity "
            "changes, listed in full below."
        )
    else:
        parts.append("Nothing in this period moved far enough to flag as a significant change.")

    items = [*(plan.get("high") or []), *(plan.get("medium") or [])]
    if items:
        parts.append(f"The most urgent action is: {items[0].get('title', '')}.")

    if forecast.get("available"):
        parts.append(
            f"Revenue is trending {str(forecast.get('trend_direction', '')).lower()}, with "
            f"{_money(forecast.get('forecast_total'), currency)} projected over the next "
            f"{_count((forecast.get('forecast_period') or {}).get('days'))} days."
        )

    return " ".join(parts)
