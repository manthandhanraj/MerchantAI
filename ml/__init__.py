"""Modelling workspace (used from Stage 6).

Boundary with `backend/app/services/`:
    ml/       - model code and any offline experimentation
    services/ - request-time orchestration that calls into ml/

Kept separate so the forecasting approach can change without touching the
API layer. Empty until Stage 6; the MVP forecast starts with a simple
trend/moving-average baseline before anything heavier is considered.
"""
