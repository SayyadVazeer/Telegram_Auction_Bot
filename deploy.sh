#!/bin/bash
# ============================================
# Telegram Auction Bot - Server Deployment
# ============================================
# Usage:
#   First time:  bash deploy.sh
#   Update:      bash deploy.sh
#   Fresh start: bash deploy.sh --fresh
#   Stop:        bash deploy.sh --stop
#   Status:      bash deploy.sh --status
#   Logs:        bash deploy.sh --logs
#   Backup DB:   bash deploy.sh --backup
#   Restore DB:  bash deploy.sh --restore backup.sql
# ============================================

set -e

COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}   Telegram Auction Bot - Deployment${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""
}

# ── Check prerequisites ──
check_prereqs() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed.${NC}"
        echo "Install Docker: https://docs.docker.com/engine/install/"
        exit 1
    fi
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not installed.${NC}"
        echo "Install: https://docs.docker.com/compose/install/"
        exit 1
    fi
}

# ── Use 'docker compose' or 'docker-compose' ──
dc() {
    if docker compose version &> /dev/null; then
        docker compose "$@"
    else
        docker-compose "$@"
    fi
}

# ── Check .env exists ──
check_env() {
    if [ ! -f .env ]; then
        echo -e "${YELLOW}No .env file found. Creating from .env.example...${NC}"
        if [ -f .env.example ]; then
            cp .env.example .env
            echo -e "${YELLOW}Please edit .env and set BOT_TOKEN and ADMIN_IDS before starting.${NC}"
            echo ""
            echo "  nano .env"
            echo ""
            exit 1
        else
            echo -e "${RED}No .env.example found either. Create .env manually.${NC}"
            exit 1
        fi
    fi
}

# ── Check if data directory has player photos ──
check_data() {
    if [ ! -d "data/photos" ] || [ -z "$(ls -A data/photos 2>/dev/null)" ]; then
        echo -e "${YELLOW}Warning: data/photos/ is empty.${NC}"
        echo "Player photos need to be in data/photos/ (e.g., PLY0001.jpg)"
        echo ""
    fi
}

# ── Show volume info ──
show_volumes() {
    echo -e "${CYAN}Docker Volumes:${NC}"
    docker volume ls --format "  {{.Name}} ({{.Driver}})" 2>/dev/null | grep -i auction || echo "  No volumes found yet"
    echo ""
}

# ── Main deploy ──
deploy() {
    print_header
    check_prereqs
    check_env
    check_data

    echo -e "${GREEN}Step 1:${NC} Stopping existing containers..."
    dc down 2>/dev/null || true

    echo -e "${GREEN}Step 2:${NC} Building bot image..."
    dc build --no-cache

    echo -e "${GREEN}Step 3:${NC} Starting services..."
    dc up -d

    echo ""
    echo -e "${GREEN}Step 4:${NC} Waiting for database..."
    sleep 5

    echo -e "${GREEN}Step 5:${NC} Checking status..."
    dc ps

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}   Deployment Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "  Bot logs:     bash deploy.sh --logs"
    echo "  Stop:         bash deploy.sh --stop"
    echo "  Status:       bash deploy.sh --status"
    echo "  Backup DB:    bash deploy.sh --backup"
    echo ""
}

# ── Fresh start (wipe everything) ──
fresh_start() {
    print_header
    echo -e "${RED}WARNING: This will DELETE all database data and rebuild from scratch!${NC}"
    echo -e "${RED}Player photos in data/photos will be preserved.${NC}"
    echo ""
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi

    check_prereqs
    check_env

    echo -e "${YELLOW}Step 1:${NC} Stopping and removing containers + volumes..."
    dc down -v

    echo -e "${YELLOW}Step 2:${NC} Building fresh..."
    dc build --no-cache

    echo -e "${YELLOW}Step 3:${NC} Starting fresh..."
    dc up -d

    sleep 5
    dc ps

    echo ""
    echo -e "${GREEN}Fresh deployment complete!${NC}"
    echo -e "${YELLOW}Note: Players from CSV need to be re-imported.${NC}"
}

# ── Stop ──
stop() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    dc down
    echo -e "${GREEN}Services stopped. Data preserved in Docker volumes.${NC}"
}

# ── Status ──
status() {
    echo -e "${CYAN}Container Status:${NC}"
    dc ps
    echo ""
    show_volumes
}

# ── Logs ──
logs() {
    dc logs -f --tail=100 bot
}

# ── Backup database ──
backup_db() {
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"
    echo -e "${CYAN}Backing up database to $BACKUP_FILE...${NC}"

    # Source .env for credentials
    source .env

    docker exec auction_postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$BACKUP_FILE"

    if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
        echo -e "${GREEN}Backup saved: $BACKUP_FILE${NC}"
        ls -lh "$BACKUP_FILE"
    else
        echo -e "${RED}Backup failed!${NC}"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
}

# ── Restore database ──
restore_db() {
    BACKUP_FILE="$1"
    if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
        echo -e "${RED}Usage: bash deploy.sh --restore <backup_file.sql>${NC}"
        echo ""
        echo "Available backups:"
        ls -lh "$BACKUP_DIR"/*.sql 2>/dev/null || echo "  No backups found"
        exit 1
    fi

    echo -e "${YELLOW}WARNING: This will OVERWRITE the current database!${NC}"
    read -p "Continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi

    source .env

    echo -e "${CYAN}Restoring from $BACKUP_FILE...${NC}"
    docker exec -i auction_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_FILE"
    echo -e "${GREEN}Database restored!${NC}"
}

# ── Parse args ──
case "${1:-}" in
    --fresh)
        fresh_start
        ;;
    --stop)
        stop
        ;;
    --status)
        status
        ;;
    --logs)
        logs
        ;;
    --backup)
        backup_db
        ;;
    --restore)
        restore_db "$2"
        ;;
    *)
        deploy
        ;;
esac
