"""Small, dependency-free helpers shared across services.

Anything here must be pure and generic (date windows, safe division,
percentage formatting). Business rules belong in `services/`, not here.

Implemented:
    calculations.py - safe_divide, growth_rate, rounding helpers
"""
