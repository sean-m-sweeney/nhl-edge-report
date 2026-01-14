"""NHL API data fetching for Caps Edge - League Edition."""

import logging
import asyncio
from datetime import datetime
from typing import Optional
import httpx
from nhlpy import NHLClient
from nhlpy.api.query.builder import QueryBuilder
from nhlpy.api.query.filters.game_type import GameTypeQuery
from nhlpy.api.query.filters.season import SeasonQuery

from backend import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NHL Edge API base URL
NHL_EDGE_BASE_URL = "https://api.nhle.com/stats/rest/en"

# Concurrency settings for parallel requests
MAX_CONCURRENT_REQUESTS = 10  # Number of parallel requests
REQUEST_DELAY = 0.1  # Small delay between batches to be respectful

# Minimum games played to be included
MIN_GAMES_PLAYED = 10

# Current season
CURRENT_SEASON = "20252026"


def get_current_season() -> str:
    """Get the current NHL season string."""
    now = datetime.now()
    # NHL season starts in October
    if now.month >= 10:
        return f"{now.year}{now.year + 1}"
    else:
        return f"{now.year - 1}{now.year}"


def calculate_percentile(value: float, sorted_values: list) -> Optional[int]:
    """
    Calculate percentile ranking for a value within a sorted list.

    Returns percentile as integer 0-100.
    """
    if not sorted_values or value is None:
        return None

    # Count how many values are below this value
    count_below = sum(1 for v in sorted_values if v < value)
    percentile = (count_below / len(sorted_values)) * 100
    return int(round(percentile))


def fetch_team_standings(client: NHLClient) -> dict:
    """
    Fetch current standings for all teams.

    Returns:
        Dict mapping team_abbr to standings dict with W/L/OT/Pts/GF/GA
    """
    logger.info("Fetching team standings...")

    try:
        standings_data = client.standings.league_standings()
        if not standings_data or "standings" not in standings_data:
            logger.error("No standings data returned")
            return {}

        standings = {}
        for team in standings_data["standings"]:
            # Get team abbreviation (nested in dict)
            team_abbr = team.get("teamAbbrev", {}).get("default", "")
            if not team_abbr:
                continue

            standings[team_abbr] = {
                "games_played": team.get("gamesPlayed"),
                "wins": team.get("wins"),
                "losses": team.get("losses"),
                "ot_losses": team.get("otLosses"),
                "points": team.get("points"),
                "goals_for": team.get("goalFor"),
                "goals_against": team.get("goalAgainst"),
                "goal_diff": team.get("goalDifferential"),
            }

        logger.info(f"Fetched standings for {len(standings)} teams")
        return standings

    except Exception as e:
        logger.error(f"Error fetching team standings: {e}")
        return {}


def fetch_team_special_teams(client: NHLClient) -> dict:
    """
    Fetch PP% and PK% for all teams.

    Returns:
        Dict mapping team_abbr to special teams stats
    """
    logger.info("Fetching team special teams stats...")
    season = get_current_season()

    # Team name aliases for NHL API variations
    TEAM_NAME_ALIASES = {
        "Montréal Canadiens": "Montreal Canadiens",
        "Utah Mammoth": "Utah Hockey Club",
    }

    try:
        summary = client.stats.team_summary(start_season=season, end_season=season)
        if not summary:
            logger.error("No team summary data returned")
            return {}

        special_teams = {}
        for team in summary:
            team_name = team.get("teamFullName", "")

            # Normalize team name using aliases
            normalized_name = TEAM_NAME_ALIASES.get(team_name, team_name)

            # Map team name to abbreviation using our NHL_TEAMS dict
            team_abbr = None
            for abbr, info in database.NHL_TEAMS.items():
                if info["name"] == normalized_name:
                    team_abbr = abbr
                    break

            if not team_abbr:
                logger.warning(f"Unknown team: {team_name}")
                continue

            # PP% and PK% are returned as decimals (0.168 = 16.8%)
            pp_pct = team.get("powerPlayPct")
            pk_pct = team.get("penaltyKillPct")

            special_teams[team_abbr] = {
                "pp_pct": round(pp_pct * 100, 1) if pp_pct else None,
                "pk_pct": round(pk_pct * 100, 1) if pk_pct else None,
            }

        logger.info(f"Fetched special teams for {len(special_teams)} teams")
        return special_teams

    except Exception as e:
        logger.error(f"Error fetching team special teams: {e}")
        return {}


def refresh_team_stats(client: NHLClient):
    """
    Refresh all team stats: standings, special teams, and Edge aggregates.
    """
    logger.info("Refreshing team stats...")

    # 1. Fetch standings (W/L/OT/Pts/GF/GA)
    standings = fetch_team_standings(client)

    # 2. Fetch special teams (PP%/PK%)
    special_teams = fetch_team_special_teams(client)

    # 3. Calculate Edge aggregates from existing player data
    edge_aggregates = {}
    for team_abbr in database.NHL_TEAMS.keys():
        edge = database.get_team_edge_aggregates(team_abbr)
        if edge:
            edge_aggregates[team_abbr] = edge

    logger.info(f"Calculated Edge aggregates for {len(edge_aggregates)} teams")

    # 4. Merge all stats and save
    all_team_stats = []
    for team_abbr in database.NHL_TEAMS.keys():
        team_stats = {
            **standings.get(team_abbr, {}),
            **special_teams.get(team_abbr, {}),
            **edge_aggregates.get(team_abbr, {}),
        }
        all_team_stats.append({"team_abbr": team_abbr, **team_stats})

    # 5. Calculate percentiles across all teams
    # Collect values for each metric
    all_points = [t.get("points") for t in all_team_stats if t.get("points") is not None]
    all_goal_diff = [t.get("goal_diff") for t in all_team_stats if t.get("goal_diff") is not None]
    all_pp = [t.get("pp_pct") for t in all_team_stats if t.get("pp_pct") is not None]
    all_pk = [t.get("pk_pct") for t in all_team_stats if t.get("pk_pct") is not None]
    all_speed = [t.get("weighted_avg_speed") for t in all_team_stats if t.get("weighted_avg_speed") is not None]
    all_shot_speed = [t.get("weighted_avg_shot_speed") for t in all_team_stats if t.get("weighted_avg_shot_speed") is not None]
    all_bursts = [t.get("avg_bursts_per_game") for t in all_team_stats if t.get("avg_bursts_per_game") is not None]
    all_hits = [t.get("total_hits") for t in all_team_stats if t.get("total_hits") is not None]
    all_blocks = [t.get("total_blocks") for t in all_team_stats if t.get("total_blocks") is not None]

    # Sort for percentile calculation
    all_points.sort()
    all_goal_diff.sort()
    all_pp.sort()
    all_pk.sort()
    all_speed.sort()
    all_shot_speed.sort()
    all_bursts.sort()
    all_hits.sort()
    all_blocks.sort()

    # 6. Add percentiles and save each team
    for team_stats in all_team_stats:
        if team_stats.get("points") is not None:
            team_stats["points_percentile"] = calculate_percentile(team_stats["points"], all_points)
        if team_stats.get("goal_diff") is not None:
            team_stats["goal_diff_percentile"] = calculate_percentile(team_stats["goal_diff"], all_goal_diff)
        if team_stats.get("pp_pct") is not None:
            team_stats["pp_percentile"] = calculate_percentile(team_stats["pp_pct"], all_pp)
        if team_stats.get("pk_pct") is not None:
            team_stats["pk_percentile"] = calculate_percentile(team_stats["pk_pct"], all_pk)
        if team_stats.get("weighted_avg_speed") is not None:
            team_stats["speed_percentile"] = calculate_percentile(team_stats["weighted_avg_speed"], all_speed)
        if team_stats.get("weighted_avg_shot_speed") is not None:
            team_stats["shot_speed_percentile"] = calculate_percentile(team_stats["weighted_avg_shot_speed"], all_shot_speed)
        if team_stats.get("avg_bursts_per_game") is not None:
            team_stats["bursts_percentile"] = calculate_percentile(team_stats["avg_bursts_per_game"], all_bursts)
        if team_stats.get("total_hits") is not None:
            team_stats["hits_percentile"] = calculate_percentile(team_stats["total_hits"], all_hits)
        if team_stats.get("total_blocks") is not None:
            team_stats["blocks_percentile"] = calculate_percentile(team_stats["total_blocks"], all_blocks)

        database.upsert_team_stats(team_stats["team_abbr"], team_stats)

    logger.info(f"Saved stats for {len(all_team_stats)} teams")


def fetch_all_league_skaters(client: NHLClient) -> list:
    """
    Fetch all NHL skaters with their team info.

    Returns:
        List of player dicts with id, name, position, team_abbr, jersey_number
    """
    logger.info("Fetching all league skaters...")
    season = get_current_season()

    filters = [
        SeasonQuery(season_start=season, season_end=season),
        GameTypeQuery(game_type="2"),
    ]

    qb = QueryBuilder()
    query_ctx = qb.build(filters=filters)

    try:
        # Paginate through all skaters
        all_skaters = []
        for start in range(0, 1500, 100):
            result = client.stats.skater_stats_with_query_context(
                query_context=query_ctx,
                report_type="summary",
                limit=100,
                start=start
            )
            batch = result.get("data", [])
            if not batch:
                break
            all_skaters.extend(batch)
            logger.info(f"Fetched skater batch: {len(batch)} players (offset {start})")

    except Exception as e:
        logger.error(f"Error fetching league skaters: {e}")
        return []

    players = []
    for skater in all_skaters:
        games_played = skater.get("gamesPlayed", 0)

        # Get position (skip goalies)
        position = skater.get("positionCode", "")
        if position == "G":
            continue

        team_abbr = skater.get("teamAbbrevs", "")
        # If player played for multiple teams, get the most recent one
        if "," in team_abbr:
            team_abbr = team_abbr.split(",")[-1].strip()

        players.append({
            "player_id": skater.get("playerId"),
            "name": f"{skater.get('skaterFullName', '')}",
            "position": position,
            "team_abbr": team_abbr,
            "jersey_number": None  # Not in summary stats, will fetch from roster if needed
        })

    logger.info(f"Found {len(players)} qualified skaters across the league")
    return players


def fetch_team_rosters(client: NHLClient, team_abbrs: list) -> dict:
    """
    Fetch jersey numbers from team rosters.

    Returns:
        Dict mapping player_id to jersey_number
    """
    logger.info(f"Fetching roster details for {len(team_abbrs)} teams...")
    season = get_current_season()

    jersey_map = {}
    for team_abbr in team_abbrs:
        try:
            roster = client.teams.team_roster(team_abbr=team_abbr, season=season)
            for group in ["forwards", "defensemen"]:
                for player in roster.get(group, []):
                    jersey_map[player["id"]] = player.get("sweaterNumber")
        except Exception as e:
            logger.warning(f"Error fetching roster for {team_abbr}: {e}")
            continue

    logger.info(f"Got jersey numbers for {len(jersey_map)} players")
    return jersey_map


def fetch_traditional_stats(client: NHLClient) -> dict:
    """
    Fetch traditional stats for all league skaters.

    Returns:
        Dict mapping player_id to stats dict
    """
    logger.info("Fetching traditional stats for all skaters...")
    season = get_current_season()

    filters = [
        SeasonQuery(season_start=season, season_end=season),
        GameTypeQuery(game_type="2"),
    ]
    qb = QueryBuilder()
    query_ctx = qb.build(filters=filters)

    try:
        # Paginate through all summary stats
        all_summary = []
        for start in range(0, 1500, 100):
            result = client.stats.skater_stats_with_query_context(
                query_context=query_ctx,
                report_type="summary",
                limit=100,
                start=start
            )
            batch = result.get("data", [])
            if not batch:
                break
            all_summary.extend(batch)

        summary_data = {p["playerId"]: p for p in all_summary}
        logger.info(f"Total summary stats: {len(summary_data)} players")

        # Paginate through realtime stats (hits, blocks, etc.)
        all_realtime = []
        for start in range(0, 1500, 100):
            result = client.stats.skater_stats_with_query_context(
                query_context=query_ctx,
                report_type="realtime",
                limit=100,
                start=start
            )
            batch = result.get("data", [])
            if not batch:
                break
            all_realtime.extend(batch)

        realtime_data = {p["playerId"]: p for p in all_realtime}
        logger.info(f"Total realtime stats: {len(realtime_data)} players")

    except Exception as e:
        logger.error(f"Error fetching traditional stats: {e}")
        return {}

    stats = {}
    for player_id, summary in summary_data.items():
        realtime = realtime_data.get(player_id, {})

        # TOI is in seconds, convert to minutes
        toi_seconds = summary.get("timeOnIcePerGame", 0)
        avg_toi = toi_seconds / 60 if toi_seconds else None

        # Calculate shots per 60 and P/60
        games_played = summary.get("gamesPlayed", 0)
        shots = summary.get("shots", 0)
        points = summary.get("points", 0)
        shots_per_60 = None
        p60 = None
        toi_per_game = avg_toi  # Already in minutes

        if games_played > 0 and avg_toi and avg_toi > 0:
            minutes_played = games_played * avg_toi
            if minutes_played > 0:
                shots_per_60 = round((shots / minutes_played) * 60, 2)
                p60 = round((points / minutes_played) * 60, 2)

        stats[player_id] = {
            "games_played": games_played,
            "avg_toi": avg_toi,
            "goals": summary.get("goals"),
            "assists": summary.get("assists"),
            "points": points,
            "plus_minus": summary.get("plusMinus"),
            "hits": realtime.get("hits"),
            "blocks": realtime.get("blockedShots"),
            "pim": summary.get("penaltyMinutes"),
            "faceoff_win_pct": summary.get("faceoffWinPct"),
            "shots": shots,
            "shots_per_60": shots_per_60,
            "p60": p60,
            "toi_per_game": toi_per_game
        }

    logger.info(f"Got traditional stats for {len(stats)} players")
    return stats


def fetch_all_league_goalies(client: NHLClient) -> list:
    """
    Fetch all NHL goalies with their stats.

    Returns:
        List of goalie dicts with id, name, team_abbr, and basic stats
    """
    logger.info("Fetching all league goalies...")
    season = get_current_season()

    try:
        # Paginate through all goalies
        all_goalies = []
        for start in range(0, 200, 100):
            batch = client.stats.goalie_stats_summary(
                start_season=season,
                end_season=season,
                stats_type="summary",
                game_type_id=2,
                limit=100,
                start=start
            )
            if not batch:
                break
            all_goalies.extend(batch)
            logger.info(f"Fetched goalie batch: {len(batch)} goalies (offset {start})")

    except Exception as e:
        logger.error(f"Error fetching league goalies: {e}")
        return []

    goalies = []
    for goalie in all_goalies:
        games_played = goalie.get("gamesPlayed", 0)
        if games_played < MIN_GAMES_PLAYED:
            continue

        team_abbr = goalie.get("teamAbbrevs", "")
        # If goalie played for multiple teams, get the most recent one
        if "," in team_abbr:
            team_abbr = team_abbr.split(",")[-1].strip()

        goalies.append({
            "player_id": goalie.get("playerId"),
            "name": goalie.get("goalieFullName", ""),
            "team_abbr": team_abbr,
            "jersey_number": None,
            "games_played": games_played,
            "wins": goalie.get("wins"),
            "losses": goalie.get("losses"),
            "ot_losses": goalie.get("otLosses"),
            "shutouts": goalie.get("shutouts"),
            "goals_against_avg": goalie.get("goalsAgainstAverage"),
            "save_pct": goalie.get("savePct"),
        })

    logger.info(f"Found {len(goalies)} qualified goalies across the league")
    return goalies


def fetch_goalie_edge_stats(client: NHLClient, player_id: int) -> Optional[dict]:
    """
    Fetch Edge stats for a single goalie (high danger save %, jersey number).

    Returns:
        Dict with goalie Edge stats or None if not available
    """
    try:
        detail = client.edge.goalie_detail(player_id=str(player_id))
    except Exception as e:
        logger.warning(f"Error fetching Edge stats for goalie {player_id}: {e}")
        return None

    if not detail:
        return None

    # Extract jersey number from player info
    player_info = detail.get("player", {})
    jersey_number = player_info.get("sweaterNumber")

    # Extract high danger save percentage from shotLocationSummary
    # Look for the 'high' location code which represents high-danger shots
    high_danger_save_pct = None
    shot_locations = detail.get("shotLocationSummary", [])
    for location in shot_locations:
        if location.get("locationCode") == "high":
            high_danger_save_pct = location.get("savePctg")
            break

    return {
        "high_danger_save_pct": high_danger_save_pct,
        "jersey_number": jersey_number,
    }


def fetch_edge_stats(client: NHLClient, player_id: int) -> Optional[dict]:
    """
    Fetch Edge stats for a single player.

    Returns:
        Dict with Edge stats or None if not available
    """
    try:
        # Get main Edge detail
        detail = client.edge.skater_detail(player_id=str(player_id))

        # Get speed detail for bursts over 22
        speed_detail = client.edge.skater_skating_speed_detail(player_id=str(player_id))

        # Get zone time for zone starts
        zone_detail = client.edge.skater_zone_time(player_id=str(player_id))

    except Exception as e:
        logger.warning(f"Error fetching Edge stats for player {player_id}: {e}")
        return None

    if not detail:
        return None

    # Extract skating speed data
    skating = detail.get("skatingSpeed", {})
    speed_max = skating.get("speedMax", {})
    bursts_20 = skating.get("burstsOver20", {})

    # Extract speed detail for bursts over 22
    speed_details = speed_detail.get("skatingSpeedDetails", {}) if speed_detail else {}
    bursts_22 = speed_details.get("burstsOver22", {})

    # Extract distance
    distance = detail.get("totalDistanceSkated", {})

    # Calculate distance per game
    player_info = detail.get("player", {})
    games_played = player_info.get("gamesPlayed", 1)
    total_distance = distance.get("imperial", 0)
    distance_per_game = total_distance / games_played if games_played > 0 else 0

    # Extract zone time
    zone_time = detail.get("zoneTimeDetails", {})

    # Extract zone starts
    zone_starts = zone_detail.get("zoneStarts", {}) if zone_detail else {}

    # Extract shot speed
    shot_speed = detail.get("topShotSpeed", {})

    # Convert percentiles from decimal (0-1) to int (0-100)
    def to_pct(val):
        if val is None:
            return None
        return int(round(val * 100))

    return {
        "top_speed_mph": speed_max.get("imperial"),
        "top_speed_percentile": to_pct(speed_max.get("percentile")),
        "bursts_20_plus": bursts_20.get("value"),
        "bursts_20_percentile": to_pct(bursts_20.get("percentile")),
        "bursts_22_plus": bursts_22.get("value"),
        "bursts_22_percentile": to_pct(bursts_22.get("percentile")),
        "distance_per_game_miles": round(distance_per_game, 2) if distance_per_game else None,
        "distance_percentile": to_pct(distance.get("percentile")),
        "off_zone_time_pct": round(zone_time.get("offensiveZonePctg", 0) * 100, 1) if zone_time.get("offensiveZonePctg") else None,
        "off_zone_percentile": to_pct(zone_time.get("offensiveZonePercentile")),
        "def_zone_time_pct": round(zone_time.get("defensiveZonePctg", 0) * 100, 1) if zone_time.get("defensiveZonePctg") else None,
        "def_zone_percentile": to_pct(zone_time.get("defensiveZonePercentile")),
        "neu_zone_time_pct": round(zone_time.get("neutralZonePctg", 0) * 100, 1) if zone_time.get("neutralZonePctg") else None,
        "zone_starts_off_pct": round(zone_starts.get("offensiveZoneStartsPctg", 0) * 100, 1) if zone_starts.get("offensiveZoneStartsPctg") else None,
        "zone_starts_percentile": to_pct(zone_starts.get("offensiveZoneStartsPctgPercentile")),
        "top_shot_speed_mph": shot_speed.get("imperial"),
        "shot_speed_percentile": to_pct(shot_speed.get("percentile"))
    }


async def async_fetch_edge_stats(client: httpx.AsyncClient, player_id: int) -> Optional[dict]:
    """
    Async version of fetch_edge_stats using httpx.

    Makes 3 parallel API calls for a single player's Edge data.
    """
    # Build URLs for the 3 Edge endpoints (using correct NHL API paths)
    base_url = "https://api-web.nhle.com/v1"
    detail_url = f"{base_url}/edge/skater-detail/{player_id}/now"
    speed_url = f"{base_url}/edge/skater-skating-speed-detail/{player_id}/now"
    zone_url = f"{base_url}/edge/skater-zone-time/{player_id}/now"

    try:
        # Make all 3 requests in parallel
        detail_resp, speed_resp, zone_resp = await asyncio.gather(
            client.get(detail_url),
            client.get(speed_url),
            client.get(zone_url),
            return_exceptions=True
        )

        # Parse responses (handle errors gracefully)
        detail = detail_resp.json() if not isinstance(detail_resp, Exception) and detail_resp.status_code == 200 else None
        speed_detail = speed_resp.json() if not isinstance(speed_resp, Exception) and speed_resp.status_code == 200 else None
        zone_detail = zone_resp.json() if not isinstance(zone_resp, Exception) and zone_resp.status_code == 200 else None

    except Exception as e:
        logger.warning(f"Error fetching async Edge stats for player {player_id}: {e}")
        return None

    if not detail:
        return None

    # Extract skating speed data
    skating = detail.get("skatingSpeed", {})
    speed_max = skating.get("speedMax", {})
    bursts_20 = skating.get("burstsOver20", {})

    # Extract speed detail for bursts over 22
    speed_details = speed_detail.get("skatingSpeedDetails", {}) if speed_detail else {}
    bursts_22 = speed_details.get("burstsOver22", {})

    # Extract distance
    distance = detail.get("totalDistanceSkated", {})

    # Calculate distance per game
    player_info = detail.get("player", {})
    games_played = player_info.get("gamesPlayed", 1)
    total_distance = distance.get("imperial", 0)
    distance_per_game = total_distance / games_played if games_played > 0 else 0

    # Extract zone time
    zone_time = detail.get("zoneTimeDetails", {})

    # Extract zone starts
    zone_starts = zone_detail.get("zoneStarts", {}) if zone_detail else {}

    # Extract shot speed
    shot_speed = detail.get("topShotSpeed", {})

    # Convert percentiles from decimal (0-1) to int (0-100)
    def to_pct(val):
        if val is None:
            return None
        return int(round(val * 100))

    return {
        "top_speed_mph": speed_max.get("imperial"),
        "top_speed_percentile": to_pct(speed_max.get("percentile")),
        "bursts_20_plus": bursts_20.get("value"),
        "bursts_20_percentile": to_pct(bursts_20.get("percentile")),
        "bursts_22_plus": bursts_22.get("value"),
        "bursts_22_percentile": to_pct(bursts_22.get("percentile")),
        "distance_per_game_miles": round(distance_per_game, 2) if distance_per_game else None,
        "distance_percentile": to_pct(distance.get("percentile")),
        "off_zone_time_pct": round(zone_time.get("offensiveZonePctg", 0) * 100, 1) if zone_time.get("offensiveZonePctg") else None,
        "off_zone_percentile": to_pct(zone_time.get("offensiveZonePercentile")),
        "def_zone_time_pct": round(zone_time.get("defensiveZonePctg", 0) * 100, 1) if zone_time.get("defensiveZonePctg") else None,
        "def_zone_percentile": to_pct(zone_time.get("defensiveZonePercentile")),
        "neu_zone_time_pct": round(zone_time.get("neutralZonePctg", 0) * 100, 1) if zone_time.get("neutralZonePctg") else None,
        "zone_starts_off_pct": round(zone_starts.get("offensiveZoneStartsPctg", 0) * 100, 1) if zone_starts.get("offensiveZoneStartsPctg") else None,
        "zone_starts_percentile": to_pct(zone_starts.get("offensiveZoneStartsPctgPercentile")),
        "top_shot_speed_mph": shot_speed.get("imperial"),
        "shot_speed_percentile": to_pct(shot_speed.get("percentile"))
    }


async def async_fetch_goalie_edge_stats(client: httpx.AsyncClient, player_id: int) -> Optional[dict]:
    """
    Async version of fetch_goalie_edge_stats using httpx.
    """
    url = f"https://api-web.nhle.com/v1/edge/goalie-detail/{player_id}/now"

    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        detail = resp.json()
    except Exception as e:
        logger.warning(f"Error fetching async Edge stats for goalie {player_id}: {e}")
        return None

    if not detail:
        return None

    # Extract jersey number from player info
    player_info = detail.get("player", {})
    jersey_number = player_info.get("sweaterNumber")

    # Extract high danger save percentage from shotLocationSummary
    high_danger_save_pct = None
    shot_locations = detail.get("shotLocationSummary", [])
    for location in shot_locations:
        if location.get("locationCode") == "high":
            high_danger_save_pct = location.get("savePctg")
            break

    return {
        "high_danger_save_pct": high_danger_save_pct,
        "jersey_number": jersey_number,
    }


async def fetch_edge_stats_batch(player_ids: list, progress_callback=None) -> dict:
    """
    Fetch Edge stats for multiple players in parallel batches.

    Args:
        player_ids: List of player IDs to fetch
        progress_callback: Optional callback(completed, total) for progress updates

    Returns:
        Dict mapping player_id to Edge stats
    """
    results = {}
    total = len(player_ids)

    if total == 0:
        return results

    logger.info(f"Fetching Edge stats for {total} players in parallel (batch size: {MAX_CONCURRENT_REQUESTS})")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Process in batches
        for i in range(0, total, MAX_CONCURRENT_REQUESTS):
            batch = player_ids[i:i + MAX_CONCURRENT_REQUESTS]

            # Fetch batch in parallel
            tasks = [async_fetch_edge_stats(client, pid) for pid in batch]
            batch_results = await asyncio.gather(*tasks)

            # Store results
            for pid, result in zip(batch, batch_results):
                if result:
                    results[pid] = result

            # Progress update
            completed = min(i + len(batch), total)
            if progress_callback:
                progress_callback(completed, total)
            elif completed % 50 == 0 or completed == total:
                logger.info(f"Edge stats progress: {completed}/{total} players")

            # Small delay between batches to be respectful
            if i + MAX_CONCURRENT_REQUESTS < total:
                await asyncio.sleep(REQUEST_DELAY)

    return results


async def fetch_goalie_edge_stats_batch(player_ids: list, progress_callback=None) -> dict:
    """
    Fetch Edge stats for multiple goalies in parallel batches.

    Args:
        player_ids: List of goalie player IDs to fetch
        progress_callback: Optional callback(completed, total) for progress updates

    Returns:
        Dict mapping player_id to goalie Edge stats
    """
    results = {}
    total = len(player_ids)

    if total == 0:
        return results

    logger.info(f"Fetching Edge stats for {total} goalies in parallel")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Process in batches
        for i in range(0, total, MAX_CONCURRENT_REQUESTS):
            batch = player_ids[i:i + MAX_CONCURRENT_REQUESTS]

            # Fetch batch in parallel
            tasks = [async_fetch_goalie_edge_stats(client, pid) for pid in batch]
            batch_results = await asyncio.gather(*tasks)

            # Store results
            for pid, result in zip(batch, batch_results):
                if result:
                    results[pid] = result

            # Progress update
            completed = min(i + len(batch), total)
            if progress_callback:
                progress_callback(completed, total)

            # Small delay between batches
            if i + MAX_CONCURRENT_REQUESTS < total:
                await asyncio.sleep(REQUEST_DELAY)

    return results


def refresh_data():
    """
    Main refresh function - fetches all league data and updates database.

    Returns:
        Number of players updated
    """
    logger.info("Starting full league data refresh...")
    client = NHLClient()

    # 1. Get all league skaters with 10+ games
    all_skaters = fetch_all_league_skaters(client)
    if not all_skaters:
        logger.error("Failed to fetch league skaters")
        return 0

    # 2. Get traditional stats for all players
    trad_stats = fetch_traditional_stats(client)

    # 3. Get unique teams and fetch jersey numbers
    unique_teams = list(set(p["team_abbr"] for p in all_skaters if p["team_abbr"]))
    jersey_map = fetch_team_rosters(client, unique_teams)

    # 4. Collect all P/60 and TOI values for percentile calculation
    all_p60 = []
    forward_toi = []
    defensemen_toi = []

    for player in all_skaters:
        player_id = player["player_id"]
        if player_id in trad_stats:
            trad = trad_stats[player_id]
            if trad.get("p60") is not None:
                all_p60.append(trad["p60"])
            if trad.get("toi_per_game") is not None:
                if player["position"] in ['C', 'L', 'R']:
                    forward_toi.append(trad["toi_per_game"])
                elif player["position"] == 'D':
                    defensemen_toi.append(trad["toi_per_game"])

    # Sort for percentile calculation
    all_p60.sort()
    forward_toi.sort()
    defensemen_toi.sort()

    logger.info(f"P/60 samples: {len(all_p60)}, Forward TOI samples: {len(forward_toi)}, D TOI samples: {len(defensemen_toi)}")

    # 5. Save all players to database with percentiles
    logger.info(f"Saving {len(all_skaters)} players to database...")
    for player in all_skaters:
        player_id = player["player_id"]
        # Get jersey number from roster data
        jersey_number = jersey_map.get(player_id, player.get("jersey_number"))

        database.upsert_player(
            player_id=player_id,
            name=player["name"],
            position=player["position"],
            jersey_number=jersey_number,
            team_abbr=player.get("team_abbr")
        )

        # Calculate and add percentiles to traditional stats
        if player_id in trad_stats:
            trad = trad_stats[player_id]

            # P/60 percentile (all skaters)
            if trad.get("p60") is not None:
                trad["p60_percentile"] = calculate_percentile(trad["p60"], all_p60)

            # TOI/G percentile (by position)
            if trad.get("toi_per_game") is not None:
                if player["position"] in ['C', 'L', 'R']:
                    trad["toi_per_game_percentile"] = calculate_percentile(trad["toi_per_game"], forward_toi)
                elif player["position"] == 'D':
                    trad["toi_per_game_percentile"] = calculate_percentile(trad["toi_per_game"], defensemen_toi)

            database.upsert_player_stats(player_id, trad)

    # 6. Fetch Edge stats - with caching and parallel requests
    all_player_ids = [p["player_id"] for p in all_skaters]

    # Check which players need Edge stats update (stale or missing)
    players_needing_update = database.get_players_needing_edge_update(all_player_ids, max_age_hours=6)
    cached_count = len(all_player_ids) - len(players_needing_update)

    if cached_count > 0:
        logger.info(f"Skipping {cached_count} players with fresh Edge stats (< 6 hours old)")

    if players_needing_update:
        logger.info(f"Fetching Edge stats for {len(players_needing_update)} players using parallel requests...")
        # Use async batch fetching for speed
        edge_stats = asyncio.run(fetch_edge_stats_batch(players_needing_update))
        logger.info(f"Fetched Edge stats for {len(edge_stats)} players")
    else:
        logger.info("All Edge stats are fresh, no fetching needed")
        edge_stats = {}

    # 7. Collect values for percentile calculation
    all_shots_per_60 = []
    all_distance_per_game = []
    for player in all_skaters:
        player_id = player["player_id"]
        if player_id in trad_stats:
            shots_per_60 = trad_stats[player_id].get("shots_per_60")
            if shots_per_60 is not None:
                all_shots_per_60.append(shots_per_60)
        if player_id in edge_stats:
            dist_per_game = edge_stats[player_id].get("distance_per_game_miles")
            if dist_per_game is not None:
                all_distance_per_game.append(dist_per_game)
    all_shots_per_60.sort()
    all_distance_per_game.sort()

    logger.info(f"Shots/60 samples: {len(all_shots_per_60)}, Dist/G samples: {len(all_distance_per_game)}")

    # 8. Save Edge stats with calculated percentiles
    players_updated = 0
    for player in all_skaters:
        player_id = player["player_id"]

        if player_id in edge_stats:
            edge = edge_stats[player_id]
            trad = trad_stats.get(player_id, {})

            # Calculate shots percentile
            shots_per_60 = trad.get("shots_per_60")
            if shots_per_60 is not None and all_shots_per_60:
                edge["shots_percentile"] = calculate_percentile(shots_per_60, all_shots_per_60)

            # Calculate distance per game percentile (override NHL's total distance percentile)
            dist_per_game = edge.get("distance_per_game_miles")
            if dist_per_game is not None and all_distance_per_game:
                edge["distance_percentile"] = calculate_percentile(dist_per_game, all_distance_per_game)

            database.upsert_player_edge_stats(player_id, edge)
            players_updated += 1

    # 9. Fetch and save all goalies
    logger.info("Fetching goalie data...")
    all_goalies = fetch_all_league_goalies(client)

    if all_goalies:
        # Collect values for percentile calculation
        all_gaa = []
        all_save_pct = []
        all_hdsv = []

        # First pass: get Edge stats for goalies needing update (with caching)
        all_goalie_ids = [g["player_id"] for g in all_goalies]
        goalies_needing_update = database.get_goalies_needing_edge_update(all_goalie_ids, max_age_hours=6)
        cached_goalie_count = len(all_goalie_ids) - len(goalies_needing_update)

        if cached_goalie_count > 0:
            logger.info(f"Skipping {cached_goalie_count} goalies with fresh Edge stats")

        if goalies_needing_update:
            logger.info(f"Fetching Edge stats for {len(goalies_needing_update)} goalies using parallel requests...")
            goalie_edge_stats = asyncio.run(fetch_goalie_edge_stats_batch(goalies_needing_update))
            logger.info(f"Fetched Edge stats for {len(goalie_edge_stats)} goalies")
        else:
            goalie_edge_stats = {}

        # Apply Edge stats to goalie data
        for goalie in all_goalies:
            player_id = goalie["player_id"]
            if player_id in goalie_edge_stats:
                edge = goalie_edge_stats[player_id]
                if edge.get("high_danger_save_pct"):
                    goalie["high_danger_save_pct"] = edge["high_danger_save_pct"]
                    all_hdsv.append(edge["high_danger_save_pct"])
                if edge.get("jersey_number"):
                    goalie["jersey_number"] = edge["jersey_number"]

            if goalie.get("goals_against_avg") is not None:
                all_gaa.append(goalie["goals_against_avg"])
            if goalie.get("save_pct") is not None:
                all_save_pct.append(goalie["save_pct"])

        # Sort for percentile calculation
        all_gaa.sort()
        all_save_pct.sort()
        all_hdsv.sort()

        logger.info(f"GAA samples: {len(all_gaa)}, SV% samples: {len(all_save_pct)}, HDSV% samples: {len(all_hdsv)}")

        # Second pass: save goalies with percentiles
        goalies_updated = 0
        for goalie in all_goalies:
            stats = {
                "games_played": goalie.get("games_played"),
                "wins": goalie.get("wins"),
                "losses": goalie.get("losses"),
                "ot_losses": goalie.get("ot_losses"),
                "shutouts": goalie.get("shutouts"),
                "goals_against_avg": goalie.get("goals_against_avg"),
                "save_pct": goalie.get("save_pct"),
                "high_danger_save_pct": goalie.get("high_danger_save_pct"),
            }

            # Calculate percentiles
            if stats.get("goals_against_avg") is not None and all_gaa:
                # For GAA, lower is better, so invert the percentile (100 - pct)
                raw_pct = calculate_percentile(stats["goals_against_avg"], all_gaa)
                stats["gaa_percentile"] = (100 - raw_pct) if raw_pct is not None else None
            if stats.get("save_pct") is not None and all_save_pct:
                stats["save_pct_percentile"] = calculate_percentile(stats["save_pct"], all_save_pct)
            if stats.get("high_danger_save_pct") is not None and all_hdsv:
                stats["hdsv_percentile"] = calculate_percentile(stats["high_danger_save_pct"], all_hdsv)

            database.upsert_goalie(
                player_id=goalie["player_id"],
                name=goalie["name"],
                jersey_number=goalie.get("jersey_number"),
                team_abbr=goalie.get("team_abbr"),
                stats=stats
            )
            goalies_updated += 1

        logger.info(f"Updated {goalies_updated} goalies")

    # 10. Refresh team stats (standings + Edge aggregates)
    refresh_team_stats(client)

    # Update timestamp
    database.set_last_updated(datetime.now())
    logger.info(f"Data refresh complete. Updated {players_updated} players with Edge stats.")

    return players_updated


if __name__ == "__main__":
    # Allow running directly for testing
    refresh_data()
