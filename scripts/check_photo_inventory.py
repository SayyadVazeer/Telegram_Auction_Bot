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


def main():
    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        csv_player_ids = {
            row["player_id"].strip()
            for row in reader
        }

    photo_player_ids = set()

    for photo in PHOTOS_DIR.iterdir():
        if not photo.is_file():
            continue

        if photo.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        photo_player_ids.add(photo.stem)

    extra_photos = sorted(
        photo_player_ids - csv_player_ids
    )

    if extra_photos:
        print("Extra photos found:")

        for player_id in extra_photos:
            print(f"- {player_id}")

        print(
            f"\nTotal extra photos: {len(extra_photos)}"
        )
    else:
        print("No extra player photos found.")


if __name__ == "__main__":
    main()
