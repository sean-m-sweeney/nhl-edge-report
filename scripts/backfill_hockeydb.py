#!/usr/bin/env python3
"""
Populate the NHL-player-id -> HockeyDB-pid mapping by scraping HockeyDB's
player search by name.

Idempotent: players already marked 'found' (or 'ambiguous') are skipped. Rows
marked 'not_found' are skipped unless --retry-not-found is passed -- the
weekly cron uses that flag so rookies who weren't in HockeyDB yet get another
chance.

Usage:
    python -m scripts.backfill_hockeydb                   # first-time backfill
    python -m scripts.backfill_hockeydb --retry-not-found # weekly delta job
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import database
from backend.hockeydb import lookup_many

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_hockeydb")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retry-not-found",
        action="store_true",
        help="Also retry rows previously marked 'not_found'. Use for the weekly delta job.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Seconds between requests (default 3). HockeyDB returns 403 if hit too fast.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    database.init_db()

    missing = database.get_players_missing_hockeydb(retry_not_found=args.retry_not_found)
    if not missing:
        logger.info("No players need HockeyDB lookup -- nothing to do")
        return 0

    logger.info(f"Looking up {len(missing)} players on HockeyDB (delay={args.delay}s)")

    # Build the lookup payload with birth years where we have them.
    payload = []
    for player_id, name in missing:
        payload.append({
            "player_id": player_id,
            "full_name": name,
            "birth_year": database.get_player_birth_year(player_id),
        })

    def progress(done, total):
        if done % 25 == 0 or done == total:
            logger.info(f"  progress: {done}/{total}")

    results = lookup_many(payload, delay_seconds=args.delay, progress_callback=progress)

    counts = {"found": 0, "not_found": 0, "ambiguous": 0, "rate_limited": 0}
    for player_id, (pid, status) in results.items():
        database.upsert_hockeydb_mapping(player_id, pid, status)
        counts[status] = counts.get(status, 0) + 1

    logger.info(f"Done. Results: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
