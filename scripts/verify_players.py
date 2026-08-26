import csv
from pathlib import Path


CSV_PATH = Path("data/csv/players.csv")
PHOTOS_DIR = Path("data/photos")

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


def load_player_ids() -> list[str]:
    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        return [
            row["player_id"].strip()
            for row in reader
        ]


def find_photo(player_id: str) -> Path | None:
    for extension in SUPPORTED_EXTENSIONS:
        photo_path = PHOTOS_DIR / f"{player_id}{extension}"

        if photo_path.is_file():
            return photo_path

    return None


def main():
    if not CSV_PATH.is_file():
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}"
        )

    if not PHOTOS_DIR.is_dir():
        raise FileNotFoundError(
            f"Photos directory not found: {PHOTOS_DIR}"
        )

    player_ids = load_player_ids()

    missing = []
    found = []

    for player_id in player_ids:
        photo = find_photo(player_id)

        if photo is None:
            missing.append(player_id)
        else:
            found.append(photo)

    print(f"Players in CSV: {len(player_ids)}")
    print(f"Photos found: {len(found)}")
    print(f"Photos missing: {len(missing)}")

    if missing:
        print("\nMissing photos:")

        for player_id in missing:
            print(f"- {player_id}")

        raise SystemExit(
            f"\nPhoto verification failed: "
            f"{len(missing)} photo(s) missing."
        )

    print("\nAll player photos verified successfully.")


if __name__ == "__main__":
    main()
