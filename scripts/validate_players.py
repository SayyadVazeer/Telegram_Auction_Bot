import csv
from pathlib import Path


CSV_PATH = Path("data/csv/players.csv")

REQUIRED_COLUMNS = {
    "name",
    "country",
    "role",
    "is_overseas",
    "set_number",
    "base_price_cr",
    "player_id",
}


def parse_bool(value: str) -> bool:
    value = value.strip().lower()

    if value in {"true", "1", "yes"}:
        return True

    if value in {"false", "0", "no"}:
        return False

    raise ValueError(f"Invalid boolean value: {value}")


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"CSV not found: {CSV_PATH}"
        )

    errors = []
    player_ids = set()
    rows = []

    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")

        columns = set(reader.fieldnames)

        missing = REQUIRED_COLUMNS - columns

        if missing:
            raise ValueError(
                f"Missing required columns: {sorted(missing)}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                player_id = row["player_id"].strip()
                name = row["name"].strip()
                country = row["country"].strip()
                role = row["role"].strip()

                if not player_id:
                    raise ValueError("player_id is empty")

                if not player_id.startswith("PLY"):
                    raise ValueError(
                        f"Invalid player_id: {player_id}"
                    )

                if player_id in player_ids:
                    raise ValueError(
                        f"Duplicate player_id: {player_id}"
                    )

                if not name:
                    raise ValueError("name is empty")

                if not country:
                    raise ValueError("country is empty")

                if not role:
                    raise ValueError("role is empty")

                is_overseas = parse_bool(
                    row["is_overseas"]
                )

                set_number = int(
                    row["set_number"].strip()
                )

                base_price_cr = float(
                    row["base_price_cr"].strip()
                )

                if set_number <= 0:
                    raise ValueError(
                        "set_number must be greater than 0"
                    )

                if base_price_cr < 0:
                    raise ValueError(
                        "base_price_cr cannot be negative"
                    )

                player_ids.add(player_id)

                rows.append(
                    {
                        "player_id": player_id,
                        "name": name,
                        "country": country,
                        "role": role,
                        "is_overseas": is_overseas,
                        "set_number": set_number,
                        "base_price_cr": base_price_cr,
                    }
                )

            except Exception as exc:
                errors.append(
                    f"Row {row_number}: {exc}"
                )

    print(f"Rows found: {len(rows)}")

    if errors:
        print("\nValidation errors:")
        for error in errors:
            print(f"- {error}")

        raise SystemExit(
            f"\nValidation failed with {len(errors)} error(s)."
        )

    print(f"Unique player IDs: {len(player_ids)}")
    print("\nCSV validation successful.")


if __name__ == "__main__":
    main()
