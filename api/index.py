"""Vercel serverless entry point for the MerchantAI API.

Vercel's Python runtime treats a module-level ASGI `app` in `api/` as the
handler, so this file only needs to make `backend` importable and re-export the
existing application. No routes, settings or behaviour are redefined here — the
deployed API is exactly the one `runner.py` serves locally.

Routing: `vercel.json` rewrites `/api/(.*)` to this function, and every route
the app defines is already under `/api/`, so paths line up without a prefix
being added or stripped.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The function bundle keeps the repository layout, so the project root is one
# level up. `backend.app.config` derives the data paths from that same root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app  # noqa: E402

__all__ = ["app"]
