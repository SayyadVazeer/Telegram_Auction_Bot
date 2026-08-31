"""Tournament standings calculator.

Auto-calculates standings after every match:
- Points: Win=2, Tie=1, No Result=1, Loss=0
- NRR = (Runs_Faced/Balls_Faced) - (Runs_Conceded/Balls_Bowled) × 20/20
- Sorted by: Points (desc) → NRR (desc)
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import text
from app.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def ensure_standings_exist(tournament_id: int, team_ids: list[int]) -> None:
    """Ensure all teams have a standing row for this tournament."""
    async with AsyncSessionLocal() as session:
        for team_id in team_ids:
            await session.execute(text("""
                INSERT INTO tournament_standings (tournament_id, team_id)
                VALUES (:tid, :team_id)
                ON CONFLICT DO NOTHING
            """), {"tid": tournament_id, "team_id": team_id})
        await session.commit()


async def update_standings_after_match(
    tournament_id: int,
    match_id: int,
    batting_team_id: int,
    bowling_team_id: int,
    batting_runs: int,
    batting_balls: int,
    bowling_runs: int,
    bowling_balls: int,
    result_type: str,  # 'batting_team_won', 'bowling_team_won', 'tie', 'no_result'
) -> None:
    """Update standings after a match completes.

    Call this once per innings (twice per match) or once at end with totals.
    """
    async with AsyncSessionLocal() as session:
        # Update batting team stats
        await session.execute(text("""
            UPDATE tournament_standings SET
                matches_played = matches_played + 1,
                runs_for = runs_for + :runs,
                balls_faced = balls_faced + :balls,
                runs_against = runs_against + :conceded,
                balls_bowled = balls_bowled + :conceded_balls
            WHERE tournament_id = :tid AND team_id = :team_id
        """), {
            "tid": tournament_id,
            "team_id": batting_team_id,
            "runs": batting_runs,
            "balls": batting_balls,
            "conceded": bowling_runs,
            "conceded_balls": bowling_balls,
        })

        # Update bowling team stats (reverse: they conceded batting_runs, scored bowling_runs)
        await session.execute(text("""
            UPDATE tournament_standings SET
                runs_for = runs_for + :runs,
                balls_faced = balls_faced + :balls,
                runs_against = runs_against + :conceded,
                balls_bowled = balls_bowled + :conceded_balls
            WHERE tournament_id = :tid AND team_id = :team_id
        """), {
            "tid": tournament_id,
            "team_id": bowling_team_id,
            "runs": bowling_runs,
            "balls": bowling_balls,
            "conceded": batting_runs,
            "conceded_balls": batting_balls,
        })

        # Update points
        if "won" in result_type:
            if result_type.startswith("batting"):
                winner_id = batting_team_id
                loser_id = bowling_team_id
            else:
                winner_id = bowling_team_id
                loser_id = batting_team_id

            await session.execute(text("""
                UPDATE tournament_standings SET
                    wins = wins + 1, points = points + 2
                WHERE tournament_id = :tid AND team_id = :wid
            """), {"tid": tournament_id, "wid": winner_id})

            await session.execute(text("""
                UPDATE tournament_standings SET losses = losses + 1
                WHERE tournament_id = :tid AND team_id = :lid
            """), {"tid": tournament_id, "lid": loser_id})
        elif result_type == "tie":
            await session.execute(text("""
                UPDATE tournament_standings SET
                    ties = ties + 1, points = points + 1
                WHERE tournament_id = :tid AND team_id IN (:t1, :t2)
            """), {"tid": tournament_id, "t1": batting_team_id, "t2": bowling_team_id})
        elif result_type == "no_result":
            await session.execute(text("""
                UPDATE tournament_standings SET
                    no_result = no_result + 1, points = points + 1
                WHERE tournament_id = :tid AND team_id IN (:t1, :t2)
            """), {"tid": tournament_id, "t1": batting_team_id, "t2": bowling_team_id})

        # Recalculate NRR for all teams
        await _recalculate_nrr(session, tournament_id)

        await session.commit()


async def _recalculate_nrr(session, tournament_id: int) -> None:
    """Recalculate Net Run Rate for all teams in a tournament."""
    await session.execute(text("""
        UPDATE tournament_standings SET nrr = CASE
            WHEN balls_faced > 0 AND balls_bowled > 0 THEN
                ROUND(
                    (runs_for::float / balls_faced * 20) - (runs_against::float / balls_bowled * 20),
                    3
                )
            ELSE 0.000
        END
        WHERE tournament_id = :tid
    """), {"tid": tournament_id})


async def get_standings(tournament_id: int) -> list[dict]:
    """Get current tournament standings sorted by points then NRR."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT
                ts.team_id,
                t.name as team_name,
                t.short_code,
                ts.matches_played,
                ts.wins,
                ts.losses,
                ts.ties,
                ts.no_result,
                ts.runs_for,
                ts.balls_faced,
                ts.runs_against,
                ts.balls_bowled,
                ts.points,
                ts.nrr
            FROM tournament_standings ts
            JOIN teams t ON t.id = ts.team_id
            WHERE ts.tournament_id = :tid
            ORDER BY ts.points DESC, ts.nrr DESC
        """), {"tid": tournament_id})

        rows = result.mappings().all()
        return [dict(row) for row in rows]


async def format_standings(tournament_id: int) -> str:
    """Format standings as a nice message."""
    standings = await get_standings(tournament_id)
    if not standings:
        return "No standings available."

    lines = ["🏆 **Tournament Standings**", ""]
    lines.append(f"{'#':<3} {'Team':<15} {'P':>3} {'W':>3} {'L':>3} {'T':>3} {'PTS':>4} {'NRR':>8}")
    lines.append("─" * 45)

    for i, row in enumerate(standings, 1):
        nrr = float(row.get("nrr", 0) or 0)
        lines.append(
            f"{i:<3} {row['team_name']:<15} "
            f"{row['matches_played']:>3} "
            f"{row['wins']:>3} "
            f"{row['losses']:>3} "
            f"{row['ties']:>3} "
            f"{row['points']:>4} "
            f"{nrr:>+8.3f}"
        )

    return "\n".join(lines)


async def get_team_stats(tournament_id: int, team_id: int) -> dict:
    """Get detailed stats for a single team."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT * FROM tournament_standings
            WHERE tournament_id = :tid AND team_id = :team_id
        """), {"tid": tournament_id, "team_id": team_id})
        row = result.mappings().first()
        return dict(row) if row else {}
