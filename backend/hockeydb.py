"""HockeyDB player ID lookup.

HockeyDB uses its own numeric player IDs (`pid`) rather than NHL player IDs, so
we have to look each player up by name. A successful lookup returns a profile
URL like `https://www.hockeydb.com/ihdb/stats/pdisplay.php?pid=63735`.

Search strategy (per `_search_once`):
1. Hit `/ihdb/stats/find_player.php?full_name=First+Last`.
2. On a unique match, HockeyDB redirects to the profile; we extract `pid` from
   the `<link rel="canonical">` tag.
3. On multiple matches, we parse the results table and pick the row whose YOB
   matches the NHL-API birth year. If none matches uniquely, we return
   'ambiguous' rather than guess.

The module intentionally uses httpx + stdlib regex (no bs4) to avoid an extra
dependency for a small scrape surface. Be polite -- callers should rate-limit.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

BASE = "https://www.hockeydb.com"
SEARCH_URL = f"{BASE}/ihdb/stats/find_player.php"
PROFILE_URL_TEMPLATE = f"{BASE}/ihdb/stats/pdisplay.php?pid={{pid}}"

# `<link rel="canonical" href="https://www.hockeydb.com/ihdb/stats/pdisplay.php?pid=63735" />`
_CANONICAL_RE = re.compile(
    r'<link\s+rel="canonical"\s+href="[^"]*?pdisplay\.php\?pid=(\d+)"',
    re.IGNORECASE,
)

# Each row in the ambiguous-results table:
# `<tr data-status='...'><td><input ... value='164509' ... col-yob'>1996</td>...`
_RESULT_ROW_RE = re.compile(
    r"<tr[^>]*data-status[^>]*>(.*?)</tr>",
    re.DOTALL | re.IGNORECASE,
)
_PID_RE = re.compile(r"pid\[\]'\s*value='(\d+)'")
_YOB_RE = re.compile(r"col-yob'>(\d{4})<")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) edgereport-player-link/1.0 (+https://edgereport.io) "
    "Safari/537.36"
)
DEFAULT_TIMEOUT = 10.0

STATUS_FOUND = "found"
STATUS_NOT_FOUND = "not_found"
STATUS_AMBIGUOUS = "ambiguous"


def hockeydb_profile_url(pid: int) -> str:
    return PROFILE_URL_TEMPLATE.format(pid=pid)


def _extract_canonical_pid(html: str) -> Optional[int]:
    m = _CANONICAL_RE.search(html)
    return int(m.group(1)) if m else None


def _parse_results_table(html: str) -> list:
    """Return a list of {pid, yob} dicts from an ambiguous-results page."""
    rows = []
    for row_html in _RESULT_ROW_RE.findall(html):
        pid_m = _PID_RE.search(row_html)
        yob_m = _YOB_RE.search(row_html)
        if pid_m:
            rows.append({
                "pid": int(pid_m.group(1)),
                "yob": int(yob_m.group(1)) if yob_m else None,
            })
    return rows


STATUS_RATE_LIMITED = "rate_limited"


def _search_once(client: httpx.Client, full_name: str, birth_year: Optional[int]) -> tuple:
    """
    Perform one HockeyDB search.

    Returns (pid, status). Status is one of STATUS_FOUND, STATUS_NOT_FOUND,
    STATUS_AMBIGUOUS, STATUS_RATE_LIMITED. A rate-limited result should be
    retried later by the caller (e.g., the weekly cron will retry not_found
    rows; 403s often come from IP throttling).
    """
    try:
        resp = client.get(SEARCH_URL, params={"full_name": full_name})
    except httpx.HTTPError as e:
        logger.warning(f"HockeyDB request failed for {full_name!r}: {e}")
        return None, STATUS_NOT_FOUND

    if resp.status_code == 403 or resp.status_code == 429:
        logger.warning(f"HockeyDB rate-limited for {full_name!r} (status {resp.status_code})")
        return None, STATUS_RATE_LIMITED
    if resp.status_code != 200:
        logger.warning(f"HockeyDB returned {resp.status_code} for {full_name!r}")
        return None, STATUS_NOT_FOUND

    html = resp.text

    # Unique-match path: the server redirects to the profile page.
    canonical_pid = _extract_canonical_pid(html)
    if canonical_pid is not None:
        return canonical_pid, STATUS_FOUND

    # Ambiguous-match path: results table on the page.
    rows = _parse_results_table(html)
    if not rows:
        return None, STATUS_NOT_FOUND

    if birth_year is not None:
        matches = [r for r in rows if r["yob"] == birth_year]
        if len(matches) == 1:
            return matches[0]["pid"], STATUS_FOUND

    return None, STATUS_AMBIGUOUS


def lookup_player(
    full_name: str,
    birth_year: Optional[int] = None,
    client: Optional[httpx.Client] = None,
) -> tuple:
    """
    Look up a player on HockeyDB by name, optionally disambiguating by birth year.

    Returns (pid_or_None, status).
    """
    if client is None:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        ) as c:
            return _search_once(c, full_name, birth_year)
    return _search_once(client, full_name, birth_year)


def lookup_many(
    players: list,
    delay_seconds: float = 3.0,
    progress_callback=None,
    stop_on_rate_limit_after: int = 5,
) -> dict:
    """
    Run HockeyDB lookups for many players with polite rate limiting.

    Each entry in `players` should be a dict with keys: player_id, full_name,
    and optional birth_year. Returns a dict mapping player_id -> (pid_or_None, status).

    If we see `stop_on_rate_limit_after` consecutive rate_limited responses we
    bail out of the run so we don't keep hammering HockeyDB. Remaining players
    will be picked up on the next scheduled run.
    """
    results = {}
    total = len(players)
    consecutive_rate_limited = 0
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    ) as client:
        for i, p in enumerate(players):
            pid, status = _search_once(client, p["full_name"], p.get("birth_year"))
            results[p["player_id"]] = (pid, status)

            if status == STATUS_RATE_LIMITED:
                consecutive_rate_limited += 1
                if consecutive_rate_limited >= stop_on_rate_limit_after:
                    logger.warning(
                        f"Aborting HockeyDB run after {consecutive_rate_limited} "
                        f"consecutive rate-limited responses ({i + 1}/{total} processed)"
                    )
                    break
            else:
                consecutive_rate_limited = 0

            if progress_callback:
                progress_callback(i + 1, total)
            if i + 1 < total and delay_seconds > 0:
                time.sleep(delay_seconds)
    return results
