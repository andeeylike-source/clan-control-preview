from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compare_rows import FIELDS, load_rows

CASES = [
    (
        "competitor_test_crop",
        Path(__file__).parent / "out" / "competitor_test_crop.paddle.4e9545a69b5b.json",
        Path(__file__).parent / "expected" / "competitor_test_crop.expected.json",
    ),
    (
        "second_test_crop",
        Path(__file__).parent / "out" / "second_test_crop.paddle.8a799bccf448.json",
        Path(__file__).parent / "expected" / "second_test_crop.expected.json",
    ),
    (
        "third_test_crop",
        Path(__file__).parent / "out" / "third_test_crop.paddle.233c74cd9808.json",
        Path(__file__).parent / "expected" / "third_test_crop.expected.json",
    ),
]


def run_case(name: str, actual_path: Path, expected_path: Path) -> dict:
    actual_rows = load_rows(actual_path, actual=True)
    expected_rows = load_rows(expected_path, actual=False)
    total = max(len(actual_rows), len(expected_rows))
    mismatches = []
    matched = 0

    for i in range(total):
        a = actual_rows[i] if i < len(actual_rows) else None
        e = expected_rows[i] if i < len(expected_rows) else None
        if a is None or e is None:
            mismatches.append({"row": i, "field": "__row__", "expected": e, "actual": a})
            continue
        row_mm = [
            {"row": i, "field": f, "expected": e.get(f), "actual": a.get(f)}
            for f in FIELDS if a.get(f) != e.get(f)
        ]
        if row_mm:
            mismatches.extend(row_mm)
        else:
            matched += 1

    return {"case": name, "total_rows": total, "matched_rows": matched,
            "mismatches": mismatches, "passed": not mismatches}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results = [run_case(n, a, e) for n, a, e in CASES]
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    print(f"\n=== regression_check: {passed}/{len(results)} passed ===\n")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['case']}  {r['matched_rows']}/{r['total_rows']} rows matched")
        for m in r["mismatches"]:
            print(f"         row={m['row']} field={m['field']} "
                  f"expected={m['expected']!r} actual={m['actual']!r}")

    print(f"\ntotal_cases={len(results)}  passed={passed}  failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
