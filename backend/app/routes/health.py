"""Health and readiness endpoint.

Used by the frontend to confirm it can reach the API, and by us to confirm
the dataset expected by later stages is actually present on disk.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.config import settings

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    sales_data_present: bool
    customers_data_present: bool
    llm_enabled: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report service status and whether the Stage 2 datasets exist yet."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
        sales_data_present=settings.sales_path.exists(),
        customers_data_present=settings.customers_path.exists(),
        llm_enabled=settings.llm_enabled,
    )
