"""Shared FastAPI dependencies.

Loading the dataset is the one thing every data route does, and every route
needs to fail the same way when the pipeline is not ready. Keeping that in one
dependency stops each router growing its own copy of the error handling.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException

from backend.app.services.data_loader import Dataset, DatasetNotFoundError, get_dataset
from backend.app.services.validation import DatasetValidationError


def load_dataset() -> Dataset:
    """Load the dataset, turning pipeline failures into an honest 503.

    A missing or invalid dataset is a service-not-ready condition rather than a
    bad request, and the detail carries the exact command to fix it.
    """
    try:
        return get_dataset()
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DatasetValidationError as exc:
        raise HTTPException(status_code=503, detail=f"Dataset failed validation.\n{exc}") from exc


LoadedDataset = Annotated[Dataset, Depends(load_dataset)]


def validate_query(dataset: Dataset, merchant_id: str, start: date | None, end: date | None) -> None:
    """Reject an unknown merchant or an inverted date range.

    Shared by every per-merchant route so they fail identically: a client
    should not have to learn a different error shape per endpoint.
    """
    known = dataset.merchant_ids
    if merchant_id not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown merchant '{merchant_id}'. Available merchants: {', '.join(known)}.",
        )

    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: start ({start}) is after end ({end}).",
        )
