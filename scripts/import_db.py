#!/usr/bin/env python3
"""
Import CSV exports into a fresh PostgreSQL database.

Run from the host:
    docker-compose exec bot python scripts/import_db.py

The script:
  1. Creates all tables if they don't exist (safe for fresh servers)
  2. Loads CSVs in foreign-key order
  3. Resets sequences so IDs are correct
"""

import csv
import os
import sys
import subprocess
from pathlib import Path

CSV_DIR = Path("data/csv")

# --- DB config ---
PG_USER = os.getenv("POSTGRES_USER", "auction_user")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "auction_user")
PG_DB = os.getenv("POSTGRES_DB", "auction_db")

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ---------------------------------------------------------------------------
#  Table creation SQL — mirrors all SQLAlchemy models
# ---------------------------------------------------------------------------
CREATE_TABLES_SQL = """
-- Core tables
CREATE TABLE IF NOT EXISTS tournaments (
    id SERIAL PRIMARY KEY,
    telegram_chat_id BIGINT UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    purse_cr NUMERIC(12,2) NOT NULL,
    max_overseas_players INT NOT NULL,
    max_players_per_team INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    short_code VARCHAR(4) NOT NULL,
    owner_telegram_id BIGINT,
    owner_username VARCHAR(100),
    logo_file_id VARCHAR(255),
    co_owner_telegram_id BIGINT,
    co_owner_username VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tournament_id, short_code),
    UNIQUE(tournament_id, name),
    UNIQUE(tournament_id, owner_telegram_id)
);

CREATE TABLE IF NOT EXISTS players (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    country VARCHAR(100) NOT NULL,
    role VARCHAR(100) NOT NULL,
    is_overseas BOOLEAN NOT NULL DEFAULT FALSE,
    set_number INT NOT NULL,
    base_price_cr NUMERIC(10,2) NOT NULL,
    telegram_file_id VARCHAR(255),
    telegram_photo_path VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auction_runs (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
    set_number INT NOT NULL,
    bid_timer_seconds INT NOT NULL,
    minimum_bid_increment_cr NUMERIC(12,2) DEFAULT 0.25,
    maximum_bid_increment_cr NUMERIC(12,2),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP,
    paused_at TIMESTAMP,
    stopped_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auction_players (
    id SERIAL PRIMARY KEY,
    auction_run_id INT REFERENCES auction_runs(id) ON DELETE CASCADE,
    player_id INT REFERENCES players(id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    current_bid_cr NUMERIC(10,2),
    current_team_id INT REFERENCES teams(id) ON DELETE SET NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(auction_run_id, player_id)
);

CREATE TABLE IF NOT EXISTS auction_results (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
    auction_run_id INT REFERENCES auction_runs(id) ON DELETE CASCADE,
    auction_player_id INT REFERENCES auction_players(id) ON DELETE CASCADE UNIQUE,
    player_id INT REFERENCES players(id) ON DELETE RESTRICT,
    result_status VARCHAR(20) NOT NULL,
    winning_team_id INT REFERENCES teams(id) ON DELETE SET NULL,
    final_bid_cr NUMERIC(10,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS media_files (
    id SERIAL PRIMARY KEY,
    key VARCHAR(32) UNIQUE NOT NULL,
    telegram_file_id VARCHAR(512) NOT NULL,
    telegram_unique_id VARCHAR(128),
    local_path VARCHAR(256),
    media_type VARCHAR(16) NOT NULL DEFAULT 'animation',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS player_stats (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(20) UNIQUE REFERENCES players(player_id),
    bat_matches INT DEFAULT 0, bat_innings INT DEFAULT 0, bat_runs INT DEFAULT 0,
    bat_highest INT DEFAULT 0, bat_average NUMERIC(5,2) DEFAULT 0,
    bat_strike_rate NUMERIC(5,2) DEFAULT 0, bat_100s INT DEFAULT 0, bat_50s INT DEFAULT 0,
    bat_4s INT DEFAULT 0, bat_6s INT DEFAULT 0,
    bat_powerplay_sr NUMERIC(5,2), bat_middle_sr NUMERIC(5,2), bat_death_sr NUMERIC(5,2),
    bat_vs_pace_avg NUMERIC(5,2), bat_vs_spin_avg NUMERIC(5,2),
    bowl_matches INT DEFAULT 0, bowl_innings INT DEFAULT 0, bowl_wickets INT DEFAULT 0,
    bowl_average NUMERIC(5,2) DEFAULT 0, bowl_economy NUMERIC(5,2) DEFAULT 0,
    bowl_strike_rate NUMERIC(5,2) DEFAULT 0, bowl_best VARCHAR(10),
    bowl_powerplay_econ NUMERIC(5,2), bowl_middle_econ NUMERIC(5,2), bowl_death_econ NUMERIC(5,2),
    catches INT DEFAULT 0, run_outs INT DEFAULT 0, stumpings INT DEFAULT 0,
    bat_rating INT DEFAULT 0, bowl_rating INT DEFAULT 0, overall_rating INT DEFAULT 0,
    power_rating INT DEFAULT 0, timing_rating INT DEFAULT 0,
    consistency_rating INT DEFAULT 0, clutch_rating INT DEFAULT 0,
    last_updated TIMESTAMP, source VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
    match_number INT DEFAULT 1,
    team1_id INT REFERENCES teams(id) ON DELETE CASCADE,
    team2_id INT REFERENCES teams(id) ON DELETE CASCADE,
    venue_code VARCHAR(10) NOT NULL, venue_name VARCHAR(150) NOT NULL,
    toss_winner_id INT REFERENCES teams(id), toss_decision VARCHAR(10),
    result_type VARCHAR(30), result_detail VARCHAR(200),
    winner_team_id INT REFERENCES teams(id),
    potm_player_id INT REFERENCES players(id), potm_reason VARCHAR(200),
    status VARCHAR(20) DEFAULT 'PENDING',
    team1_setup TEXT, team2_setup TEXT,
    started_at TIMESTAMP, completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS match_innings (
    id SERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    innings_number INT NOT NULL,
    batting_team_id INT REFERENCES teams(id),
    bowling_team_id INT REFERENCES teams(id),
    total_runs INT DEFAULT 0, total_wickets INT DEFAULT 0, total_balls INT DEFAULT 0,
    extras_wides INT DEFAULT 0, extras_noballs INT DEFAULT 0,
    extras_byes INT DEFAULT 0, extras_legbyes INT DEFAULT 0, extras_total INT DEFAULT 0,
    run_rate NUMERIC(5,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS match_deliveries (
    id SERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    innings_number INT NOT NULL, ball_number INT NOT NULL,
    over_number INT NOT NULL, ball_in_over INT NOT NULL,
    striker_id INT REFERENCES players(id),
    non_striker_id INT REFERENCES players(id),
    bowler_id INT REFERENCES players(id),
    outcome VARCHAR(20) NOT NULL, runs_scored INT DEFAULT 0,
    extras INT DEFAULT 0, total_runs INT DEFAULT 0,
    is_wicket BOOLEAN DEFAULT FALSE, dismissal_type VARCHAR(30),
    dismissal_detail VARCHAR(200), dismissed_player_id INT REFERENCES players(id),
    fielder_id INT REFERENCES players(id), commentary TEXT
);

CREATE TABLE IF NOT EXISTS match_batting_scorecard (
    id SERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    innings_number INT NOT NULL, player_id INT REFERENCES players(id),
    team_id INT REFERENCES teams(id), batting_order INT DEFAULT 0,
    runs INT DEFAULT 0, balls INT DEFAULT 0, fours INT DEFAULT 0, sixes INT DEFAULT 0,
    is_not_out BOOLEAN DEFAULT FALSE, dismissal_type VARCHAR(30),
    dismissed_by_id INT REFERENCES players(id), strike_rate NUMERIC(6,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS match_bowling_scorecard (
    id SERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    innings_number INT NOT NULL, player_id INT REFERENCES players(id),
    team_id INT REFERENCES teams(id),
    balls_bowled INT DEFAULT 0, runs_conceded INT DEFAULT 0, wickets INT DEFAULT 0,
    wides INT DEFAULT 0, noballs INT DEFAULT 0, economy NUMERIC(5,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tournament_standings (
    id SERIAL PRIMARY KEY,
    tournament_id INT REFERENCES tournaments(id) ON DELETE CASCADE,
    team_id INT REFERENCES teams(id) ON DELETE CASCADE,
    matches_played INT DEFAULT 0, wins INT DEFAULT 0, losses INT DEFAULT 0,
    ties INT DEFAULT 0, no_result INT DEFAULT 0,
    runs_for INT DEFAULT 0, balls_faced INT DEFAULT 0,
    runs_against INT DEFAULT 0, balls_bowled INT DEFAULT 0,
    points INT DEFAULT 0, nrr NUMERIC(6,3) DEFAULT 0.000,
    UNIQUE(tournament_id, team_id)
);
"""


# Import order matters (foreign keys)
TABLES = [
    ("tournaments", "tournaments.csv", [
        "id", "telegram_chat_id", "name", "purse_cr",
        "max_overseas_players", "max_players_per_team",
    ]),
    ("teams", "teams.csv", [
        "id", "tournament_id", "name", "short_code",
        "owner_telegram_id", "owner_username", "logo_file_id",
        "co_owner_telegram_id", "co_owner_username",
    ]),
    ("players", "players.csv", [
        "id", "player_id", "name", "country", "role",
        "is_overseas", "set_number", "base_price_cr",
        "telegram_file_id", "telegram_photo_path",
    ]),
    ("auction_runs", "auction_runs.csv", [
        "id", "tournament_id", "set_number", "bid_timer_seconds",
        "minimum_bid_increment_cr", "maximum_bid_increment_cr", "status",
    ]),
    ("auction_players", "auction_players.csv", [
        "id", "auction_run_id", "player_id", "status",
        "current_bid_cr", "current_team_id",
    ]),
    ("auction_results", "auction_results.csv", [
        "id", "tournament_id", "auction_run_id", "auction_player_id",
        "player_id", "result_status", "winning_team_id", "final_bid_cr",
    ]),
    ("media_files", "media_files.csv", [
        "id", "key", "telegram_file_id", "telegram_unique_id",
        "local_path", "media_type",
    ]),
    ("player_stats", "player_stats.csv", None),
]


def load_csv(filename: Path) -> list[dict]:
    if not filename.exists():
        return []
    with open(filename, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escape_sql(val) -> str:
    if val is None or val == "":
        return "\\N"
    return str(val).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def get_conn():
    """Get a psycopg2 connection."""
    return psycopg2.connect(
        host="postgres", port="5432",
        user=PG_USER, password=PG_PASS, dbname=PG_DB,
    )


def run_sql(conn, sql):
    """Execute raw SQL."""
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()


def import_table(conn, rows, table, columns):
    """Import rows using psycopg2 COPY."""
    if not rows:
        print(f"    ⏭️  {table} — no data, skipping")
        return

    lines = []
    for row in rows:
        vals = [escape_sql(row.get(c)) for c in columns]
        lines.append("\t".join(vals))

    data = "\n".join(lines) + "\n"
    col_str = ", ".join(columns)

    cur = conn.cursor()
    copy_sql = f"COPY {table}({col_str}) FROM STDIN WITH (FORMAT text)"
    cur.copy_expert(copy_sql, __import__("io").StringIO(data))
    conn.commit()
    cur.close()
    print(f"    ✅ {table}: {len(rows)} rows")


def main():
    print("=" * 50)
    print("📥 Importing database from CSV files")
    print("=" * 50)

    if not HAS_PSYCOPG2:
        print("❌ psycopg2 not installed!")
        print("   Run: pip install psycopg2-binary")
        sys.exit(1)

    if not CSV_DIR.exists():
        print(f"❌ CSV directory not found: {CSV_DIR}")
        sys.exit(1)

    # Connect
    print("🔌 Connecting to PostgreSQL...")
    try:
        conn = get_conn()
    except Exception as e:
        print(f"❌ Cannot connect: {e}")
        sys.exit(1)
    print("✅ Connected!\n")

    # Step 1: Create all tables
    print("🏗️  Creating tables (if not exist)...")
    run_sql(conn, CREATE_TABLES_SQL)
    print("    ✅ All tables ready\n")

    # Step 2: Import data in FK order
    # Tables with FK dependencies on parent tables
    FK_DEPS = {
        "teams": ["tournaments"],
        "auction_runs": ["tournaments"],
        "auction_players": ["auction_runs", "players"],
        "auction_results": ["tournaments", "auction_runs", "auction_players", "players", "teams"],
        "player_stats": ["players"],
    }
    imported_tables = set()  # Track which tables got data

    print("📥 Importing data...")
    total_rows = 0
    for table, filename, columns in TABLES:
        csv_file = CSV_DIR / filename
        rows = load_csv(csv_file)
        if not rows:
            print(f"    ⏭️  {filename} — not found or empty, skipping")
            continue

        # Check parent tables exist
        deps = FK_DEPS.get(table, [])
        missing_deps = [d for d in deps if d not in imported_tables]
        if missing_deps:
            print(f"    ⏭️  {table} — skipped (missing dependencies: {', '.join(missing_deps)})")
            continue

        if columns is None:
            columns = list(rows[0].keys())
        try:
            import_table(conn, rows, table, columns)
            imported_tables.add(table)
            total_rows += len(rows)
        except Exception as e:
            print(f"    ❌ {table} — import failed: {e}")
            conn.rollback()

    # Step 3: Reset sequences
    print("\n🔄 Resetting sequences...")
    for table, filename, columns in TABLES:
        if columns and "id" in columns:
            cur = conn.cursor()
            cur.execute(
                f"SELECT setval('{table}_id_seq', "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
            conn.commit()
            cur.close()

    conn.close()
    print()
    print("=" * 50)
    print(f"✅ Import complete! Total rows: {total_rows}")
    print("=" * 50)


if __name__ == "__main__":
    main()
