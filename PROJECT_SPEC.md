# Telegram Auction Bot — Project Specification

## 1. Project Overview

This project is a Telegram-based player auction system designed to run an auction inside a Telegram group.

The system will manage:

- Tournaments
- Tournament-specific auction rules
- Teams
- Team owners
- Players
- Player photos
- Auction sets
- Random player selection
- Live bidding
- Bid timers
- Last-call sequence
- Sold/unsold players
- Auction history
- Admin controls
- Tournament completion

The bot is designed to support concurrent bidding and future expansion without mixing Telegram handlers, business logic, and database operations.

---

# 2. Technology Stack

## Backend

- Python 3.12
- aiogram 3.x
- SQLAlchemy
- PostgreSQL
- Alembic
- asyncpg
- pydantic-settings

## Infrastructure

- Docker
- Docker Compose
- Persistent PostgreSQL storage
- Local/player-photo storage during development

## Telegram

The bot runs inside Telegram groups.

A tournament is associated with one Telegram group.

---

# 3. Project Architecture

The intended architecture is:

```text
Telegram
   |
   v
aiogram
   |
   v
Handlers
   |
   v
Services
   |
   v
Repositories
   |
   v
SQLAlchemy
   |
   v
PostgreSQL




Project Structure

Telegram_Auction_Bot/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── player.py
│   │       ├── tournament.py
│   │       └── team.py
│   │
│   ├── repositories/
│   │   ├── player_repository.py
│   │   ├── tournament_repository.py
│   │   └── team_repository.py
│   │
│   ├── services/
│   │   ├── player_service.py
│   │   ├── tournament_service.py
│   │   ├── team_service.py
│   │   ├── auction_service.py
│   │   └── bidding_service.py
│   │
│   └── bot/
│       ├── bot.py
│       │
│       ├── handlers/
│       │   ├── start.py
│       │   ├── players.py
│       │   ├── tournament.py
│       │   ├── team.py
│       │   ├── auction.py
│       │   ├── bidding.py
│       │   └── admin.py
│       │
│       ├── keyboards/
│       │   ├── tournament.py
│       │   ├── team.py
│       │   ├── auction.py
│       │   └── admin.py
│       │
│       └── states/
│           ├── tournament_states.py
│           ├── team_states.py
│           └── auction_states.py
│
├── data/
│   ├── csv/
│   │   └── players.csv
│   │
│   └── photos/
│       ├── PLY0001.jpg
│       ├── PLY0002.jpg
│       └── ...
│
├── migrations/
│
├── scripts/
│   ├── import_players.py
│   └── validate_players.py
│
├── tests/
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── README.md
└── PROJECT_SPEC.md


