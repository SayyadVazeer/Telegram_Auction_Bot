# Telegram Auction Bot

A cricket auction bot for Telegram groups with live bidding, player management, team management, trading, and real-time auction GIFs.

## Quick Start (Server)

```bash
# 1. Clone the repo
git clone <repo-url>
cd Telegram_Auction_Bot

# 2. Copy and edit .env
cp .env.example .env
nano .env   # Set BOT_TOKEN and ADMIN_IDS

# 3. Deploy
bash deploy.sh
```

## Deploy Script Commands

```bash
bash deploy.sh              # Build and start (preserves DB data)
bash deploy.sh --fresh      # Wipe DB and start fresh
bash deploy.sh --stop       # Stop all containers (data preserved)
bash deploy.sh --status     # Show container status
bash deploy.sh --logs       # Tail bot logs
bash deploy.sh --backup     # Backup database to backups/
bash deploy.sh --restore    # Restore from backup
```

## Server Requirements

- Docker & Docker Compose
- At least 1GB RAM
- Ports 5433 (PostgreSQL) available

## Data Persistence

| What | Where | Preserved? |
|------|-------|------------|
| Database | Docker volume `postgres_data` | Yes across rebuilds |
| Player photos | `data/photos/` (mounted volume) | Yes |
| GIFs/media | `data/` (mounted volume) | Yes |
| Bot config | `.env` (on host) | Yes |

## Project Structure

```
app/
  bot/
    handlers/    # Command handlers
    keyboards/   # Inline keyboards
    states/      # FSM states
    filters/     # Admin filters
  database/      # SQLAlchemy models
  services/      # Business logic
  config/        # Settings
data/
  photos/        # Player photos (444 files)
  csv/           # players.csv
  *.gif, *.jpg   # Auction media files
```

## Commands

### Everyone
- `/start` - Main menu
- `/help` - Command list
- `/teams` - View teams
- `/my_team` - View your team
- `/purse` - Check purse
- `/b <amount>` or `/bid <amount>` - Place bid
- `/trade_player` - Trade player
- `/accept_trade` / `/reject_trade` - Handle trade
- `/add_coowner <team>` - Add co-owner
- `/remove_coowner <team>` - Remove co-owner
- `/player_photo <ID>` - View player photo

### Admin
- `/start_auction` - Start auction
- `/pause_auction` / `/resume_auction` / `/stop_auction` - Control
- `/status` - Auction status
- `/manual_sell` / `/manual_unsell` - Manual operations
- `/help_all` - Full admin guide (DM only)
