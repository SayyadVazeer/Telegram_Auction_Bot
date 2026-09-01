from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.team import Team


async def get_team_by_name(
    session: AsyncSession,
    tournament_id: int,
    name: str,
) -> Team | None:
    result = await session.execute(
        select(Team).where(
            Team.tournament_id == tournament_id,
            Team.name == name,
        )
    )

    return result.scalar_one_or_none()


async def get_team_by_short_code(
    session: AsyncSession,
    tournament_id: int,
    short_code: str,
) -> Team | None:
    result = await session.execute(
        select(Team).where(
            Team.tournament_id == tournament_id,
            Team.short_code == short_code,
        )
    )

    return result.scalar_one_or_none()


async def create_team(
    session: AsyncSession,
    *,
    tournament_id: int,
    name: str,
    short_code: str,
) -> Team:
    team = Team(
        tournament_id=tournament_id,
        name=name,
        short_code=short_code,
    )

    session.add(team)

    await session.flush()

    return team


async def get_teams_by_tournament(
    session: AsyncSession,
    tournament_id: int,
) -> list[Team]:
    result = await session.execute(
        select(Team)
        .where(Team.tournament_id == tournament_id)
        .order_by(Team.id)
    )

    return list(result.scalars().all())

async def get_team_by_id(
    session: AsyncSession,
    team_id: int,
) -> Team | None:
    return await session.get(Team, team_id)


async def get_team_by_owner(
    session: AsyncSession,
    tournament_id: int,
    owner_telegram_id: int,
) -> Team | None:
    result = await session.execute(
        select(Team).where(
            Team.tournament_id == tournament_id,
            Team.owner_telegram_id == owner_telegram_id,
        )
    )

    return result.scalar_one_or_none()


async def get_team_by_owner_or_coowner(
    session: AsyncSession,
    tournament_id: int,
    telegram_id: int,
) -> Team | None:
    """Find a team where the user is either the owner or co-owner."""
    result = await session.execute(
        select(Team).where(
            Team.tournament_id == tournament_id,
            (Team.owner_telegram_id == telegram_id)
            | (Team.co_owner_telegram_id == telegram_id),
        )
    )
    return result.scalar_one_or_none()


async def assign_team_owner(
    session: AsyncSession,
    team: Team,
    owner_telegram_id: int,
    owner_username: str | None,
) -> None:
    team.owner_telegram_id = owner_telegram_id
    team.owner_username = owner_username

    await session.flush()
