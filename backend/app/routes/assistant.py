"""AI assistant endpoint (Stage 6).

Thin: validate, call `services/assistant.py`, serialise. The context assembly,
the offline answer path and the numeric grounding check all live in the service.

The endpoint works with no API key and no network: `LLM_ENABLED` defaults to
false and the assistant answers deterministically from the merchant's own data.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset, validate_query
from backend.app.services.assistant import STARTER_QUESTIONS, ask
from backend.app.services.llm import describe as describe_llm

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

MAX_QUESTION_LENGTH = 500


class AskRequest(BaseModel):
    merchant_id: str = Field(description="Merchant to answer about, e.g. 'M001'.")
    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
        description="The merchant's question, in plain language.",
    )
    start: date | None = Field(default=None, description="Inclusive start date (YYYY-MM-DD).")
    end: date | None = Field(default=None, description="Inclusive end date (YYYY-MM-DD).")
    include_context: bool = Field(
        default=False,
        description="Return the full structured context the answer was grounded in.",
    )


class AskResponse(BaseModel):
    merchant_id: str
    question: str
    answer: str
    source: str = Field(
        description="'deterministic' when answered from the data directly, 'llm' when "
        "a verified model response was used."
    )
    llm_enabled: bool
    has_data: bool
    grounded_in: list[str] = Field(
        default_factory=list, description="Context sections the answer drew on."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Model unavailability, or a reply rejected for untraceable figures.",
    )
    suggested_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    context: dict | None = None


class AssistantStatusResponse(BaseModel):
    enabled: bool = Field(description="Whether a live model call is possible.")
    flag_set: bool
    key_present: bool = Field(description="Whether a key is configured. Never the key itself.")
    provider: str
    model: str
    suggested_questions: list[str]


@router.get("/status", response_model=AssistantStatusResponse)
def status() -> AssistantStatusResponse:
    """Assistant configuration, for the UI to show the right state.

    Never returns the API key — only whether one is present.
    """
    return AssistantStatusResponse(
        **describe_llm(), suggested_questions=list(STARTER_QUESTIONS)
    )


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(payload: AskRequest, dataset: LoadedDataset) -> AskResponse:
    """Answer a question about one merchant, grounded in computed analytics.

    Always returns an answer. A disabled or failing model degrades to the
    deterministic path with a warning, rather than failing the request.
    """
    validate_query(dataset, payload.merchant_id, payload.start, payload.end)

    result = ask(
        dataset,
        payload.merchant_id,
        payload.question,
        start=payload.start,
        end=payload.end,
        include_context=payload.include_context,
    )
    return AskResponse(**result.as_dict())
