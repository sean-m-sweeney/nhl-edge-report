#!/usr/bin/env python3
"""
Weekly HockeyDB delta. Picks up new players (no mapping row), retries rows
previously marked 'not_found' in case a rookie has since been indexed, and
retries anything previously rate-limited.

Thin wrapper around backfill_hockeydb with --retry-not-found.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backfill_hockeydb import main as backfill_main  # noqa: E402


def main():
    # Monkey-patch argv so backfill_main's argparse sees --retry-not-found.
    sys.argv = [sys.argv[0], "--retry-not-found"]
    return backfill_main()


if __name__ == "__main__":
    sys.exit(main())
