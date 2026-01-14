"""FastAPI application for Edge Report."""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend import database
from backend.models import (
    Player, PlayerStats, PlayerEdgeStats,
    PlayerResponse, PlayersResponse, HealthResponse, RefreshResponse,
    TeamsResponse, DivisionsResponse
)
from backend.fetcher import refresh_data

# API key for protected endpoints
API_REFRESH_KEY = os.environ.get("API_REFRESH_KEY", "dev-key-change-me")

app = FastAPI(
    title="Edge Report API",
    description="NHL Edge stats in a comprehensive, sortable format",
    version="2.0.0"
)

# Static files path
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def db_row_to_player(row: dict) -> Player:
    """Convert database row to Player model."""
    stats = None
    if row.get("games_played") is not None:
        stats = PlayerStats(
            games_played=row.get("games_played"),
            avg_toi=round(row["avg_toi"], 1) if row.get("avg_toi") else None,
            goals=row.get("goals"),
            assists=row.get("assists"),
            points=row.get("points"),
            plus_minus=row.get("plus_minus"),
            hits=row.get("hits"),
            blocks=row.get("blocks"),
            pim=row.get("pim"),
            faceoff_win_pct=round(row["faceoff_win_pct"] * 100, 1) if row.get("faceoff_win_pct") else None,
            shots=row.get("shots"),
            shots_per_60=round(row["shots_per_60"], 1) if row.get("shots_per_60") else None,
            p60=round(row["p60"], 2) if row.get("p60") else None,
            p60_percentile=row.get("p60_percentile")
        )

    edge_stats = None
    if row.get("top_speed_mph") is not None or row.get("bursts_20_plus") is not None:
        edge_stats = PlayerEdgeStats(
            top_speed_mph=round(row["top_speed_mph"], 1) if row.get("top_speed_mph") else None,
            top_speed_percentile=row.get("top_speed_percentile"),
            bursts_20_plus=row.get("bursts_20_plus"),
            bursts_20_percentile=row.get("bursts_20_percentile"),
            bursts_22_plus=row.get("bursts_22_plus"),
            bursts_22_percentile=row.get("bursts_22_percentile"),
            distance_per_game_miles=round(row["distance_per_game_miles"], 2) if row.get("distance_per_game_miles") else None,
            distance_percentile=row.get("distance_percentile"),
            off_zone_time_pct=round(row["off_zone_time_pct"], 1) if row.get("off_zone_time_pct") else None,
            off_zone_percentile=row.get("off_zone_percentile"),
            def_zone_time_pct=round(row["def_zone_time_pct"], 1) if row.get("def_zone_time_pct") else None,
            def_zone_percentile=row.get("def_zone_percentile"),
            neu_zone_time_pct=round(row["neu_zone_time_pct"], 1) if row.get("neu_zone_time_pct") else None,
            zone_starts_off_pct=round(row["zone_starts_off_pct"], 1) if row.get("zone_starts_off_pct") else None,
            zone_starts_percentile=row.get("zone_starts_percentile"),
            top_shot_speed_mph=round(row["top_shot_speed_mph"], 1) if row.get("top_shot_speed_mph") else None,
            shot_speed_percentile=row.get("shot_speed_percentile"),
            shots_percentile=row.get("shots_percentile")
        )

    return Player(
        player_id=row["player_id"],
        name=row["name"],
        position=row["position"],
        jersey_number=row.get("jersey_number"),
        team_abbr=row.get("team_abbr"),
        team_name=row.get("team_name"),
        division=row.get("division"),
        conference=row.get("conference"),
        stats=stats,
        edge_stats=edge_stats
    )


@app.get("/api/players", response_model=PlayersResponse)
async def get_players(
    team: Optional[str] = Query(None, description="Team abbreviation (e.g., WSH, PIT)"),
    division: Optional[str] = Query(None, description="Division name (Metropolitan, Atlantic, Central, Pacific)"),
    conference: Optional[str] = Query(None, description="Conference name (Eastern, Western)")
):
    """
    Get all skaters with full stats and edge stats.

    Optional filters:
    - team: Filter by team abbreviation (e.g., WSH for Capitals)
    - division: Filter by division (Metropolitan, Atlantic, Central, Pacific)
    - conference: Filter by conference (Eastern, Western)

    If no filters provided, returns all league players.
    """
    rows = database.get_players_with_stats(
        team_abbr=team,
        division=division,
        conference=conference
    )
    players = [db_row_to_player(row) for row in rows]
    last_updated = database.get_last_updated()

    return PlayersResponse(
        players=players,
        last_updated=last_updated,
        count=len(players)
    )


@app.get("/api/players/{player_id}", response_model=PlayerResponse)
async def get_player(player_id: int):
    """Get a single player with all stats."""
    row = database.get_player_by_id(player_id)
    if not row:
        raise HTTPException(status_code=404, detail="Player not found")

    player = db_row_to_player(row)
    last_updated = database.get_last_updated()

    return PlayerResponse(
        player=player,
        last_updated=last_updated
    )


@app.get("/api/teams", response_model=TeamsResponse)
async def get_teams():
    """Get list of all NHL teams with their divisions and conferences."""
    teams = database.get_teams_list()
    return TeamsResponse(teams=teams)


@app.get("/api/divisions", response_model=DivisionsResponse)
async def get_divisions():
    """Get list of all divisions grouped by conference."""
    divisions = database.get_divisions_list()
    return DivisionsResponse(divisions=divisions)


@app.get("/api/goalies")
async def get_goalies(
    team: Optional[str] = Query(None, description="Team abbreviation (e.g., WSH, PIT)"),
    division: Optional[str] = Query(None, description="Division name (Metropolitan, Atlantic, Central, Pacific)"),
    conference: Optional[str] = Query(None, description="Conference name (Eastern, Western)")
):
    """
    Get all goalies with stats.

    Optional filters:
    - team: Filter by team abbreviation (e.g., WSH for Capitals)
    - division: Filter by division (Metropolitan, Atlantic, Central, Pacific)
    - conference: Filter by conference (Eastern, Western)

    If no filters provided, returns all league goalies.
    """
    rows = database.get_goalies_with_stats(
        team_abbr=team,
        division=division,
        conference=conference
    )

    # Format goalie data for frontend
    goalies = []
    for row in rows:
        goalie = {
            "player_id": row["player_id"],
            "name": row["name"],
            "jersey_number": row.get("jersey_number"),
            "team_abbr": row.get("team_abbr"),
            "team_name": row.get("team_name"),
            "division": row.get("division"),
            "conference": row.get("conference"),
            "games_played": row.get("games_played"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "ot_losses": row.get("ot_losses"),
            "shutouts": row.get("shutouts"),
            "goals_against_avg": round(row["goals_against_avg"], 2) if row.get("goals_against_avg") else None,
            "save_pct": round(row["save_pct"] * 100, 1) if row.get("save_pct") else None,
            "high_danger_save_pct": round(row["high_danger_save_pct"] * 100, 1) if row.get("high_danger_save_pct") else None,
            "gaa_percentile": row.get("gaa_percentile"),
            "save_pct_percentile": row.get("save_pct_percentile"),
            "hdsv_percentile": row.get("hdsv_percentile"),
        }
        goalies.append(goalie)

    last_updated = database.get_last_updated()

    return {
        "goalies": goalies,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "count": len(goalies)
    }


@app.get("/api/goalies/{player_id}")
async def get_goalie(player_id: int):
    """Get a single goalie with all stats."""
    row = database.get_goalie_by_id(player_id)
    if not row:
        raise HTTPException(status_code=404, detail="Goalie not found")

    goalie = {
        "player_id": row["player_id"],
        "name": row["name"],
        "jersey_number": row.get("jersey_number"),
        "team_abbr": row.get("team_abbr"),
        "team_name": row.get("team_name"),
        "division": row.get("division"),
        "conference": row.get("conference"),
        "games_played": row.get("games_played"),
        "wins": row.get("wins"),
        "losses": row.get("losses"),
        "ot_losses": row.get("ot_losses"),
        "shutouts": row.get("shutouts"),
        "goals_against_avg": round(row["goals_against_avg"], 2) if row.get("goals_against_avg") else None,
        "save_pct": round(row["save_pct"] * 100, 1) if row.get("save_pct") else None,
        "high_danger_save_pct": round(row["high_danger_save_pct"] * 100, 1) if row.get("high_danger_save_pct") else None,
        "gaa_percentile": row.get("gaa_percentile"),
        "save_pct_percentile": row.get("save_pct_percentile"),
        "hdsv_percentile": row.get("hdsv_percentile"),
    }
    last_updated = database.get_last_updated()

    return {
        "goalie": goalie,
        "last_updated": last_updated.isoformat() if last_updated else None
    }


@app.get("/api/team-speed/{team_abbr}")
async def get_team_speed(team_abbr: str):
    """
    Get team speed stats with league ranking.

    Returns TOI-weighted average top speed, average bursts/game,
    and the team's league rank.
    """
    # Get all teams for ranking
    all_teams = database.get_all_teams_speed_stats()

    # Find the requested team
    team_stats = None
    for team in all_teams:
        if team["team_abbr"] == team_abbr.upper():
            team_stats = team
            break

    if not team_stats:
        raise HTTPException(status_code=404, detail="Team speed data not found")

    return {
        "team_abbr": team_stats["team_abbr"],
        "team_name": team_stats["team_name"],
        "weighted_avg_speed": team_stats["weighted_avg_speed"],
        "avg_bursts_per_game": team_stats["avg_bursts_per_game"],
        "rank": team_stats["rank"],
        "total_teams": len(all_teams),
        "player_count": team_stats["player_count"]
    }


@app.get("/api/team-speed")
async def get_all_team_speeds():
    """Get speed stats for all teams ranked by weighted average speed."""
    all_teams = database.get_all_teams_speed_stats()
    return {
        "teams": all_teams,
        "count": len(all_teams)
    }


@app.get("/api/team-stats")
async def get_team_stats(
    division: Optional[str] = Query(None, description="Division name (Metropolitan, Atlantic, Central, Pacific)"),
    conference: Optional[str] = Query(None, description="Conference name (Eastern, Western)")
):
    """
    Get all teams with full stats for the Teams view.

    Optional filters:
    - division: Filter by division (Metropolitan, Atlantic, Central, Pacific)
    - conference: Filter by conference (Eastern, Western)

    If no filters provided, returns all 32 teams.
    """
    rows = database.get_all_team_stats(
        division=division,
        conference=conference
    )

    # Format team data for frontend
    teams = []
    for row in rows:
        team = {
            "team_abbr": row.get("team_abbr"),
            "team_name": row.get("team_name"),
            "division": row.get("division"),
            "conference": row.get("conference"),
            "games_played": row.get("games_played"),
            "wins": row.get("wins"),
            "losses": row.get("losses"),
            "ot_losses": row.get("ot_losses"),
            "points": row.get("points"),
            "goals_for": row.get("goals_for"),
            "goals_against": row.get("goals_against"),
            "goal_diff": row.get("goal_diff"),
            "pp_pct": row.get("pp_pct"),
            "pk_pct": row.get("pk_pct"),
            "weighted_avg_speed": row.get("weighted_avg_speed"),
            "weighted_avg_shot_speed": row.get("weighted_avg_shot_speed"),
            "avg_bursts_per_game": row.get("avg_bursts_per_game"),
            "total_hits": row.get("total_hits"),
            "total_blocks": row.get("total_blocks"),
            "points_percentile": row.get("points_percentile"),
            "goal_diff_percentile": row.get("goal_diff_percentile"),
            "pp_percentile": row.get("pp_percentile"),
            "pk_percentile": row.get("pk_percentile"),
            "speed_percentile": row.get("speed_percentile"),
            "shot_speed_percentile": row.get("shot_speed_percentile"),
            "bursts_percentile": row.get("bursts_percentile"),
            "hits_percentile": row.get("hits_percentile"),
            "blocks_percentile": row.get("blocks_percentile"),
        }
        teams.append(team)

    last_updated = database.get_last_updated()

    return {
        "teams": teams,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "count": len(teams)
    }


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    rows = database.get_players_with_stats()
    last_updated = database.get_last_updated()

    return HealthResponse(
        status="healthy",
        last_updated=last_updated,
        player_count=len(rows)
    )


@app.get("/api/refresh", response_model=RefreshResponse)
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None)
):
    """Trigger a manual data refresh. Protected by API key."""
    if x_api_key != API_REFRESH_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Run refresh in background
    background_tasks.add_task(refresh_data)

    return RefreshResponse(
        status="started",
        message="Data refresh started in background",
        players_updated=0
    )


@app.get("/api/refresh/sync", response_model=RefreshResponse)
async def trigger_refresh_sync(x_api_key: str = Header(None)):
    """Trigger a synchronous data refresh. Protected by API key."""
    if x_api_key != API_REFRESH_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    players_updated = refresh_data()

    return RefreshResponse(
        status="completed",
        message="Data refresh completed",
        players_updated=players_updated
    )


# Serve frontend static files
@app.get("/")
async def serve_index():
    """Serve the main index.html."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend not found")


@app.get("/{filename:path}")
async def serve_static(filename: str):
    """Serve static files from frontend directory."""
    # Skip API routes
    if filename.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    file_path = FRONTEND_DIR / filename
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)

    # Fall back to index.html for SPA routing
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
