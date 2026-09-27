"""MerchantAI API entrypoint.

Run from the project root:

    uvicorn backend.app.main:app --reload

Interactive docs: http://127.0.0.1:8000/docs
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import settings
from backend.app.routes import (
    accounts,
    action_plan,
    assistant,
    dashboard,
    dataset,
    forecast,
    health,
    insights,
    recommendations,
    workspace,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="MerchantAI API",
    description="AI business copilot for merchants.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(dataset.router)
app.include_router(dashboard.router)
app.include_router(insights.router)
app.include_router(recommendations.router)
app.include_router(action_plan.router)
app.include_router(forecast.router)
app.include_router(assistant.router)
app.include_router(workspace.router)
app.include_router(accounts.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return clean JSON for unexpected failures.

    The traceback belongs in the server log, not in a response the browser has
    to render. The frontend gets a message it can display as-is.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check the API logs for details."},
    )


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
