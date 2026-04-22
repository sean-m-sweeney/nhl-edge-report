#!/usr/bin/env python3
"""
One-shot backfill of per-season NHL Edge stats for every active skater.

NHL Edge player-tracking data is available from the 2021-22 season onward. This
script iterates every skater in the database across every season we care about,
calls the Edge API via the existing async fetcher, and upserts into the
player_season_edge_stats table.

Idempotent: skips (player_id, season) rows that are already stored, so it is
safe to re-run after failures or to add new seasons.

Usage:
    python -m scripts.backfill_historical_edge                    # all seasons
    python -m scripts.backfill_historical_edge --seasons 20232024 # just one
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

# Make repo-root imports work when invoked as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from backend import database
from backend.fetcher import async_fetch_edge_stats_for_season, MAX_CONCURRENT_REQUESTS

DEFAULT_SEASONS = ["20212022", "20222023", "20232024", "20242025"]  # current season is kept fresh by cron

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_edge")


async def backfill_one_season(
    client: httpx.AsyncClient, season: str, player_ids: list
) -> int:
    """Fetch Edge stats for each player_id for the given season. Returns count written."""
    written = 0
    batch_size = MAX_CONCURRENT_REQUESTS
    for i in range(0, len(player_ids), batch_size):
        batch = player_ids[i:i + batch_size]
        tasks = [async_fetch_edge_stats_for_season(client, pid, season) for pid in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for pid, result in zip(batch, results):
            if isinstance(result, Exception) or not result:
                continue
            database.upsert_player_season_edge_stats(
                pid, season, result.get("games_played"), result
            )
            written += 1
        done = min(i + batch_size, len(player_ids))
        if done % 100 == 0 or done == len(player_ids):
            logger.info(f"  season {season}: {done}/{len(player_ids)} processed ({written} written)")
    return written


async def main_async(seasons: list):
    # Load every skater currently in the DB
    with database.db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT player_id FROM players WHERE position != 'G'")
        all_player_ids = [row["player_id"] for row in cursor.fetchall()]

    if not all_player_ids:
        logger.error("No players in database -- run a refresh first so players exist")
        return 1

    logger.info(f"Starting backfill for {len(all_player_ids)} players across {len(seasons)} seasons")
    started = datetime.now()

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for season in seasons:
            # Skip rows already stored for this season so the script is resumable.
            with database.db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT player_id FROM player_season_edge_stats WHERE season = ?",
                    (season,)
                )
                already = {row["player_id"] for row in cursor.fetchall()}
            todo = [pid for pid in all_player_ids if pid not in already]
            logger.info(
                f"Season {season}: {len(todo)} to fetch "
                f"({len(already)} already stored)"
            )
            if not todo:
                continue
            written = await backfill_one_season(client, season, todo)
            logger.info(f"Season {season}: wrote {written} rows")

    elapsed = (datetime.now() - started).total_seconds()
    logger.info(f"Backfill complete in {elapsed:.0f}s")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=DEFAULT_SEASONS,
        help="Seasons to backfill (8-digit format, e.g. 20232024). Defaults to all seasons since Edge tracking began.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    database.init_db()
    return asyncio.run(main_async(args.seasons))


if __name__ == "__main__":
    sys.exit(main())
