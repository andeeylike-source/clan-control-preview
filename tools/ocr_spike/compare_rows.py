from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FIELDS = ("name", "kills", "deaths", "pvpDamage", "pveDamage")


def load_rows(path: Path, actual: bool) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if actual:
        rows = data.get("rows") if isinstance(data, dict) else None
    else:
        rows = data
    if not isinstance(rows, list):
        raise ValueError(f"{path} does not contain a rows list")
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Compare OCR parsed rows against expected rows.")
    parser.add_argument("--actual", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=Path)
    args = parser.parse_args()

    actual_rows = load_rows(args.actual, actual=True)
    expected_rows = load_rows(args.expected, actual=False)

    mismatches: list[dict[str, Any]] = []
    matched_rows = 0
    total_rows = max(len(actual_rows), len(expected_rows))

    for index in range(total_rows):
        actual_row = actual_rows[index] if index < len(actual_rows) else None
        expected_row = expected_rows[index] if index < len(expected_rows) else None

        if actual_row is None or expected_row is None:
            mismatches.append(
                {
                    "row": index,
                    "field": "__row__",
                    "expected": expected_row,
                    "actual": actual_row,
                }
            )
            continue

        row_mismatches = []
        for field in FIELDS:
            if actual_row.get(field) != expected_row.get(field):
                row_mismatches.append(
                    {
                        "row": index,
                        "field": field,
                        "expected": expected_row.get(field),
                        "actual": actual_row.get(field),
                    }
                )
        if row_mismatches:
            mismatches.extend(row_mismatches)
        else:
            matched_rows += 1

    result = {
        "total_rows": total_rows,
        "actual_rows": len(actual_rows),
        "expected_rows": len(expected_rows),
        "matched_rows": matched_rows,
        "field_mismatches": mismatches,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
