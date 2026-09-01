#!/usr/bin/env python3
"""
Import CSV exports into a fresh PostgreSQL database.
Run from the host (outside Docker):

    docker compose exec bot python scripts/import_db.py

Or inside the container (bot service):

    python scripts/import_db.py

Reads CSV files from data/csv/ and inserts them in the correct order
(respecting foreign keys).
"""

import csv
import os
import sys
import subprocess
from pathlib import Path

CSV_DIR = Path("data/csv")

# ---------------------------------------------------------------------------
#  Database connection — detect if running inside Docker or on host
# ---------------------------------------------------------------------------
IS_DOCKER = os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "1"

if IS_DOCKER:
    # Inside container — connect directly to postgres via Docker network
    PG_HOST = "postgres"  # Service name in docker-compose
    PG_PORT = "5432"
else:
    # On host — connect via docker exec
    PG_HOST = None  # Will use docker exec instead
    PG_PORT = None

PG_USER = os.getenv("POSTGRES_USER", "auction_user")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "auction_user")
PG_DB = os.getenv("POSTGRES_DB", "auction_db")

# Try psycopg2 first (direct connection)
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


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


def run_psql(sql: str) -> tuple[int, str, str]:
    """Run a SQL command. Returns (returncode, stdout, stderr)."""
    if HAS_PSYCOPG2 and IS_DOCKER:
        # Direct connection inside container
        try:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT,
                user=PG_USER, password=PG_PASS, dbname=PG_DB,
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(sql)
            try:
                result = "\n".join(cur.fetchall().__repr__())
            except Exception:
                result = ""
            cur.close()
            conn.close()
            return 0, result, ""
        except Exception as e:
            return 1, "", str(e)
    else:
        # docker exec from host
        cmd = (
            f"docker exec auction_postgres psql "
            f"-U {PG_USER} -d {PG_DB} -c \"{sql}\""
        )
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr


def import_with_copy(rows: list[dict], table: str, columns: list[str]):
    """Import using psql \\COPY via COPY ... FROM STDIN."""
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

    if HAS_PSYCOPG2 and IS_DOCKER:
        # Direct psycopg2 COPY
        try:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT,
                user=PG_USER, password=PG_PASS, dbname=PG_DB,
            )
            conn.autocommit = True
            cur = conn.cursor()
            copy_sql = f"COPY {table}({col_str}) FROM STDIN WITH (FORMAT text)"
            cur.copy_expert(copy_sql, open("/dev/stdin", "r") if False else __import__("io").StringIO(data))
            cur.close()
            conn.close()
            print(f"    ✅ {table}: {len(rows)} rows")
        except Exception as e:
            print(f"    ❌ Error importing {table}: {e}")
    else:
        # docker exec approach
        cmd = (
            f"docker exec -i auction_postgres psql "
            f"-U {PG_USER} -d {PG_DB} -c "
            f"\"\\COPY {table}({col_str}) FROM STDIN WITH (FORMAT text)\""
        )
        proc = subprocess.run(cmd, shell=True, input=data, capture_output=True, text=True)
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

    # Check if PostgreSQL is reachable
    rc, out, err = run_psql("SELECT 1")
    if rc != 0:
        print("❌ PostgreSQL is not reachable!")
        if IS_DOCKER:
            print("   Make sure postgres service is running.")
        else:
            print("   Start it with: docker compose up -d postgres")
        sys.exit(1)

    print("✅ PostgreSQL is running\n")

    # Reset sequences first (so IDs work correctly)
    print("🔄 Resetting sequences...")
    for table, filename, columns in TABLES:
        csv_file = CSV_DIR / filename
        rows = load_csv(csv_file)
        if rows and "id" in (columns or []):
            run_psql(
                f"SELECT setval('{table}_id_seq', "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
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

        import_with_copy(rows, table, columns)
        total_rows += len(rows)

    print()
    print("=" * 50)
    print(f"✅ Import complete! Total rows: {total_rows}")
    print("=" * 50)


if __name__ == "__main__":
    main()
