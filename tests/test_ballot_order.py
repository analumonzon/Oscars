import csv
from pathlib import Path

from app.ballot_loader import load_ballot


def _expected_category_order(csv_path: Path) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if any(cell.strip() for cell in row)]

    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    has_header = any(keyword in " ".join(header) for keyword in ("category", "nominee", "points"))
    data_rows = rows[1:] if has_header else rows

    seen: set[str] = set()
    ordered: list[str] = []

    for row in data_rows:
        if len(row) < 1:
            continue
        category = row[0].strip()
        if not category or category in seen:
            continue
        seen.add(category)
        ordered.append(category)

    return ordered


def test_ballot_category_order_matches_csv() -> None:
    csv_path = Path("docs/OscarBallotList.csv")
    ballot = load_ballot(csv_path)

    expected = _expected_category_order(csv_path)
    actual = [category["name"] for category in ballot]

    assert actual == expected
