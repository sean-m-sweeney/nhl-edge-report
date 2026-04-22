"""Trend classification over a short time series of Edge metrics."""

from typing import Optional

RISING = "rising"
STABLE = "stable"
DECLINING = "declining"

# Per-season percent change that flips a value away from 'stable'. 1.5% per
# season is ~4.5% over three seasons -- well outside noise for speed metrics,
# and still conservative enough that a single soft year doesn't mis-flag
# burst/distance counts.
TREND_THRESHOLD = 0.015


def classify_trend(values: list) -> Optional[str]:
    """
    Classify a short sequence of metric values across seasons.

    `values` is oldest-to-newest. None/zero entries are dropped before fitting.
    Returns 'rising' / 'stable' / 'declining', or None if there are fewer than
    two valid data points.

    The slope is a simple OLS line through (season_index, value), normalized by
    the mean to get a per-season percent change. Magnitudes below TREND_THRESHOLD
    are classified as stable to avoid calling noise a trend.
    """
    cleaned = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(cleaned) < 2:
        return None

    xs = [p[0] for p in cleaned]
    ys = [p[1] for p in cleaned]
    mean_y = sum(ys) / len(ys)
    if mean_y == 0:
        return STABLE

    n = len(cleaned)
    mean_x = sum(xs) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return STABLE

    slope = num / den
    pct_change = slope / mean_y

    if pct_change > TREND_THRESHOLD:
        return RISING
    if pct_change < -TREND_THRESHOLD:
        return DECLINING
    return STABLE
