"""Pure numeric helpers shared by the processing layer.

Everything here is generic and business-rule free. Every division in MerchantAI
goes through `safe_divide`: a merchant with a quiet day genuinely has zero
orders, and that must render as 0.0, never as `inf` or `NaN`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def safe_divide(
    numerator: float | pd.Series,
    denominator: float | pd.Series,
    default: float = 0.0,
) -> float | pd.Series:
    """Divide, substituting `default` wherever the denominator is zero or the
    result is not finite. Works on both scalars and pandas Series.

    A scalar operand is kept scalar so pandas broadcasts it across the Series.
    Wrapping it in `pd.Series(...)` would build a one-element Series and make
    the division *index-align* instead, silently blanking every row but the
    first — which is how a share-of-total column ends up as zeros.
    """
    numerator_is_series = isinstance(numerator, pd.Series)
    denominator_is_series = isinstance(denominator, pd.Series)

    if numerator_is_series or denominator_is_series:
        left = numerator if numerator_is_series else float(numerator)
        right = denominator if denominator_is_series else float(denominator)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = left / right
        if not isinstance(result, pd.Series):
            result = pd.Series(result)
        return result.replace([np.inf, -np.inf], np.nan).fillna(default).astype("float64")

    if not denominator:
        return default
    result = numerator / denominator
    return result if np.isfinite(result) else default


def growth_rate(current: float, previous: float) -> float:
    """Period-over-period change as a fraction. Returns 0.0 when there is no
    prior period to compare against, which is the honest answer rather than
    an infinite or undefined growth rate."""
    return float(safe_divide(current - previous, previous, default=0.0))


def round_money(value: float) -> float:
    """Round to paise. Applied at the API boundary so floating-point noise
    never reaches the UI."""
    return round(float(value), 2)


def round_rate(value: float) -> float:
    """Round a fraction/rate to four places (0.1234 = 12.34%)."""
    return round(float(value), 4)
