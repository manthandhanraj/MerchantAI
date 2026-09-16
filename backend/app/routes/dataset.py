"""Dataset endpoints (Stage 2).

These expose what the pipeline produced — the merchant list, a dataset summary
and the validation report. Dashboard metrics are Stage 3 and deliberately not
served here.

Routes stay thin: each one loads the dataset and calls a single service.
Every aggregate is computed in `services/metrics.py`, never in this module.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset
from backend.app.services.metrics import merchant_directory, summary_metrics

router = APIRouter(prefix="/api", tags=["dataset"])


class MerchantEntry(BaseModel):
    merchant_id: str
    total_revenue: float
    total_orders: int
    products: int
    categories: int
    first_date: str
    last_date: str


class MerchantListResponse(BaseModel):
    count: int
    merchants: list[MerchantEntry]


class DatasetSummaryResponse(BaseModel):
    synthetic: bool = Field(
        default=True,
        description="Always true. This dataset is generated, never real merchant data.",
    )
    sales_rows: int
    customer_rows: int
    merchants: list[str]
    products: int
    categories: int
    date_start: str
    date_end: str
    days: int
    restock_events: int
    validation_status: str
    totals: dict


class ValidationIssueEntry(BaseModel):
    rule: str
    severity: str
    message: str
    count: int
    examples: list[str]


class ValidationResponse(BaseModel):
    ok: bool
    summary: str
    errors: list[ValidationIssueEntry]
    warnings: list[ValidationIssueEntry]
    stats: dict


@router.get("/merchants", response_model=MerchantListResponse)
def list_merchants(dataset: LoadedDataset) -> MerchantListResponse:
    """Merchants available in the dataset, for the frontend's selector."""
    entries = merchant_directory(dataset)
    return MerchantListResponse(count=len(entries), merchants=entries)


@router.get("/dataset/summary", response_model=DatasetSummaryResponse)
def dataset_summary(dataset: LoadedDataset) -> DatasetSummaryResponse:
    """Shape of the loaded dataset plus portfolio-wide totals."""
    stats = dataset.validation.stats
    start, end = dataset.date_range

    return DatasetSummaryResponse(
        sales_rows=int(len(dataset.sales)),
        customer_rows=int(len(dataset.customers)),
        merchants=dataset.merchant_ids,
        products=int(dataset.sales["product"].nunique()),
        categories=int(dataset.sales["category"].nunique()),
        date_start=start.isoformat(),
        date_end=end.isoformat(),
        days=int(dataset.sales["date"].nunique()),
        restock_events=int(stats.get("restock_events", 0)),
        validation_status=dataset.validation.summary(),
        totals=summary_metrics(dataset),
    )


@router.get("/dataset/validation", response_model=ValidationResponse)
def dataset_validation(dataset: LoadedDataset) -> ValidationResponse:
    """Full validation report for the loaded dataset.

    Reachable only when the dataset already passed, since loading raises
    otherwise. It exists so the report stays inspectable rather than being a
    one-off check buried at startup.
    """
    report = dataset.validation

    def to_entry(issue) -> ValidationIssueEntry:
        return ValidationIssueEntry(
            rule=issue.rule,
            severity=issue.severity,
            message=issue.message,
            count=issue.count,
            examples=list(issue.examples),
        )

    return ValidationResponse(
        ok=report.ok,
        summary=report.summary(),
        errors=[to_entry(i) for i in report.errors],
        warnings=[to_entry(i) for i in report.warnings],
        stats=report.stats,
    )
