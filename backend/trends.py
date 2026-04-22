"""Trend classification over a short time series of Edge metrics."""

from typing import Optional

RISING = "rising"
STABLE = "stable"
DECLINING = "declining"

# Minimum games played for a season to count toward the trend.
# Below this, the sample is too small for Edge metrics to be meaningful
# (injury-shortened seasons, late call-ups, traded-at-deadline cases).
MIN_GP_FOR_TREND = 20

# Percent change between the most recent season and the mean of prior
# valid seasons that flips the badge away from 'stable'. 2% catches the
# kind of year-over-year shift a human notices in the chart without
# flagging ordinary variance.
TREND_THRESHOLD = 0.02


def classify_trend(values: list, games_played: Optional[list] = None) -> Optional[str]:
    """
    Classify how the most recent season compares to the prior seasons.

    `values` is oldest-to-newest. If `games_played` is given (same length),
    seasons with < MIN_GP_FOR_TREND games are filtered out -- a 4-game season
    is noise, not a trend point.

    The signal is last-season-value minus the mean of prior valid seasons,
    expressed as a percent. This matches how a human reads the table:
    "did this year jump / drop compared to the baseline of the last few years?"

    Returns 'rising' / 'stable' / 'declining', or None if fewer than two
    seasons pass the filter.
    """
    if games_played is not None and len(games_played) == len(values):
        pairs = [
            v for v, g in zip(values, games_played)
            if v is not None and g is not None and g >= MIN_GP_FOR_TREND
        ]
    else:
        pairs = [v for v in values if v is not None]

    if len(pairs) < 2:
        return None

    last = pairs[-1]
    prior_mean = sum(pairs[:-1]) / (len(pairs) - 1)
    if prior_mean == 0:
        return STABLE

    pct_change = (last - prior_mean) / prior_mean

    if pct_change > TREND_THRESHOLD:
        return RISING
    if pct_change < -TREND_THRESHOLD:
        return DECLINING
    return STABLE
