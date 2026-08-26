import asyncio
import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.database.models import Player
from app.database.session import AsyncSessionLocal


CSV_PATH = Path("data/csv/players.csv")


def parse_bool(value: str) -> bool:
    value = value.strip().lower()

    if value in {"true", "1", "yes"}:
        return True

    if value in {"false", "0", "no"}:
        return False

    raise ValueError(f"Invalid boolean value: {value}")


def load_csv() -> list[dict]:
    if not CSV_PATH.is_file():
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}"
        )

    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        players = []

        for row_number, row in enumerate(
            reader,
            start=2,
        ):
            try:
                players.append(
                    {
                        "player_id": row["player_id"].strip(),
                        "name": row["name"].strip(),
                        "country": row["country"].strip(),
                        "role": row["role"].strip(),
                        "is_overseas": parse_bool(
                            row["is_overseas"]
                        ),
                        "set_number": int(
                            row["set_number"].strip()
                        ),
                        "base_price_cr": Decimal(
                            row["base_price_cr"].strip()
                        ),
                    }
                )
            except Exception as exc:
                raise ValueError(
                    f"Invalid CSV row {row_number}: {exc}"
                ) from exc

        return players


async def import_players():
    players = load_csv()

    inserted = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        existing_result = await session.execute(
            select(Player.player_id)
        )

        existing_ids = {
            player_id
            for player_id in existing_result.scalars()
        }

        for data in players:
            player_id = data["player_id"]

            if player_id in existing_ids:
                skipped += 1
                continue

            player = Player(
                player_id=data["player_id"],
                name=data["name"],
                country=data["country"],
                role=data["role"],
                is_overseas=data["is_overseas"],
                set_number=data["set_number"],
                base_price_cr=data["base_price_cr"],
            )

            session.add(player)
            existing_ids.add(player_id)

            inserted += 1

        await session.commit()

    print(f"CSV records: {len(players)}")
    print(f"Players inserted: {inserted}")
    print(f"Players skipped: {skipped}")
    print(
        f"Total processed: {inserted + skipped}"
    )


def main():
    asyncio.run(import_players())


if __name__ == "__main__":
    main()
