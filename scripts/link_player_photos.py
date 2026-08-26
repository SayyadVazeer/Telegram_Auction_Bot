import asyncio
from pathlib import Path

from sqlalchemy import select

from app.database.models import Player
from app.database.session import AsyncSessionLocal


PHOTOS_DIR = Path("data/photos")

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


def find_photo(player_id: str) -> Path | None:
    for extension in SUPPORTED_EXTENSIONS:
        path = PHOTOS_DIR / f"{player_id}{extension}"

        if path.is_file():
            return path

    return None


async def link_player_photos():
    linked = 0
    already_linked = 0
    missing = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Player).order_by(Player.player_id)
        )

        players = result.scalars().all()

        for player in players:
            photo = find_photo(player.player_id)

            if photo is None:
                missing += 1
                print(
                    f"PHOTO MISSING: {player.player_id}"
                )
                continue

            photo_path = str(photo)

            if player.telegram_photo_path == photo_path:
                already_linked += 1
                continue

            player.telegram_photo_path = photo_path
            linked += 1

        await session.commit()

    print()
    print(f"Players checked: {len(players)}")
    print(f"Photos linked: {linked}")
    print(f"Already linked: {already_linked}")
    print(f"Photos missing: {missing}")


def main():
    asyncio.run(link_player_photos())


if __name__ == "__main__":
    main()
