"""Player stats scraper — fetches real T20 stats from EliteSport Cricket API.

Flow:
1. Fetch player stats by name from EliteSport API
2. Store in player_stats table

Falls back to CSV import if no API key configured.
"""

from __future__ import annotations

import asyncio
import csv as csv_mod
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

ELITESPORT_BASE = "https://trial.elitesportapi.com/api/v2"
RATE_LIMIT_DELAY = 1.0  # seconds between requests


# ── EliteSport API Functions ──────────────────────────────────────

async def search_and_fetch_player(
    name: str, api_key: str, session: aiohttp.ClientSession,
) -> Optional[dict]:
    """Search for a player by name and fetch their stats via EliteSport API."""
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    try:
        url = f"{ELITESPORT_BASE}/getPlayerInfo?name={name.replace(' ', '+')}"
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 401:
                logger.error("EliteSport API: Invalid API key")
                return None
            if resp.status == 429:
                logger.warning("EliteSport API: Rate limited, waiting 5s...")
                await asyncio.sleep(5)
                return None
            if resp.status != 200:
                logger.warning("API search failed for %s: HTTP %d", name, resp.status)
                return None
            data = await resp.json()
            if not data.get("success"):
                return None
            player_data = data.get("data", data.get("player", {}))
            if isinstance(player_data, list):
                player_data = player_data[0] if player_data else {}
            return _extract_stats_from_api(player_data)
    except Exception as e:
        logger.error("EliteSport API error for %s: %s", name, e)
    return None


def _extract_stats_from_api(data: dict) -> Optional[dict]:
    """Extract our stats format from EliteSport API response."""
    if not data:
        return None
    batting = data.get("batting", data.get("batting_stats", {}))
    bowling = data.get("bowling", data.get("bowling_stats", {}))
    fielding = data.get("fielding", data.get("fielding_stats", {}))
    stats = {
        "bat_matches": int(batting.get("matches", batting.get("mat", 0)) or 0),
        "bat_innings": int(batting.get("innings", batting.get("inn", 0)) or 0),
        "bat_runs": int(batting.get("runs", 0) or 0),
        "bat_highest": int(batting.get("highest", batting.get("hs", 0)) or 0),
        "bat_average": float(batting.get("average", batting.get("avg", 0)) or 0),
        "bat_strike_rate": float(batting.get("strike_rate", batting.get("sr", 0)) or 0),
        "bat_100s": int(batting.get("hundreds", batting.get("100s", 0)) or 0),
        "bat_50s": int(batting.get("fifties", batting.get("50s", 0)) or 0),
        "bat_4s": int(batting.get("fours", batting.get("4s", 0)) or 0),
        "bat_6s": int(batting.get("sixes", batting.get("6s", 0)) or 0),
        "bowl_matches": int(bowling.get("matches", bowling.get("mat", 0)) or 0),
        "bowl_innings": int(bowling.get("innings", bowling.get("inn", 0)) or 0),
        "bowl_wickets": int(bowling.get("wickets", bowling.get("wkts", 0)) or 0),
        "bowl_average": float(bowling.get("average", bowling.get("avg", 0)) or 0),
        "bowl_economy": float(bowling.get("economy", bowling.get("econ", 0)) or 0),
        "bowl_best": str(bowling.get("best", bowling.get("best_bowling", "")) or ""),
        "catches": int(fielding.get("catches", 0) or 0),
        "run_outs": int(fielding.get("run_outs", fielding.get("runouts", 0)) or 0),
        "stumpings": int(fielding.get("stumpings", 0) or 0),
        "source": "elitesport_api",
    }
    if stats["bat_matches"] == 0 and stats["bowl_wickets"] == 0:
        return None
    return stats


async def scrape_all_players(
    players: list[dict], api_key: str = "",
) -> list[dict]:
    """Fetch stats for a list of players via EliteSport API."""
    results = []
    if not api_key:
        logger.warning("No EliteSport API key, skipping API scrape")
        return [{"player_id": p["player_id"], "source": "no_api_key"} for p in players]

    async with aiohttp.ClientSession() as session:
        for player in players:
            name = player["name"]
            pid = player.get("player_id", "?")
            logger.info("Fetching stats for %s (%s)...", name, pid)
            stats = await search_and_fetch_player(name, api_key, session)
            if stats:
                stats["player_id"] = pid
                results.append(stats)
                logger.info("  Got %s: avg=%.1f, sr=%.1f, wkts=%d",
                            name, stats.get("bat_average", 0),
                            stats.get("bat_strike_rate", 0),
                            stats.get("bowl_wickets", 0))
            else:
                logger.warning("  No stats for %s", name)
                results.append({"player_id": pid, "source": "not_found"})
            await asyncio.sleep(RATE_LIMIT_DELAY)
    return results


async def scrape_from_api(
    players: list[dict], api_key: str,
) -> tuple[int, int]:
    """Scrape all players from EliteSport API and save to DB."""
    results = await scrape_all_players(players, api_key)
    saved = 0
    for stats in results:
        if stats.get("source") not in ("not_found", "no_api_key"):
            await save_stats_to_db(stats["player_id"], stats)
            saved += 1
    return len(players), saved


# ── DB Storage ────────────────────────────────────────────────────

async def save_stats_to_db(player_id: str, stats: dict) -> None:
    """Save scraped stats to the player_stats table."""
    from app.database.session import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO player_stats (
                    player_id, bat_matches, bat_innings, bat_runs, bat_highest,
                    bat_average, bat_strike_rate, bat_100s, bat_50s, bat_4s, bat_6s,
                    bowl_matches, bowl_innings, bowl_wickets, bowl_average, bowl_economy,
                    bowl_best, catches, run_outs, stumpings,
                    last_updated, source
                ) VALUES (
                    :player_id, :bat_matches, :bat_innings, :bat_runs, :bat_highest,
                    :bat_average, :bat_strike_rate, :bat_100s, :bat_50s, :bat_4s, :bat_6s,
                    :bowl_matches, :bowl_innings, :bowl_wickets, :bowl_average, :bowl_economy,
                    :bowl_best, :catches, :run_outs, :stumpings,
                    NOW(), :source
                )
                ON CONFLICT (player_id) DO UPDATE SET
                    bat_matches = EXCLUDED.bat_matches,
                    bat_innings = EXCLUDED.bat_innings,
                    bat_runs = EXCLUDED.bat_runs,
                    bat_highest = EXCLUDED.bat_highest,
                    bat_average = EXCLUDED.bat_average,
                    bat_strike_rate = EXCLUDED.bat_strike_rate,
                    bat_100s = EXCLUDED.bat_100s,
                    bat_50s = EXCLUDED.bat_50s,
                    bat_4s = EXCLUDED.bat_4s,
                    bat_6s = EXCLUDED.bat_6s,
                    bowl_matches = EXCLUDED.bowl_matches,
                    bowl_innings = EXCLUDED.bowl_innings,
                    bowl_wickets = EXCLUDED.bowl_wickets,
                    bowl_average = EXCLUDED.bowl_average,
                    bowl_economy = EXCLUDED.bowl_economy,
                    bowl_best = EXCLUDED.bowl_best,
                    catches = EXCLUDED.catches,
                    run_outs = EXCLUDED.run_outs,
                    stumpings = EXCLUDED.stumpings,
                    last_updated = NOW(),
                    source = EXCLUDED.source
            """), {
                "player_id": player_id,
                "bat_matches": stats.get("bat_matches", 0),
                "bat_innings": stats.get("bat_innings", 0),
                "bat_runs": stats.get("bat_runs", 0),
                "bat_highest": stats.get("bat_highest", 0),
                "bat_average": stats.get("bat_average", 0),
                "bat_strike_rate": stats.get("bat_strike_rate", 0),
                "bat_100s": stats.get("bat_100s", 0),
                "bat_50s": stats.get("bat_50s", 0),
                "bat_4s": stats.get("bat_4s", 0),
                "bat_6s": stats.get("bat_6s", 0),
                "bowl_matches": stats.get("bowl_matches", 0),
                "bowl_innings": stats.get("bowl_innings", 0),
                "bowl_wickets": stats.get("bowl_wickets", 0),
                "bowl_average": stats.get("bowl_average", 0),
                "bowl_economy": stats.get("bowl_economy", 0),
                "bowl_best": stats.get("bowl_best", ""),
                "catches": stats.get("catches", 0),
                "run_outs": stats.get("run_outs", 0),
                "stumpings": stats.get("stumpings", 0),
                "source": stats.get("source", "manual"),
            })
            await session.commit()
        logger.info("Saved stats for %s", player_id)
    except Exception as e:
        logger.error("Failed to save stats for %s: %s", player_id, e)


async def load_stats_from_db(player_id: str) -> Optional[dict]:
    """Load cached stats from player_stats table."""
    from app.database.session import AsyncSessionLocal
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM player_stats WHERE player_id = :pid"),
                {"pid": player_id},
            )
            row = result.mappings().first()
            if row:
                return dict(row)
    except Exception:
        pass
    return None


# ── CSV Import ────────────────────────────────────────────────────

async def import_stats_from_csv(csv_path: str) -> tuple[int, int]:
    """Import player stats from a CSV file into the player_stats table."""
    from app.database.session import AsyncSessionLocal
    from sqlalchemy import text
    total = 0
    saved = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv_mod.DictReader(f)
        rows = list(reader)

    total = len(rows)
    async with AsyncSessionLocal() as session:
        for row in rows:
            try:
                await session.execute(text("""
                    INSERT INTO player_stats (
                        player_id, bat_matches, bat_innings, bat_runs, bat_highest,
                        bat_average, bat_strike_rate, bat_100s, bat_50s, bat_4s, bat_6s,
                        bowl_matches, bowl_innings, bowl_wickets, bowl_average, bowl_economy,
                        bowl_best, catches, run_outs, stumpings,
                        last_updated, source
                    ) VALUES (
                        :player_id, :bat_matches, :bat_innings, :bat_runs, :bat_highest,
                        :bat_average, :bat_strike_rate, :bat_100s, :bat_50s, :bat_4s, :bat_6s,
                        :bowl_matches, :bowl_innings, :bowl_wickets, :bowl_average, :bowl_economy,
                        :bowl_best, :catches, :run_outs, :stumpings,
                        NOW(), :source
                    )
                    ON CONFLICT (player_id) DO UPDATE SET
                        bat_matches = EXCLUDED.bat_matches,
                        bat_innings = EXCLUDED.bat_innings,
                        bat_runs = EXCLUDED.bat_runs,
                        bat_highest = EXCLUDED.bat_highest,
                        bat_average = EXCLUDED.bat_average,
                        bat_strike_rate = EXCLUDED.bat_strike_rate,
                        bat_100s = EXCLUDED.bat_100s,
                        bat_50s = EXCLUDED.bat_50s,
                        bat_4s = EXCLUDED.bat_4s,
                        bat_6s = EXCLUDED.bat_6s,
                        bowl_matches = EXCLUDED.bowl_matches,
                        bowl_innings = EXCLUDED.bowl_innings,
                        bowl_wickets = EXCLUDED.bowl_wickets,
                        bowl_average = EXCLUDED.bowl_average,
                        bowl_economy = EXCLUDED.bowl_economy,
                        bowl_best = EXCLUDED.bowl_best,
                        catches = EXCLUDED.catches,
                        run_outs = EXCLUDED.run_outs,
                        stumpings = EXCLUDED.stumpings,
                        last_updated = NOW(),
                        source = EXCLUDED.source
                """), {
                    "player_id": row["player_id"],
                    "bat_matches": int(row.get("bat_matches", 0)),
                    "bat_innings": int(row.get("bat_innings", 0)),
                    "bat_runs": int(row.get("bat_runs", 0)),
                    "bat_highest": int(row.get("bat_highest", 0)),
                    "bat_average": float(row.get("bat_average", 0)),
                    "bat_strike_rate": float(row.get("bat_strike_rate", 0)),
                    "bat_100s": int(row.get("bat_100s", 0)),
                    "bat_50s": int(row.get("bat_50s", 0)),
                    "bat_4s": int(row.get("bat_4s", 0)),
                    "bat_6s": int(row.get("bat_6s", 0)),
                    "bowl_matches": int(row.get("bowl_matches", 0)),
                    "bowl_innings": int(row.get("bowl_innings", 0)),
                    "bowl_wickets": int(row.get("bowl_wickets", 0)),
                    "bowl_average": float(row.get("bowl_average", 0)),
                    "bowl_economy": float(row.get("bowl_economy", 0)),
                    "bowl_best": row.get("bowl_best", "0/0"),
                    "catches": int(row.get("catches", 0)),
                    "run_outs": int(row.get("run_outs", 0)),
                    "stumpings": int(row.get("stumpings", 0)),
                    "source": row.get("source", "csv_import"),
                })
                saved += 1
            except Exception as e:
                logger.error("Failed to import stats for %s: %s", row.get("player_id"), e)
        await session.commit()

    logger.info("Imported %d/%d player stats from CSV", saved, total)
    return total, saved
