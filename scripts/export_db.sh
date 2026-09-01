#!/bin/bash
# ============================================================
#  Export Database to CSV — Run this on your LOCAL machine
#  Usage: bash scripts/export_db.sh
# ============================================================

set -e

OUT_DIR="data/csv"
DB_CONTAINER="auction_postgres"
DB_USER="auction_user"
DB_NAME="auction_db"

mkdir -p "$OUT_DIR"

echo "📦 Exporting database to $OUT_DIR ..."
echo ""

# --- Helper function ---
export_table() {
    local table=$1
    local outfile=$2
    local sql=$3

    echo "  → $table"
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' -c "$sql" > "$OUT_DIR/$outfile"
    # Add header row by counting columns from first data row
    if [ -s "$OUT_DIR/$outfile" ]; then
        # Use the column names from the SELECT
        local header=$(echo "$sql" | sed 's/.*SELECT //i' | sed 's/ FROM .*//i' | tr '[:lower:]' '[:upper:]')
        # Actually just grab first line to check if data exists
        local count=$(wc -l < "$OUT_DIR/$outfile")
        echo "    ✅ $count rows"
    else
        echo "    ⚠️  No data"
    fi
}

# --- 1. Tournaments ---
echo "  → tournaments"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT id, telegram_chat_id, name, purse_cr::text, max_overseas_players, max_players_per_team FROM tournaments" \
  > "$OUT_DIR/tournaments.csv"
# Prepend header
sed -i '1i id,telegram_chat_id,name,purse_cr,max_overseas_players,max_players_per_team' "$OUT_DIR/tournaments.csv"
echo "    ✅ $(tail -n +2 "$OUT_DIR/tournaments.csv" | wc -l | tr -d ' ') rows"

# --- 2. Teams ---
echo "  → teams"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT id, tournament_id, name, short_code, COALESCE(owner_telegram_id::text,''), COALESCE(owner_username,''), COALESCE(logo_file_id,''), COALESCE(co_owner_telegram_id::text,''), COALESCE(co_owner_username,'') FROM teams" \
  > "$OUT_DIR/teams.csv"
sed -i '1i id,tournament_id,name,short_code,owner_telegram_id,owner_username,logo_file_id,co_owner_telegram_id,co_owner_username' "$OUT_DIR/teams.csv"
echo "    ✅ $(tail -n +2 "$OUT_DIR/teams.csv" | wc -l | tr -d ' ') rows"

# --- 3. Players ---
echo "  → players"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT id, player_id, name, country, role, is_overseas, set_number, base_price_cr::text, COALESCE(telegram_file_id,'')::text, COALESCE(telegram_photo_path,'') FROM players" \
  > "$OUT_DIR/players.csv"
sed -i '1i id,player_id,name,country,role,is_overseas,set_number,base_price_cr,telegram_file_id,telegram_photo_path' "$OUT_DIR/players.csv"
echo "    ✅ $(tail -n +2 "$OUT_DIR/players.csv" | wc -l | tr -d ' ') rows"

# --- 4. Auction Runs ---
echo "  → auction_runs"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT id, tournament_id, set_number, bid_timer_seconds, minimum_bid_increment_cr::text, COALESCE(maximum_bid_increment_cr::text,''), status FROM auction_runs" \
  > "$OUT_DIR/auction_runs.csv"
sed -i '1i id,tournament_id,set_number,bid_timer_seconds,minimum_bid_increment_cr,maximum_bid_increment_cr,status' "$OUT_DIR/auction_runs.csv"
echo "    ✅ $(tail -n +2 "$OUT_DIR/auction_runs.csv" | wc -l | tr -d ' ') rows"

# --- 5. Auction Results ---
echo "  → auction_results"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT id, tournament_id, COALESCE(auction_run_id::text,''), COALESCE(auction_player_id::text,''), player_id, result_status, COALESCE(winning_team_id::text,''), COALESCE(final_bid_cr::text,'') FROM auction_results" \
  > "$OUT_DIR/auction_results.csv"
sed -i '1i id,tournament_id,auction_run_id,auction_player_id,player_id,result_status,winning_team_id,final_bid_cr' "$OUT_DIR/auction_results.csv"
echo "    ✅ $(tail -n +2 "$OUT_DIR/auction_results.csv" | wc -l | tr -d ' ') rows"

# --- 6. Media Files ---
echo "  → media_files"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT id, key, telegram_file_id, COALESCE(telegram_unique_id,''), COALESCE(local_path,''), media_type FROM media_files" \
  > "$OUT_DIR/media_files.csv"
sed -i '1i id,key,telegram_file_id,telegram_unique_id,local_path,media_type' "$OUT_DIR/media_files.csv"
echo "    ✅ $(tail -n +2 "$OUT_DIR/media_files.csv" | wc -l | tr -d ' ') rows"

# --- 7. Player Stats (may not exist yet) ---
echo "  → player_stats"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F',' \
  -c "SELECT * FROM player_stats" \
  > "$OUT_DIR/player_stats.csv" 2>/dev/null
if [ -s "$OUT_DIR/player_stats.csv" ]; then
    echo "    ✅ $(wc -l < "$OUT_DIR/player_stats.csv" | tr -d ' ') rows"
else
    echo "    ⏭️  Table not found or empty — skipped"
    rm -f "$OUT_DIR/player_stats.csv"
fi

# --- Summary ---
echo ""
echo "════════════════════════════════════════"
echo "✅ Export complete!"
echo "════════════════════════════════════════"
echo ""
echo "Files saved to $OUT_DIR/:"
for f in "$OUT_DIR"/*.csv; do
    name=$(basename "$f" .csv)
    lines=$(tail -n +2 "$f" | wc -l | tr -d ' ')
    size=$(ls -lh "$f" | awk '{print $5}')
    echo "  📄 $name.csv — $lines rows ($size)"
done
echo ""
echo "Next steps:"
echo "  1. Upload entire project to server (including data/csv/ and data/photos/)"
echo "  2. On server: docker compose exec bot python scripts/import_db.py"
