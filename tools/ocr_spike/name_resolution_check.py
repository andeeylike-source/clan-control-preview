from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parser


POSITIVE_CASES = [
    ("boxbaKapa", "БожьяКара"),
    ("BowbaKapa", "БожьяКара"),
    ("BpaTPeebl4", "БратРевыч"),
    ("Akek", "Джейк"),
    ("BM3APA", "ВИЗАРД"),
    ("WyT", "Шут"),
    ("Ympa", "Умра"),
    ("AKC", "Акс"),
    ("Christmas", "Christmas"),
    ("VelvetRemedy", "VelvetRemedy"),
    ("Ks4ndars", "Ks4ndars"),
    ("TANb4A", "TANb4A"),
    ("iAcTpO", "iAcTpO"),
    ("IDeathI", "IDeathI"),
    ("Scotty", "Scotty"),
    ("Terran", "Terran"),
]

NEGATIVE_CASES = [
    "UnknownGarbage",
    "RandomLatinNick",
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    roster = parser._load_known_names() + ["VelvetRemedy"]
    failed = 0

    print("\n=== name_resolution_check ===\n")
    for raw, expected in POSITIVE_CASES:
        result = parser.resolve_name(raw, roster, {})
        ok = result["resolvedName"] == expected and not result["needsReview"]
        failed += 0 if ok else 1
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {raw!r} -> {result['resolvedName']!r} method={result['method']}")

    for raw in NEGATIVE_CASES:
        result = parser.resolve_name(raw, roster, {})
        ok = result["needsReview"] and result["resolvedName"] == raw
        failed += 0 if ok else 1
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {raw!r} unresolved method={result['method']}")

    total = len(POSITIVE_CASES) + len(NEGATIVE_CASES)
    print(f"\ntotal_cases={total}  passed={total - failed}  failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
