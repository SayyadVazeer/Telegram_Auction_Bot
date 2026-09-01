# 🏏 Telegram Auction Bot — The Hundreds

A full-featured cricket auction bot for Telegram groups with live bidding, player management, team management, trading, real-time auction GIFs, and **AI-powered match simulation**.

---

## ✨ Features

### V1 — Auction System
- 🎯 **Live Auction** — Real-time bidding with countdown timer
- 🎬 **GIF Animations** — "Going once, going twice, SOLD/UNSOLD" with player cards
- 👥 **Team Management** — Create teams, assign owners, co-owners
- 🔄 **Trading** — Player trade system with accept/reject
- 📊 **Auction Control** — Pause, resume, stop, manual sell/unsell
- 📸 **Player Cards** — Generated with Pillow (gold text, player photos)
- 🏷️ **Set System** — 16 sets of players, group-wise bidding
- 💰 **Purse Management** — Track spending, overseas limits, squad size

### V2 — Match Simulation
- ⚡ **Ball-by-Ball Simulation** — Probability-based engine using player ratings
- 🏟️ **12 Venue Models** — Trent Bridge, Lord's, Oval, etc. with realistic effects
- 🎯 **Player Archetypes** — Power hitter, anchor, accumulator, spin wizard, etc.
- 📈 **Player Ratings** — 0-100 ratings derived from real T20 stats
- 🏆 **Tournament Standings** — Points table with NRR, head-to-head
- 📝 **Commentary Generation** — TV-style ball-by-ball commentary
- 🎮 **Interactive Control** — Owners pick playing 11, openers, bowling plans

---

## 🚀 Deploy to Oracle Cloud (Free Tier)

### Prerequisites
- Oracle Cloud account (Always Free tier)
- SSH key pair

### 1. Create VM Instance

1. Oracle Cloud Console → **Compute** → **Instances** → **Create Instance**
2. Configure:
   - **Name:** `auction-bot`
   - **Image:** Ubuntu 22.04/24.04 (aarch64/ARM)
   - **Shape:** VM.Standard.A1.Flex → **2 OCPUs + 12 GB RAM**
   - **VCN:** Create new (default)
   - **Public IP:** Assign one
3. Add SSH key → **Create**

### 2. Connect & Install Docker

```bash
ssh ubuntu@<YOUR_PUBLIC_IP> -i ~/.ssh/your_key

# Install Docker
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io
sudo usermod -aG docker ubuntu
newgrp docker
```

### 3. Export Database (from your PC)

```bash
cd Telegram_Auction_Bot
bash scripts/export_db.sh
```

This creates CSVs in `data/csv/`:
- `players.csv` (445+ players)
- `teams.csv`
- `tournaments.csv`
- `auction_runs.csv`
- `auction_results.csv`
- `media_files.csv`

### 4. Upload to Server

```bash
# From your PC
scp -r . ubuntu@<YOUR_IP>:~/auction-bot/

# Or create a tarball first
tar -czf auction-bot.tar.gz --exclude='__pycache__' --exclude='.git' .
scp auction-bot.tar.gz ubuntu@<YOUR_IP>:~/
ssh ubuntu@<YOUR_IP>
mkdir -p ~/auction-bot && cd ~/auction-bot
tar -xzf ~/auction-bot.tar.gz
```

### 5. Configure Environment

```bash
cp .env.example .env
nano .env
```

Set these variables:
```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql+asyncpg://auction_user:auction_user@postgres:5432/auction_db
POSTGRES_USER=auction_user
POSTGRES_PASSWORD=auction_user
POSTGRES_DB=auction_db
ADMIN_IDS=your_telegram_id
ELITESPORT_API_KEY=your_api_key  # Optional — for live stats
```

### 6. Build & Run

```bash
docker compose up -d --build
docker compose logs -f bot  # Watch startup logs
```

### 7. Import Database

```bash
docker compose exec bot python scripts/import_db.py
```

### 8. Import Player Stats (Optional)

```bash
docker compose exec bot python -c "
import asyncio
from app.simulation.stats_scraper import import_stats_from_csv
asyncio.run(import_stats_from_csv())
"
```

---

## 🔧 Management Commands

```bash
# Status
docker compose ps

# Logs
docker compose logs -f bot
docker compose logs -f postgres

# Restart bot
docker compose restart bot

# Full rebuild
docker compose down && docker compose up -d --build

# Database backup
docker exec auction_postgres pg_dump -U auction_user auction_db > backup.sql

# Database restore
cat backup.sql | docker exec -i auction_postgres psql -U auction_user auction_db
```

---

## 📋 Bot Commands

### 👥 Everyone Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu with buttons |
| `/help` | Command list |
| `/help_all` | Full admin guide (admin DM only) |
| `/cancel` | Cancel current operation |
| `/teams` | View all teams |
| `/my_team` | View your team squad |
| `/purse` | Check remaining purse, player count, overseas count |
| `/b` or `/bid` | Auto-bid at minimum increment |
| `/bid <amount>` | Bid specific amount |
| `/team_logo` | Upload team logo |
| `/player_photo <ID>` | View player photo (with edit option) |
| `/add_coowner <team>` | Add co-owner by replying to user |
| `/remove_coowner <team>` | Remove co-owner |
| `/trade_player` | Propose player trade |
| `/accept_trade` | Accept incoming trade |
| `/reject_trade` | Reject incoming trade |

### 🛡️ Admin Commands

| Command | Description |
|---------|-------------|
| `/menu` | Admin control panel |
| `/add_player` | Add new player (ID → name → role → photo) |
| `/add_team` | Create new team |
| `/assign_owner` | Assign team owner |
| `/edit_team` | Edit team details |
| `/delete_team` | Delete team |
| `/change_owner` | Change team owner |
| `/create_tournament` | Create tournament |
| `/complete_tournament` | End tournament |
| `/start_auction` | Begin auction |
| `/pause_auction` | Pause auction |
| `/resume_auction` | Resume auction |
| `/stop_auction` | Stop auction |
| `/next_player` | Skip to next player |
| `/status` | Auction status |
| `/manual_sell` | Manually sell player |
| `/manual_unsell` | Manually unsell player |
| `/trade_on` | Enable trading |
| `/trade_off` | Disable trading |
| `/add_admin` | Add admin by user ID |
| `/remove_admin` | Remove admin |

### 📊 Simulation Commands (V2)

| Command | Description |
|---------|-------------|
| `/simulate_match` | Start match simulation flow |
| `/tournament_table` | View standings |
| `/match_history` | Past match results |
| `/view_scorecard <id>` | View match scorecard |
| `/refresh_stats` | Fetch player stats from API |
| `/import_stats` | Load stats from CSV |
| `/update_tournament_stats` | Merge auction results into stats |

### 🎬 Media Cache Commands (Admin)

| Command | Description |
|---------|-------------|
| `/player_image_change_generator` | Cache player photos |
| `/image_change_generator` | Upload GIF media files |
| `/upload_gif <key>` | Upload specific GIF |
| `/save_all_media` | Cache all media file IDs |

---

## 🏗️ Project Structure

```
Telegram_Auction_Bot/
├── app/
│   ├── bot/
│   │   ├── handlers/          # Command handlers
│   │   │   ├── auction.py     # Auction flow, bidding, timer
│   │   │   ├── bidding.py     # /bid command, auto-bid logic
│   │   │   ├── start.py       # /start, /help, admin panel, player management
│   │   │   ├── team.py        # Team CRUD, owner assignment
│   │   │   ├── tournament.py  # Tournament creation
│   │   │   ├── players_admin.py  # Admin player operations
│   │   │   └── simulate.py    # V2 match simulation handlers
│   │   ├── keyboards/         # Inline keyboards
│   │   │   ├── auction.py     # Auction control buttons
│   │   │   └── home.py        # Admin panel, player list
│   │   ├── states/            # FSM states
│   │   │   ├── auction_states.py
│   │   │   └── tournament_states.py
│   │   ├── filters/           # Admin/permission filters
│   │   └── bot.py             # Bot setup, router registration
│   ├── database/
│   │   ├── models/            # SQLAlchemy models
│   │   │   ├── player.py      # Player table
│   │   │   ├── team.py        # Team table
│   │   │   ├── tournament.py  # Tournament table
│   │   │   ├── auction.py     # AuctionRun, AuctionPlayer, AuctionResult
│   │   │   ├── media.py       # MediaFile (Telegram file_ids)
│   │   │   └── match.py       # V2: Match, MatchInnings, MatchBall, Standings
│   │   └── base.py            # SQLAlchemy Base
│   ├── services/
│   │   ├── auction_service.py # Auction business logic
│   │   ├── auction_runtime.py # Live auction state management
│   │   └── sold_card.py       # Pillow card generation
│   ├── simulation/            # V2 — Match Simulation
│   │   ├── engine.py          # Ball-by-ball simulation engine
│   │   ├── probability.py     # Outcome probability model
│   │   ├── ratings.py         # Player rating system (0-100)
│   │   ├── venues.py          # 12 venue models with effects
│   │   ├── commentary.py      # TV-style commentary generator
│   │   ├── match_state.py     # Innings/match state tracking
│   │   └── stats_scraper.py   # EliteSport API + CSV stats import
│   ├── config/
│   │   └── settings.py        # Pydantic settings (reads .env)
│   └── main.py                # App entry point
├── scripts/
│   ├── export_db.sh           # Export DB to CSV
│   ├── import_db.py           # Import CSV to DB
│   └── generate_player_stats.py  # Generate player stats CSV
├── data/
│   ├── photos/                # Player photos (445+ JPGs)
│   ├── csv/                   # Database CSVs + player stats
│   ├── *.gif, *.jpg           # Auction media files (bid1.gif, sold.gif, etc.)
│   └── templates/             # HTML templates
├── migrations/                # Alembic migrations
├── tests/                     # Test files
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env                       # Environment variables (not committed)
└── .env.example               # Template
```

---

## 🎮 How the Simulation Works (V2)

### Fairness System

| Factor | How It Works |
|--------|-------------|
| **Player Ratings** | 0-100 derived from real stats (avg, SR, wickets, economy) |
| **Batter vs Bowler** | Power hitter vs express pacer = different probabilities |
| **Venue Effects** | Trent Bridge = batting paradise, Lord's = seam-friendly |
| **Match Phase** | Powerplay (fielding restrictions), middle overs, death overs |
| **Match Situation** | Chasing = aggressive, setting = calculated |
| **Archetypes** | Power hitters hit more 6s, tailenders struggle |
| **Random Variance** | Weighted random — even top batters can get out |

### Player Rating Sources

| Source | Method | Coverage |
|--------|--------|----------|
| EliteSport API | `/refresh_stats` | Real T20 stats (requires API key) |
| CSV Import | `/import_stats` | 444 players with curated stats |
| Fallback | Automatic | Role + price + country → estimated ratings |

### Match Flow
```
Admin selects teams → Pick venue → Toss
    ↓
Team owners pick Playing 11, openers
    ↓
Ball-by-ball simulation (20 overs each)
    ↓
Scorecard → Points table update
```

---

## 🔐 Security

| Concern | Solution |
|---------|----------|
| Bot token | Stored in `.env`, never committed |
| Database | Internal Docker network only |
| Admin access | Telegram user ID whitelist |
| SSH | Key-based authentication |
| PostgreSQL port | Not exposed to internet (internal only) |

---

## 📊 Data Persistence

| What | Where | Survives Rebuild? |
|------|-------|-------------------|
| Database | Docker volume `postgres_data` | ✅ Yes |
| Player photos | `data/photos/` (host mount) | ✅ Yes |
| Auction media | `data/` (host mount) | ✅ Yes |
| CSV exports | `data/csv/` (host mount) | ✅ Yes |
| Bot config | `.env` (host) | ✅ Yes |
| Docker images | Docker cache | ❌ Rebuild needed |

---

## 🔄 Backup Strategy

```bash
# Daily backup (set up cron on server)
0 3 * * * docker exec auction_postgres pg_dump -U auction_user auction_db > ~/backups/db_$(date +\%Y\%m\%d).sql

# Keep last 7 days
0 4 * * * find ~/backups -name "db_*.sql" -mtime +7 -delete
```

---

## 🛠️ Tech Stack

- **Bot Framework:** aiogram 3.31
- **Database:** PostgreSQL 16 + SQLAlchemy 2.0 (async)
- **Card Generation:** Pillow 12.3
- **Deployment:** Docker Compose
- **API Integration:** EliteSport API (player stats)
- **Python:** 3.12

---

## 📝 License

Private project — not for redistribution.
