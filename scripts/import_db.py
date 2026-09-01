#!/usr/bin/env python3
"""
Import CSV exports into a fresh PostgreSQL database.
Run this INSIDE the Docker container on the server:

    docker compose exec bot python scripts/import_db.py

Or locally to test:

    python scripts/import_db.py

It reads CSV files from data/csv/ and inserts them in the correct order
(respecting foreign keys).
"""

import csv
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
#  Database connection — reads from environment (set by docker-compose .env)
# ---------------------------------------------------------------------------
try:
    from app.config.settings import settings
    DATABASE_URL = settings.database_url
except Exception:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://auction_user:auction_user@localhost:5432/auction_db",
    )

# We need synchronous psycopg2 for the import script.
# Fall back to a raw approach if psycopg2 isn't installed.
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# If no psycopg2, try using docker exec with psql
try:
    import subprocess
    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False


CSV_DIR = Path("data/csv")

# Import order matters (foreign keys)
TABLES = [
    # (table_name, csv_filename, columns_in_order)
    (
        "tournaments",
        "tournaments.csv",
        [
            "id", "telegram_chat_id", "name", "purse_cr",
            "max_overseas_players", "max_players_per_team",
        ],
    ),
    (
        "teams",
        "teams.csv",
        [
            "id", "tournament_id", "name", "short_code",
            "owner_telegram_id", "owner_username", "logo_file_id",
            "co_owner_telegram_id", "co_owner_username",
        ],
    ),
    (
        "players",
        "players.csv",
        [
            "id", "player_id", "name", "country", "role",
            "is_overseas", "set_number", "base_price_cr",
            "telegram_file_id", "telegram_photo_path",
        ],
    ),
    (
        "auction_runs",
        "auction_runs.csv",
        [
            "id", "tournament_id", "set_number", "bid_timer_seconds",
            "minimum_bid_increment_cr", "maximum_bid_increment_cr", "status",
        ],
    ),
    (
        "auction_players",
        "auction_players.csv",
        [
            "id", "auction_run_id", "player_id", "status",
            "current_bid_cr", "current_team_id",
        ],
    ),
    (
        "auction_results",
        "auction_results.csv",
        [
            "id", "tournament_id", "auction_run_id", "auction_player_id",
            "player_id", "result_status", "winning_team_id", "final_bid_cr",
        ],
    ),
    (
        "media_files",
        "media_files.csv",
        [
            "id", "key", "telegram_file_id", "telegram_unique_id",
            "local_path", "media_type",
        ],
    ),
    (
        "player_stats",
        "player_stats.csv",
        None,  # All columns
    ),
]


def load_csv(filename: Path) -> list[dict]:
    """Load a CSV file into a list of dicts. Returns empty list if missing."""
    if not filename.exists():
        return []
    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def escape_sql(val: str | None) -> str:
    """Simple SQL value escaping for COPY format."""
    if val is None or val == "":
        return "\\N"
    return str(val).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def import_with_psql(rows: list[dict], table: str, columns: list[str]):
    """Import using psql \\copy via COPY ... FROM STDIN."""
    if not rows:
        print(f"    ⚠️  No data for {table}")
        return

    # Build TSV-like data for COPY
    lines = []
    for row in rows:
        vals = [escape_sql(row.get(c)) for c in columns]
        lines.append("\t".join(vals))

    data = "\n".join(lines) + "\n"
    col_str = ", ".join(columns)

    cmd = (
        f"docker exec auction_postgres psql -U auction_user -d auction_db -c "
        f"\"\\COPY {table}({col_str}) FROM STDIN WITH (FORMAT text)\""
    )

    proc = subprocess.run(
        cmd, shell=True, input=data, capture_output=True, text=True
    )
    if proc.returncode != 0:
        print(f"    ❌ Error importing {table}: {proc.stderr.strip()}")
    else:
        print(f"    ✅ {table}: {len(rows)} rows")


def main():
    print("=" * 50)
    print("📥 Importing database from CSV files")
    print("=" * 50)

    if not CSV_DIR.exists():
        print(f"❌ CSV directory not found: {CSV_DIR}")
        print("   Make sure data/csv/ exists with exported CSV files.")
        sys.exit(1)

    # Check if docker is running
    check = subprocess.run(
        "docker exec auction_postgres pg_isready -U auction_user -d auction_bot",
        shell=True, capture_output=True, text=True
    )
    if check.returncode != 0:
        print("❌ PostgreSQL container is not running!")
        print("   Start it with: docker compose up -d postgres")
        sys.exit(1)

    print("✅ PostgreSQL is running\n")

    # Reset sequences first (so IDs work correctly)
    print("🔄 Resetting sequences...")
    for table, _, columns in TABLES:
        csv_file = CSV_DIR / TABLES[TABLES.index((table, _, columns))][1]
        rows = load_csv(csv_file)
        if rows and "id" in columns:
            subprocess.run(
                f"docker exec auction_postgres psql -U auction_user -d auction_db -c "
                f"\"SELECT setval('{table}_id_seq', COALESCE((SELECT MAX(id) FROM {table}), 1))\"",
                shell=True, capture_output=True, text=True
            )
    print()

    # Import each table
    total_rows = 0
    for table, filename, columns in TABLES:
        csv_file = CSV_DIR / filename
        rows = load_csv(csv_file)
        if not rows:
            print(f"    ⏭️  {filename} — not found, skipping")
            continue

        if columns is None:
            # Use all columns from CSV header
            columns = list(rows[0].keys())

        import_with_psql(rows, table, columns)
        total_rows += len(rows)

    print()
    print("=" * 50)
    print(f"✅ Import complete! Total rows: {total_rows}")
    print("=" * 50)


if __name__ == "__main__":
    main()
