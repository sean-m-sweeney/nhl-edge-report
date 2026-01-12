"""Database setup and queries for Caps Edge."""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
import os

# Database path - use /app/data in Docker, local data/ otherwise
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = DATA_DIR / "caps_edge.db"

# NHL Team/Division/Conference mappings
NHL_TEAMS = {
    # Metropolitan Division (Eastern)
    "CAR": {"name": "Carolina Hurricanes", "division": "Metropolitan", "conference": "Eastern"},
    "CBJ": {"name": "Columbus Blue Jackets", "division": "Metropolitan", "conference": "Eastern"},
    "NJD": {"name": "New Jersey Devils", "division": "Metropolitan", "conference": "Eastern"},
    "NYI": {"name": "New York Islanders", "division": "Metropolitan", "conference": "Eastern"},
    "NYR": {"name": "New York Rangers", "division": "Metropolitan", "conference": "Eastern"},
    "PHI": {"name": "Philadelphia Flyers", "division": "Metropolitan", "conference": "Eastern"},
    "PIT": {"name": "Pittsburgh Penguins", "division": "Metropolitan", "conference": "Eastern"},
    "WSH": {"name": "Washington Capitals", "division": "Metropolitan", "conference": "Eastern"},
    # Atlantic Division (Eastern)
    "BOS": {"name": "Boston Bruins", "division": "Atlantic", "conference": "Eastern"},
    "BUF": {"name": "Buffalo Sabres", "division": "Atlantic", "conference": "Eastern"},
    "DET": {"name": "Detroit Red Wings", "division": "Atlantic", "conference": "Eastern"},
    "FLA": {"name": "Florida Panthers", "division": "Atlantic", "conference": "Eastern"},
    "MTL": {"name": "Montreal Canadiens", "division": "Atlantic", "conference": "Eastern"},
    "OTT": {"name": "Ottawa Senators", "division": "Atlantic", "conference": "Eastern"},
    "TBL": {"name": "Tampa Bay Lightning", "division": "Atlantic", "conference": "Eastern"},
    "TOR": {"name": "Toronto Maple Leafs", "division": "Atlantic", "conference": "Eastern"},
    # Central Division (Western)
    "UTA": {"name": "Utah Hockey Club", "division": "Central", "conference": "Western"},
    "CHI": {"name": "Chicago Blackhawks", "division": "Central", "conference": "Western"},
    "COL": {"name": "Colorado Avalanche", "division": "Central", "conference": "Western"},
    "DAL": {"name": "Dallas Stars", "division": "Central", "conference": "Western"},
    "MIN": {"name": "Minnesota Wild", "division": "Central", "conference": "Western"},
    "NSH": {"name": "Nashville Predators", "division": "Central", "conference": "Western"},
    "STL": {"name": "St. Louis Blues", "division": "Central", "conference": "Western"},
    "WPG": {"name": "Winnipeg Jets", "division": "Central", "conference": "Western"},
    # Pacific Division (Western)
    "ANA": {"name": "Anaheim Ducks", "division": "Pacific", "conference": "Western"},
    "CGY": {"name": "Calgary Flames", "division": "Pacific", "conference": "Western"},
    "EDM": {"name": "Edmonton Oilers", "division": "Pacific", "conference": "Western"},
    "LAK": {"name": "Los Angeles Kings", "division": "Pacific", "conference": "Western"},
    "SEA": {"name": "Seattle Kraken", "division": "Pacific", "conference": "Western"},
    "SJS": {"name": "San Jose Sharks", "division": "Pacific", "conference": "Western"},
    "VAN": {"name": "Vancouver Canucks", "division": "Pacific", "conference": "Western"},
    "VGK": {"name": "Vegas Golden Knights", "division": "Pacific", "conference": "Western"},
}


def get_team_info(team_abbr: str) -> dict:
    """Get team info (division, conference) from abbreviation."""
    return NHL_TEAMS.get(team_abbr, {"name": team_abbr, "division": "Unknown", "conference": "Unknown"})


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Players table with team info
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            position TEXT NOT NULL,
            jersey_number INTEGER,
            team_abbr TEXT,
            team_name TEXT,
            division TEXT,
            conference TEXT
        )
    """)

    # Player stats table (traditional stats)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            updated_at DATETIME NOT NULL,
            games_played INTEGER,
            avg_toi REAL,
            goals INTEGER,
            assists INTEGER,
            points INTEGER,
            plus_minus INTEGER,
            hits INTEGER,
            pim INTEGER,
            faceoff_win_pct REAL,
            shots INTEGER,
            shots_per_60 REAL,
            p60 REAL,
            p60_percentile INTEGER,
            toi_per_game REAL,
            toi_per_game_percentile INTEGER,
            FOREIGN KEY (player_id) REFERENCES players(player_id)
        )
    """)

    # Player Edge stats table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_edge_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            updated_at DATETIME NOT NULL,

            -- Skating Speed
            top_speed_mph REAL,
            top_speed_percentile INTEGER,

            -- Bursts
            bursts_20_plus INTEGER,
            bursts_20_percentile INTEGER,
            bursts_22_plus INTEGER,
            bursts_22_percentile INTEGER,

            -- Distance
            distance_per_game_miles REAL,
            distance_percentile INTEGER,

            -- Zone Time
            off_zone_time_pct REAL,
            off_zone_percentile INTEGER,
            def_zone_time_pct REAL,
            def_zone_percentile INTEGER,
            neu_zone_time_pct REAL,

            -- Zone Starts
            zone_starts_off_pct REAL,
            zone_starts_percentile INTEGER,

            -- Shot Speed
            top_shot_speed_mph REAL,
            shot_speed_percentile INTEGER,

            -- Shots percentile (for shots/60)
            shots_percentile INTEGER,

            FOREIGN KEY (player_id) REFERENCES players(player_id)
        )
    """)

    # Metadata table for tracking updates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Run migrations for existing databases
    _run_migrations(cursor)

    conn.commit()
    conn.close()


def _run_migrations(cursor):
    """Run database migrations for schema changes."""
    # Check players table for team columns
    cursor.execute("PRAGMA table_info(players)")
    player_columns = [col[1] for col in cursor.fetchall()]

    if "team_abbr" not in player_columns:
        cursor.execute("ALTER TABLE players ADD COLUMN team_abbr TEXT")
    if "team_name" not in player_columns:
        cursor.execute("ALTER TABLE players ADD COLUMN team_name TEXT")
    if "division" not in player_columns:
        cursor.execute("ALTER TABLE players ADD COLUMN division TEXT")
    if "conference" not in player_columns:
        cursor.execute("ALTER TABLE players ADD COLUMN conference TEXT")

    # Check player_stats for new columns
    cursor.execute("PRAGMA table_info(player_stats)")
    columns = [col[1] for col in cursor.fetchall()]

    if "shots" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN shots INTEGER")
    if "shots_per_60" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN shots_per_60 REAL")
    if "p60" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN p60 REAL")
    if "p60_percentile" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN p60_percentile INTEGER")
    if "toi_per_game" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN toi_per_game REAL")
    if "toi_per_game_percentile" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN toi_per_game_percentile INTEGER")

    # Check player_edge_stats columns
    cursor.execute("PRAGMA table_info(player_edge_stats)")
    edge_columns = [col[1] for col in cursor.fetchall()]

    if "shots_percentile" not in edge_columns:
        cursor.execute("ALTER TABLE player_edge_stats ADD COLUMN shots_percentile INTEGER")

    # Drop old tables if they exist (no longer needed)
    cursor.execute("DROP TABLE IF EXISTS position_averages")
    cursor.execute("DROP TABLE IF EXISTS league_stats")


def get_last_updated() -> Optional[datetime]:
    """Get the last update timestamp."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row["value"])
    return None


def set_last_updated(timestamp: datetime):
    """Set the last update timestamp."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)
    """, (timestamp.isoformat(),))
    conn.commit()
    conn.close()


def upsert_player(player_id: int, name: str, position: str, jersey_number: Optional[int],
                  team_abbr: Optional[str] = None):
    """Insert or update a player."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get team info
    team_info = get_team_info(team_abbr) if team_abbr else {}

    cursor.execute("""
        INSERT OR REPLACE INTO players (player_id, name, position, jersey_number,
                                        team_abbr, team_name, division, conference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        player_id,
        name,
        position,
        jersey_number,
        team_abbr,
        team_info.get("name"),
        team_info.get("division"),
        team_info.get("conference")
    ))
    conn.commit()
    conn.close()


def upsert_player_stats(player_id: int, stats: dict):
    """Insert or update player stats (keeps only latest)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Delete old stats for this player
    cursor.execute("DELETE FROM player_stats WHERE player_id = ?", (player_id,))

    # Insert new stats
    cursor.execute("""
        INSERT INTO player_stats (
            player_id, updated_at, games_played, avg_toi, goals, assists,
            points, plus_minus, hits, pim, faceoff_win_pct, shots, shots_per_60,
            p60, p60_percentile, toi_per_game, toi_per_game_percentile
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        player_id,
        datetime.now().isoformat(),
        stats.get("games_played"),
        stats.get("avg_toi"),
        stats.get("goals"),
        stats.get("assists"),
        stats.get("points"),
        stats.get("plus_minus"),
        stats.get("hits"),
        stats.get("pim"),
        stats.get("faceoff_win_pct"),
        stats.get("shots"),
        stats.get("shots_per_60"),
        stats.get("p60"),
        stats.get("p60_percentile"),
        stats.get("toi_per_game"),
        stats.get("toi_per_game_percentile")
    ))
    conn.commit()
    conn.close()


def upsert_player_edge_stats(player_id: int, stats: dict):
    """Insert or update player Edge stats (keeps only latest)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Delete old stats for this player
    cursor.execute("DELETE FROM player_edge_stats WHERE player_id = ?", (player_id,))

    # Insert new stats
    cursor.execute("""
        INSERT INTO player_edge_stats (
            player_id, updated_at,
            top_speed_mph, top_speed_percentile,
            bursts_20_plus, bursts_20_percentile,
            bursts_22_plus, bursts_22_percentile,
            distance_per_game_miles, distance_percentile,
            off_zone_time_pct, off_zone_percentile,
            def_zone_time_pct, def_zone_percentile,
            neu_zone_time_pct,
            zone_starts_off_pct, zone_starts_percentile,
            top_shot_speed_mph, shot_speed_percentile,
            shots_percentile
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        player_id,
        datetime.now().isoformat(),
        stats.get("top_speed_mph"),
        stats.get("top_speed_percentile"),
        stats.get("bursts_20_plus"),
        stats.get("bursts_20_percentile"),
        stats.get("bursts_22_plus"),
        stats.get("bursts_22_percentile"),
        stats.get("distance_per_game_miles"),
        stats.get("distance_percentile"),
        stats.get("off_zone_time_pct"),
        stats.get("off_zone_percentile"),
        stats.get("def_zone_time_pct"),
        stats.get("def_zone_percentile"),
        stats.get("neu_zone_time_pct"),
        stats.get("zone_starts_off_pct"),
        stats.get("zone_starts_percentile"),
        stats.get("top_shot_speed_mph"),
        stats.get("shot_speed_percentile"),
        stats.get("shots_percentile")
    ))
    conn.commit()
    conn.close()


def clear_all_player_data():
    """Clear all player data for fresh full refresh."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM player_edge_stats")
    cursor.execute("DELETE FROM player_stats")
    cursor.execute("DELETE FROM players")
    conn.commit()
    conn.close()


def get_league_shots_per_60() -> list:
    """Get all shots per 60 for percentile calculation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT shots_per_60 FROM player_stats
        WHERE games_played >= 10 AND shots_per_60 IS NOT NULL
        ORDER BY shots_per_60
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row["shots_per_60"] for row in rows]


def get_league_p60() -> list:
    """Get all P/60 values for percentile calculation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p60 FROM player_stats
        WHERE games_played >= 10 AND p60 IS NOT NULL
        ORDER BY p60
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row["p60"] for row in rows]


def get_league_toi_by_position() -> dict:
    """Get TOI/G values by position (F vs D) for percentile calculation."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get forwards TOI
    cursor.execute("""
        SELECT s.toi_per_game FROM player_stats s
        JOIN players p ON s.player_id = p.player_id
        WHERE s.games_played >= 10 AND s.toi_per_game IS NOT NULL
        AND p.position IN ('C', 'L', 'R')
        ORDER BY s.toi_per_game
    """)
    forwards = [row["toi_per_game"] for row in cursor.fetchall()]

    # Get defensemen TOI
    cursor.execute("""
        SELECT s.toi_per_game FROM player_stats s
        JOIN players p ON s.player_id = p.player_id
        WHERE s.games_played >= 10 AND s.toi_per_game IS NOT NULL
        AND p.position = 'D'
        ORDER BY s.toi_per_game
    """)
    defensemen = [row["toi_per_game"] for row in cursor.fetchall()]

    conn.close()
    return {"F": forwards, "D": defensemen}


def get_teams_list() -> list:
    """Get list of all teams in model format."""
    teams = []
    for abbr, info in NHL_TEAMS.items():
        teams.append({
            "abbr": abbr,
            "name": info["name"],
            "division": info["division"],
            "conference": info["conference"]
        })
    # Sort by conference, division, name
    teams.sort(key=lambda t: (t["conference"], t["division"], t["name"]))
    return teams


def get_divisions_list() -> list:
    """Get list of divisions with teams in model format."""
    divisions = {
        "Metropolitan": {"name": "Metropolitan", "conference": "Eastern", "teams": []},
        "Atlantic": {"name": "Atlantic", "conference": "Eastern", "teams": []},
        "Central": {"name": "Central", "conference": "Western", "teams": []},
        "Pacific": {"name": "Pacific", "conference": "Western", "teams": []},
    }

    for abbr, info in NHL_TEAMS.items():
        div = info["division"]
        if div in divisions:
            divisions[div]["teams"].append(abbr)

    # Sort teams within each division
    for div in divisions.values():
        div["teams"].sort()

    return list(divisions.values())


def get_players_with_stats(team_abbr: Optional[str] = None,
                            division: Optional[str] = None,
                            conference: Optional[str] = None) -> list:
    """Get players with stats, optionally filtered by team/division/conference."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            p.player_id, p.name, p.position, p.jersey_number,
            p.team_abbr, p.team_name, p.division, p.conference,
            s.games_played, s.avg_toi, s.goals, s.assists, s.points,
            s.plus_minus, s.hits, s.pim, s.faceoff_win_pct,
            s.shots, s.shots_per_60,
            s.p60, s.p60_percentile,
            s.toi_per_game, s.toi_per_game_percentile,
            e.top_speed_mph, e.top_speed_percentile,
            e.bursts_20_plus, e.bursts_20_percentile,
            e.bursts_22_plus, e.bursts_22_percentile,
            e.distance_per_game_miles, e.distance_percentile,
            e.off_zone_time_pct, e.off_zone_percentile,
            e.def_zone_time_pct, e.def_zone_percentile,
            e.neu_zone_time_pct,
            e.zone_starts_off_pct, e.zone_starts_percentile,
            e.top_shot_speed_mph, e.shot_speed_percentile,
            e.shots_percentile
        FROM players p
        LEFT JOIN player_stats s ON p.player_id = s.player_id
        LEFT JOIN player_edge_stats e ON p.player_id = e.player_id
        WHERE p.position != 'G'
    """

    params = []

    if team_abbr:
        query += " AND p.team_abbr = ?"
        params.append(team_abbr)
    elif division:
        query += " AND p.division = ?"
        params.append(division)
    elif conference:
        query += " AND p.conference = ?"
        params.append(conference)

    query += " ORDER BY s.points DESC NULLS LAST"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_players_with_stats() -> list:
    """Get all players with their stats and edge stats (legacy compatibility)."""
    return get_players_with_stats()


def get_player_by_id(player_id: int) -> Optional[dict]:
    """Get a single player with all stats."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            p.player_id, p.name, p.position, p.jersey_number,
            p.team_abbr, p.team_name, p.division, p.conference,
            s.games_played, s.avg_toi, s.goals, s.assists, s.points,
            s.plus_minus, s.hits, s.pim, s.faceoff_win_pct,
            s.shots, s.shots_per_60,
            s.p60, s.p60_percentile,
            s.toi_per_game, s.toi_per_game_percentile,
            e.top_speed_mph, e.top_speed_percentile,
            e.bursts_20_plus, e.bursts_20_percentile,
            e.bursts_22_plus, e.bursts_22_percentile,
            e.distance_per_game_miles, e.distance_percentile,
            e.off_zone_time_pct, e.off_zone_percentile,
            e.def_zone_time_pct, e.def_zone_percentile,
            e.neu_zone_time_pct,
            e.zone_starts_off_pct, e.zone_starts_percentile,
            e.top_shot_speed_mph, e.shot_speed_percentile,
            e.shots_percentile
        FROM players p
        LEFT JOIN player_stats s ON p.player_id = s.player_id
        LEFT JOIN player_edge_stats e ON p.player_id = e.player_id
        WHERE p.player_id = ?
    """, (player_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# Initialize database on import
init_db()
