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

    # Goalies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goalies (
            player_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            jersey_number INTEGER,
            team_abbr TEXT,
            team_name TEXT,
            division TEXT,
            conference TEXT,
            games_played INTEGER,
            wins INTEGER,
            losses INTEGER,
            ot_losses INTEGER,
            shutouts INTEGER,
            goals_against_avg REAL,
            save_pct REAL,
            high_danger_save_pct REAL,
            gaa_percentile INTEGER,
            save_pct_percentile INTEGER,
            hdsv_percentile INTEGER,
            updated_at DATETIME
        )
    """)

    # Metadata table for tracking updates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Team stats table for Teams view
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
            team_abbr TEXT PRIMARY KEY,
            team_name TEXT NOT NULL,
            division TEXT,
            conference TEXT,
            games_played INTEGER,
            wins INTEGER,
            losses INTEGER,
            ot_losses INTEGER,
            points INTEGER,
            goals_for INTEGER,
            goals_against INTEGER,
            goal_diff INTEGER,
            pp_pct REAL,
            pk_pct REAL,
            weighted_avg_speed REAL,
            weighted_avg_shot_speed REAL,
            avg_bursts_per_game REAL,
            total_hits INTEGER,
            points_percentile INTEGER,
            goal_diff_percentile INTEGER,
            pp_percentile INTEGER,
            pk_percentile INTEGER,
            speed_percentile INTEGER,
            shot_speed_percentile INTEGER,
            bursts_percentile INTEGER,
            updated_at DATETIME
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
    if "blocks" not in columns:
        cursor.execute("ALTER TABLE player_stats ADD COLUMN blocks INTEGER")

    # Check player_edge_stats columns
    cursor.execute("PRAGMA table_info(player_edge_stats)")
    edge_columns = [col[1] for col in cursor.fetchall()]

    if "shots_percentile" not in edge_columns:
        cursor.execute("ALTER TABLE player_edge_stats ADD COLUMN shots_percentile INTEGER")

    # Drop old tables if they exist (no longer needed)
    cursor.execute("DROP TABLE IF EXISTS position_averages")
    cursor.execute("DROP TABLE IF EXISTS league_stats")

    # Check if goalies table exists (for migrations)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goalies'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS goalies (
                player_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                jersey_number INTEGER,
                team_abbr TEXT,
                team_name TEXT,
                division TEXT,
                conference TEXT,
                games_played INTEGER,
                wins INTEGER,
                losses INTEGER,
                ot_losses INTEGER,
                shutouts INTEGER,
                goals_against_avg REAL,
                save_pct REAL,
                high_danger_save_pct REAL,
                gaa_percentile INTEGER,
                save_pct_percentile INTEGER,
                hdsv_percentile INTEGER,
                updated_at DATETIME
            )
        """)

    # Check if team_stats table exists (for migrations)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='team_stats'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_abbr TEXT PRIMARY KEY,
                team_name TEXT NOT NULL,
                division TEXT,
                conference TEXT,
                games_played INTEGER,
                wins INTEGER,
                losses INTEGER,
                ot_losses INTEGER,
                points INTEGER,
                goals_for INTEGER,
                goals_against INTEGER,
                goal_diff INTEGER,
                pp_pct REAL,
                pk_pct REAL,
                weighted_avg_speed REAL,
                weighted_avg_shot_speed REAL,
                avg_bursts_per_game REAL,
                total_hits INTEGER,
                total_blocks INTEGER,
                points_percentile INTEGER,
                goal_diff_percentile INTEGER,
                pp_percentile INTEGER,
                pk_percentile INTEGER,
                speed_percentile INTEGER,
                shot_speed_percentile INTEGER,
                bursts_percentile INTEGER,
                hits_percentile INTEGER,
                blocks_percentile INTEGER,
                updated_at DATETIME
            )
        """)
    else:
        # Add new columns if they don't exist
        cursor.execute("PRAGMA table_info(team_stats)")
        team_stats_columns = [col[1] for col in cursor.fetchall()]
        if "total_blocks" not in team_stats_columns:
            cursor.execute("ALTER TABLE team_stats ADD COLUMN total_blocks INTEGER")
        if "hits_percentile" not in team_stats_columns:
            cursor.execute("ALTER TABLE team_stats ADD COLUMN hits_percentile INTEGER")
        if "blocks_percentile" not in team_stats_columns:
            cursor.execute("ALTER TABLE team_stats ADD COLUMN blocks_percentile INTEGER")


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
            points, plus_minus, hits, blocks, pim, faceoff_win_pct, shots, shots_per_60,
            p60, p60_percentile, toi_per_game, toi_per_game_percentile
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        stats.get("blocks"),
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


def upsert_goalie(player_id: int, name: str, jersey_number: Optional[int],
                  team_abbr: Optional[str], stats: dict):
    """Insert or update a goalie with all stats."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get team info
    team_info = get_team_info(team_abbr) if team_abbr else {}

    cursor.execute("""
        INSERT OR REPLACE INTO goalies (
            player_id, name, jersey_number, team_abbr, team_name,
            division, conference, games_played, wins, losses, ot_losses,
            shutouts, goals_against_avg, save_pct, high_danger_save_pct,
            gaa_percentile, save_pct_percentile, hdsv_percentile, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        player_id,
        name,
        jersey_number,
        team_abbr,
        team_info.get("name"),
        team_info.get("division"),
        team_info.get("conference"),
        stats.get("games_played"),
        stats.get("wins"),
        stats.get("losses"),
        stats.get("ot_losses"),
        stats.get("shutouts"),
        stats.get("goals_against_avg"),
        stats.get("save_pct"),
        stats.get("high_danger_save_pct"),
        stats.get("gaa_percentile"),
        stats.get("save_pct_percentile"),
        stats.get("hdsv_percentile"),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def clear_all_goalie_data():
    """Clear all goalie data for fresh refresh."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM goalies")
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


def get_league_goalie_gaa() -> list:
    """Get all GAA values for percentile calculation (lower is better)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT goals_against_avg FROM goalies
        WHERE games_played >= 10 AND goals_against_avg IS NOT NULL
        ORDER BY goals_against_avg DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row["goals_against_avg"] for row in rows]


def get_league_goalie_save_pct() -> list:
    """Get all save percentage values for percentile calculation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT save_pct FROM goalies
        WHERE games_played >= 10 AND save_pct IS NOT NULL
        ORDER BY save_pct
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row["save_pct"] for row in rows]


def get_league_goalie_hdsv() -> list:
    """Get all high danger save pct values for percentile calculation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT high_danger_save_pct FROM goalies
        WHERE games_played >= 10 AND high_danger_save_pct IS NOT NULL
        ORDER BY high_danger_save_pct
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row["high_danger_save_pct"] for row in rows]


def get_goalies_with_stats(team_abbr: Optional[str] = None,
                           division: Optional[str] = None,
                           conference: Optional[str] = None) -> list:
    """Get goalies with stats, optionally filtered by team/division/conference."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            player_id, name, jersey_number, team_abbr, team_name,
            division, conference, games_played, wins, losses, ot_losses,
            shutouts, goals_against_avg, save_pct, high_danger_save_pct,
            gaa_percentile, save_pct_percentile, hdsv_percentile
        FROM goalies
        WHERE 1=1
    """

    params = []

    if team_abbr:
        query += " AND team_abbr = ?"
        params.append(team_abbr)
    elif division:
        query += " AND division = ?"
        params.append(division)
    elif conference:
        query += " AND conference = ?"
        params.append(conference)

    query += " ORDER BY wins DESC NULLS LAST"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_goalie_by_id(player_id: int) -> Optional[dict]:
    """Get a single goalie with all stats."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            player_id, name, jersey_number, team_abbr, team_name,
            division, conference, games_played, wins, losses, ot_losses,
            shutouts, goals_against_avg, save_pct, high_danger_save_pct,
            gaa_percentile, save_pct_percentile, hdsv_percentile
        FROM goalies
        WHERE player_id = ?
    """, (player_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_team_speed_stats(team_abbr: str) -> Optional[dict]:
    """
    Calculate TOI-weighted average top speed and average bursts/game for a team.

    Returns dict with:
    - weighted_avg_speed: TOI-weighted average top speed
    - avg_bursts_per_game: Average bursts over 20 mph per game
    - player_count: Number of players with speed data
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get players with speed data and TOI
    cursor.execute("""
        SELECT
            e.top_speed_mph,
            e.bursts_20_plus,
            s.avg_toi,
            s.games_played
        FROM players p
        JOIN player_edge_stats e ON p.player_id = e.player_id
        JOIN player_stats s ON p.player_id = s.player_id
        WHERE p.team_abbr = ?
        AND e.top_speed_mph IS NOT NULL
        AND s.avg_toi IS NOT NULL
        AND s.games_played >= 10
    """, (team_abbr,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    # Calculate TOI-weighted average speed
    total_toi = 0
    weighted_speed_sum = 0
    total_bursts = 0
    total_games = 0

    for row in rows:
        toi = row["avg_toi"] or 0
        speed = row["top_speed_mph"] or 0
        bursts = row["bursts_20_plus"] or 0
        games = row["games_played"] or 0

        total_toi += toi
        weighted_speed_sum += speed * toi
        total_bursts += bursts
        total_games += games

    weighted_avg_speed = weighted_speed_sum / total_toi if total_toi > 0 else 0
    avg_bursts_per_game = total_bursts / total_games if total_games > 0 else 0

    return {
        "weighted_avg_speed": round(weighted_avg_speed, 2),
        "avg_bursts_per_game": round(avg_bursts_per_game, 2),
        "player_count": len(rows)
    }


def get_all_teams_speed_stats() -> list:
    """
    Get speed stats for all teams for ranking purposes.

    Returns list of dicts sorted by weighted_avg_speed descending.
    """
    results = []
    for team_abbr in NHL_TEAMS.keys():
        stats = get_team_speed_stats(team_abbr)
        if stats:
            stats["team_abbr"] = team_abbr
            stats["team_name"] = NHL_TEAMS[team_abbr]["name"]
            results.append(stats)

    # Sort by weighted average speed (descending)
    results.sort(key=lambda x: x["weighted_avg_speed"], reverse=True)

    # Add rank
    for i, team in enumerate(results):
        team["rank"] = i + 1

    return results


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
            s.plus_minus, s.hits, s.blocks, s.pim, s.faceoff_win_pct,
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
            s.plus_minus, s.hits, s.blocks, s.pim, s.faceoff_win_pct,
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


def upsert_team_stats(team_abbr: str, stats: dict):
    """Insert or update team stats."""
    conn = get_connection()
    cursor = conn.cursor()

    team_info = get_team_info(team_abbr)

    cursor.execute("""
        INSERT OR REPLACE INTO team_stats (
            team_abbr, team_name, division, conference,
            games_played, wins, losses, ot_losses, points,
            goals_for, goals_against, goal_diff,
            pp_pct, pk_pct,
            weighted_avg_speed, weighted_avg_shot_speed,
            avg_bursts_per_game, total_hits, total_blocks,
            points_percentile, goal_diff_percentile,
            pp_percentile, pk_percentile,
            speed_percentile, shot_speed_percentile, bursts_percentile,
            hits_percentile, blocks_percentile,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        team_abbr,
        team_info.get("name"),
        team_info.get("division"),
        team_info.get("conference"),
        stats.get("games_played"),
        stats.get("wins"),
        stats.get("losses"),
        stats.get("ot_losses"),
        stats.get("points"),
        stats.get("goals_for"),
        stats.get("goals_against"),
        stats.get("goal_diff"),
        stats.get("pp_pct"),
        stats.get("pk_pct"),
        stats.get("weighted_avg_speed"),
        stats.get("weighted_avg_shot_speed"),
        stats.get("avg_bursts_per_game"),
        stats.get("total_hits"),
        stats.get("total_blocks"),
        stats.get("points_percentile"),
        stats.get("goal_diff_percentile"),
        stats.get("pp_percentile"),
        stats.get("pk_percentile"),
        stats.get("speed_percentile"),
        stats.get("shot_speed_percentile"),
        stats.get("bursts_percentile"),
        stats.get("hits_percentile"),
        stats.get("blocks_percentile"),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def get_all_team_stats(division: Optional[str] = None,
                       conference: Optional[str] = None) -> list:
    """Get all teams with stats, optionally filtered by division/conference."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            team_abbr, team_name, division, conference,
            games_played, wins, losses, ot_losses, points,
            goals_for, goals_against, goal_diff,
            pp_pct, pk_pct,
            weighted_avg_speed, weighted_avg_shot_speed,
            avg_bursts_per_game, total_hits, total_blocks,
            points_percentile, goal_diff_percentile,
            pp_percentile, pk_percentile,
            speed_percentile, shot_speed_percentile, bursts_percentile,
            hits_percentile, blocks_percentile
        FROM team_stats
        WHERE 1=1
    """

    params = []

    if division:
        query += " AND division = ?"
        params.append(division)
    elif conference:
        query += " AND conference = ?"
        params.append(conference)

    query += " ORDER BY points DESC NULLS LAST"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_team_edge_aggregates(team_abbr: str) -> Optional[dict]:
    """
    Calculate TOI-weighted Edge aggregates for a team.

    Returns dict with:
    - weighted_avg_speed: TOI-weighted average top speed
    - weighted_avg_shot_speed: TOI-weighted average shot speed
    - avg_bursts_per_game: Average bursts over 20 mph per game
    - total_hits: Sum of all player hits
    - total_blocks: Sum of all player blocks
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get players with Edge data and TOI
    cursor.execute("""
        SELECT
            e.top_speed_mph,
            e.top_shot_speed_mph,
            e.bursts_20_plus,
            s.avg_toi,
            s.games_played,
            s.hits,
            s.blocks
        FROM players p
        JOIN player_edge_stats e ON p.player_id = e.player_id
        JOIN player_stats s ON p.player_id = s.player_id
        WHERE p.team_abbr = ?
        AND s.avg_toi IS NOT NULL
        AND s.games_played >= 10
    """, (team_abbr,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    # Calculate TOI-weighted averages
    total_toi = 0
    weighted_speed_sum = 0
    weighted_shot_speed_sum = 0
    total_bursts = 0
    total_games = 0
    total_hits = 0
    total_blocks = 0
    speed_toi = 0  # Track TOI only for players with speed data
    shot_speed_toi = 0  # Track TOI only for players with shot speed data

    for row in rows:
        toi = row["avg_toi"] or 0
        speed = row["top_speed_mph"]
        shot_speed = row["top_shot_speed_mph"]
        bursts = row["bursts_20_plus"] or 0
        games = row["games_played"] or 0
        hits = row["hits"] or 0
        blocks = row["blocks"] or 0

        total_toi += toi
        total_bursts += bursts
        total_games += games
        total_hits += hits
        total_blocks += blocks

        if speed is not None:
            weighted_speed_sum += speed * toi
            speed_toi += toi

        if shot_speed is not None:
            weighted_shot_speed_sum += shot_speed * toi
            shot_speed_toi += toi

    weighted_avg_speed = weighted_speed_sum / speed_toi if speed_toi > 0 else None
    weighted_avg_shot_speed = weighted_shot_speed_sum / shot_speed_toi if shot_speed_toi > 0 else None
    avg_bursts_per_game = total_bursts / total_games if total_games > 0 else 0

    return {
        "weighted_avg_speed": round(weighted_avg_speed, 2) if weighted_avg_speed else None,
        "weighted_avg_shot_speed": round(weighted_avg_shot_speed, 2) if weighted_avg_shot_speed else None,
        "avg_bursts_per_game": round(avg_bursts_per_game, 2),
        "total_hits": total_hits,
        "total_blocks": total_blocks
    }


def clear_all_team_stats():
    """Clear all team stats for fresh refresh."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM team_stats")
    conn.commit()
    conn.close()


def get_players_needing_edge_update(player_ids: list, max_age_hours: int = 6) -> list:
    """
    Get list of player IDs that need Edge stats update.

    A player needs an update if:
    - They have no Edge stats record
    - Their Edge stats are older than max_age_hours

    Args:
        player_ids: List of player IDs to check
        max_age_hours: Maximum age of Edge stats before refresh (default 6 hours)

    Returns:
        List of player IDs that need Edge stats refresh
    """
    if not player_ids:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    # Get current Edge stats timestamps
    placeholders = ','.join('?' * len(player_ids))
    cursor.execute(f"""
        SELECT player_id, updated_at
        FROM player_edge_stats
        WHERE player_id IN ({placeholders})
    """, player_ids)

    existing = {row["player_id"]: row["updated_at"] for row in cursor.fetchall()}
    conn.close()

    # Calculate cutoff time
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    needs_update = []
    for player_id in player_ids:
        if player_id not in existing:
            # No Edge stats at all
            needs_update.append(player_id)
        else:
            # Check if stale
            updated_at = datetime.fromisoformat(existing[player_id])
            if updated_at < cutoff:
                needs_update.append(player_id)

    return needs_update


def get_goalies_needing_edge_update(player_ids: list, max_age_hours: int = 6) -> list:
    """
    Get list of goalie IDs that need Edge stats update.

    A goalie needs an update if:
    - They have no updated_at timestamp
    - Their record is older than max_age_hours

    Args:
        player_ids: List of goalie player IDs to check
        max_age_hours: Maximum age before refresh (default 6 hours)

    Returns:
        List of goalie player IDs that need refresh
    """
    if not player_ids:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    # Get current goalie timestamps
    placeholders = ','.join('?' * len(player_ids))
    cursor.execute(f"""
        SELECT player_id, updated_at
        FROM goalies
        WHERE player_id IN ({placeholders})
    """, player_ids)

    existing = {row["player_id"]: row["updated_at"] for row in cursor.fetchall()}
    conn.close()

    # Calculate cutoff time
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    needs_update = []
    for player_id in player_ids:
        if player_id not in existing or existing[player_id] is None:
            # No record or no timestamp
            needs_update.append(player_id)
        else:
            # Check if stale
            updated_at = datetime.fromisoformat(existing[player_id])
            if updated_at < cutoff:
                needs_update.append(player_id)

    return needs_update


# Initialize database on import
init_db()
