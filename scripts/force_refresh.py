#!/usr/bin/env python3
"""
Invalidate the 6-hour Edge-stats cache and run a full refresh.

Use this after deploys that add new columns / change parsing so the main
player_edge_stats rows pick up the new fields immediately instead of waiting
for a rolling cache expiration.

Usage:
    docker exec edge-report python -m scripts.force_refresh
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import database
from backend.fetcher import refresh_data


def main():
    database.init_db()
    with database.db_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE player_edge_stats SET updated_at = '2000-01-01T00:00:00'")
        cur.execute("UPDATE goalies SET updated_at = '2000-01-01T00:00:00'")
        conn.commit()
    print(f"[{datetime.now().isoformat()}] Edge cache invalidated; starting forced refresh")
    updated = refresh_data()
    print(f"[{datetime.now().isoformat()}] Forced refresh complete. Updated {updated} players.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
