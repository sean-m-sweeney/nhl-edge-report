#!/usr/bin/env python3
"""
Audit trend classifications across every player with Edge history.

Surfaces classifications that are:
  - BORDERLINE: within +/- 0.5% of the 2% threshold (fragile, could flip on
    a small data update).
  - RAW-vs-PG DISAGREES: raw burst totals and per-game rate tell different
    stories -- a red flag that the per-game normalization is the right call,
    but also a case the UI may visually confuse the reader on.
  - CAREER-HIGH DECLINING: current season is the max of all full-season
    values, yet classified declining. Shouldn't happen with last-vs-prior-mean,
    but good canary for algorithm changes.
  - CAREER-LOW RISING: mirror of the above.

Read-only. Usage:
    docker exec edge-report python -m scripts.audit_trends [--metric top_speed_mph]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import database
from backend.trends import (
    classify_trend,
    MIN_GP_FOR_TREND,
    TREND_THRESHOLD,
    RISING,
    DECLINING,
)

BORDERLINE_WINDOW = 0.005  # +/- 0.5 percentage points around the 2% threshold

# (display, db_column, normalize_by_gp)
METRICS = [
    ("top_speed_mph", "top_speed_mph", False),
    ("bursts_18_plus", "bursts_18_plus", True),
    ("bursts_20_plus", "bursts_20_plus", True),
    ("distance_per_game_miles", "distance_per_game_miles", False),
    ("top_shot_speed_mph", "top_shot_speed_mph", False),
]


def pct_change_for(values, games_played):
    """Recompute the pct_change used by classify_trend so we can see magnitude."""
    pairs = [
        v for v, g in zip(values, games_played)
        if v is not None and g is not None and g >= MIN_GP_FOR_TREND
    ]
    if len(pairs) < 2:
        return None
    last = pairs[-1]
    prior_mean = sum(pairs[:-1]) / (len(pairs) - 1)
    if prior_mean == 0:
        return 0.0
    return (last - prior_mean) / prior_mean


def evaluate_player(player_id, player_name, season_rows):
    flags = []

    gp_series = [s.get("games_played") for s in season_rows]
    # Only-full-seasons (GP >= 40) view used for career-high/low checks.
    full_only = [s for s in season_rows if (s.get("games_played") or 0) >= MIN_GP_FOR_TREND]

    for display, col, normalize in METRICS:
        raw_vals = [s.get(col) for s in season_rows]
        if normalize:
            # per-game values
            values = [
                (v / g) if (v is not None and g) else None
                for v, g in zip(raw_vals, gp_series)
            ]
        else:
            values = list(raw_vals)

        trend = classify_trend(values, gp_series)
        if trend is None:
            continue

        pct = pct_change_for(values, gp_series)
        if pct is None:
            continue

        # BORDERLINE: just outside or just inside threshold
        if abs(abs(pct) - TREND_THRESHOLD) <= BORDERLINE_WINDOW:
            flags.append(
                f"BORDERLINE  {display:26} {trend:10} pct={pct*100:+.2f}%"
            )

        # CAREER HIGH / LOW on full-season values
        full_vals = [v for v, s in zip(values, season_rows)
                     if v is not None and (s.get("games_played") or 0) >= MIN_GP_FOR_TREND]
        if len(full_vals) >= 2:
            current_in_full = full_vals[-1]
            prior_full = full_vals[:-1]
            if prior_full:
                if current_in_full >= max(prior_full) and trend == DECLINING:
                    flags.append(
                        f"CAREER-HIGH DECLINING  {display:26} values={[round(v,2) for v in full_vals]}"
                    )
                if current_in_full <= min(prior_full) and trend == RISING:
                    flags.append(
                        f"CAREER-LOW RISING      {display:26} values={[round(v,2) for v in full_vals]}"
                    )

        # RAW vs PER-GAME disagreement (only for normalized metrics)
        if normalize:
            raw_trend = classify_trend(raw_vals, gp_series)
            if raw_trend in (RISING, DECLINING) and trend in (RISING, DECLINING) and raw_trend != trend:
                flags.append(
                    f"RAW/PG DISAGREES  {display:22} raw={raw_trend:10} per-game={trend}"
                )

    return flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after N players (0 = all)")
    args = parser.parse_args()

    with database.db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.player_id, p.name FROM players p
            WHERE p.position != 'G'
            AND EXISTS (SELECT 1 FROM player_season_edge_stats e WHERE e.player_id = p.player_id)
            ORDER BY p.name
        """)
        players = cur.fetchall()

    total = len(players)
    if args.limit:
        players = players[:args.limit]

    flagged = 0
    total_flags = 0
    categories = {}
    per_player = []
    for row in players:
        pid, name = row["player_id"], row["name"]
        season_rows = database.get_player_season_history(pid)
        if len(season_rows) < 2:
            continue
        flags = evaluate_player(pid, name, season_rows)
        if flags:
            flagged += 1
            total_flags += len(flags)
            per_player.append((name, pid, flags))
            for f in flags:
                key = f.split()[0] + (" " + f.split()[1] if f.split()[0] in ("CAREER-HIGH", "CAREER-LOW", "RAW/PG") else "")
                categories[key] = categories.get(key, 0) + 1

    # Print category summary first
    print(f"\n==== AUDIT SUMMARY ({total} players, {flagged} flagged, {total_flags} total flags) ====\n")
    for k, v in sorted(categories.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    print()

    # Sort per-player entries: raw/pg disagreement + career-high/low first, then borderline
    def severity(p):
        serious = sum(1 for f in p[2] if "BORDERLINE" not in f)
        return (-serious, -len(p[2]), p[0])
    per_player.sort(key=severity)

    print("==== PER-PLAYER FLAGS (worst-first) ====\n")
    for name, pid, flags in per_player:
        print(f"{name} ({pid})")
        for f in flags:
            print(f"  {f}")
        print()


if __name__ == "__main__":
    main()
