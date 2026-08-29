"""Migration: set telegram_photo_path for all players where it's NULL."""

import asyncio
import os
from sqlalchemy import select, update

from app.database.session import AsyncSessionLocal
from app.database.models.player import Player


async def fix_photo_paths():
    async with AsyncSessionLocal() as session:
        # Get all players with no photo path
        result = await session.execute(
            select(Player).where(Player.telegram_photo_path.is_(None))
        )
        players = result.scalars().all()

        updated = 0
        skipped = 0

        for player in players:
            photo_path = f"data/photos/{player.player_id}.jpg"
            if os.path.exists(photo_path):
                player.telegram_photo_path = photo_path
                updated += 1
            else:
                skipped += 1

        await session.commit()

    print(f"Players with NULL photo_path: {len(players)}")
    print(f"Updated: {updated}")
    print(f"No photo file found: {skipped}")


if __name__ == "__main__":
    asyncio.run(fix_photo_paths())
