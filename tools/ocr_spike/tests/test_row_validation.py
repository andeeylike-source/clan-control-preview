"""
Row validation tests.
Covers: kills recovery from x-zone, needsReview on missing kills,
mixed-script name detection, complete rows passing clean.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import parser

WIDTH = 1000

# Column x-zone midpoints (mirrors _default_columns ratios)
_NAME_CX = int(WIDTH * 0.20)
_KILLS_CX = int(WIDTH * 0.54)
_DEATHS_CX = int(WIDTH * 0.65)
_PVP_CX = int(WIDTH * 0.775)
_PVE_CX = int(WIDTH * 0.93)


def _box(text: str, cx: int, cy: int = 100) -> dict:
    hw = max(len(text) * 6, 20)
    return {
        "text": text, "confidence": 0.99,
        "bbox": [cx - hw, cy - 15, cx + hw, cy + 15],
        "cx": float(cx), "cy": float(cy),
    }


def _row(*boxes_spec: tuple[str, int], cy: int = 100) -> list[dict]:
    """Build a list of boxes from (text, cx_zone) pairs at the given cy."""
    return [_box(text, cx_zone, cy) for text, cx_zone in boxes_spec]


def test_kills_missing_sets_needs_review():
    """Row where kills column has no OCR box gets needsReview.
    Uses a name not in LIVE_CHRISTMAS_KILLS so _repair does not backfill kills."""
    boxes = _row(
        ("Xan", _NAME_CX),      # in known_names, not in LIVE_CHRISTMAS_KILLS
        # kills box intentionally absent
        ("7", _DEATHS_CX),
        ("300", _PVP_CX),
        ("55", _PVE_CX),
    )
    rows = parser.parse_rows(boxes, image_width=WIDTH)
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
    row = rows[0]
    assert row.get("needsReview") is True, "needsReview must be True when kills is absent"
    assert row["kills"] is None, f"kills should remain None, got {row['kills']}"
    assert row["deaths"] == 7
    assert row["pvpDamage"] == 300
    assert row["pveDamage"] == 55


def test_complete_row_no_numeric_needs_review():
    """Row with all 4 numeric columns present must not have needsReview from numeric validation."""
    boxes = _row(
        ("Scotty", _NAME_CX),
        ("11", _KILLS_CX),
        ("18", _DEATHS_CX),
        ("120", _PVP_CX),
        ("91", _PVE_CX),
    )
    rows = parser.parse_rows(boxes, image_width=WIDTH)
    assert len(rows) == 1
    row = rows[0]
    assert row["kills"] == 11
    assert row["kills"] is not None
    # needsReview must NOT be set due to numeric issues
    # (name Scotty is in known_names, so no name review either)
    assert not row.get("needsReview"), f"Unexpected needsReview on complete row: {row}"


def test_mixed_script_name_sets_needs_review():
    """Name with mixed latin+cyrillic (OCR artifact) gets needsReview.
    'Sсotty': S is LATIN, с is CYRILLIC SMALL LETTER ES — looks identical but mixed script."""
    # U+0053 (LATIN S) + U+0441 (CYRILLIC с) + "otty"
    mixed = "Sсotty"
    assert parser.has_mixed_latin_cyrillic(mixed), "prerequisite: input is mixed script"
    boxes = _row(
        (mixed, _NAME_CX),
        ("11", _KILLS_CX),
        ("18", _DEATHS_CX),
        ("120", _PVP_CX),
        ("91", _PVE_CX),
    )
    rows = parser.parse_rows(boxes, image_width=WIDTH)
    assert len(rows) == 1
    row = rows[0]
    assert row.get("needsReview") is True, (
        f"Mixed-script name must trigger needsReview; row={row}"
    )


def test_unknown_name_no_roster_match_needs_review():
    """Completely unknown name with no roster match gets needsReview."""
    boxes = _row(
        ("xZq99FooBarBazUnknown", _NAME_CX),
        ("5", _KILLS_CX),
        ("10", _DEATHS_CX),
        ("100", _PVP_CX),
        ("50", _PVE_CX),
    )
    rows = parser.parse_rows(boxes, image_width=WIDTH)
    assert len(rows) == 1
    row = rows[0]
    assert row.get("needsReview") is True


def test_kills_zero_not_flagged_as_missing():
    """kills=0 (legitimate) must NOT trigger needsReview from numeric validation."""
    boxes = _row(
        ("IDeathI", _NAME_CX),
        ("0", _KILLS_CX),
        ("13", _DEATHS_CX),
        ("0", _PVP_CX),
        ("2", _PVE_CX),
    )
    rows = parser.parse_rows(boxes, image_width=WIDTH)
    assert len(rows) == 1
    row = rows[0]
    assert row["kills"] == 0
    assert not row.get("needsReview"), f"kills=0 should not trigger needsReview: {row}"


def test_ocr_garbled_name_resolves_via_skeleton():
    """boxbaKapa (OCR of БожьяКара) resolves correctly when БожьяКара is in known_names."""
    boxes = _row(
        ("boxbaKapa", _NAME_CX),
        ("5", _KILLS_CX),
        ("21", _DEATHS_CX),
        ("80", _PVP_CX),
        ("1145", _PVE_CX),
    )
    rows = parser.parse_rows(boxes, image_width=WIDTH)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "БожьяКара", f"Expected БожьяКара, got {row['name']!r}"
    assert not row.get("needsReview"), "Resolved name should not have needsReview"


def test_deaths_box_at_cx672_width1122_not_in_kills_zone():
    """Header-calibrated detection: deaths box at cx=672 must land in deaths, not kills.

    Live file 4 (width=1122): X header at cx=572, no C header.
    Fixed-ratio boundary was 673.2px, putting cx=672 in kills zone by 1px.
    Header detection infers deaths=[632, 742], kills=[512, 632].
    """
    W = 1122
    # Header row at cy=30, data row at cy=100
    header_boxes = [
        _box("4neh rpynnbl", 216, 30),
        _box("X", 572, 30),
        _box("PvP ypoH", 834, 30),
        _box("PvE ypoH", 1000, 30),
    ]
    data_boxes = [
        _box("BloodMather", 146, 100),
        _box("12", 564, 100),
        _box("9", 672, 100),
        _box("203", 809, 100),
        _box("767", 976, 100),
    ]
    rows = parser.parse_rows(header_boxes + data_boxes, image_width=W)
    blood_rows = [r for r in rows if "Blood" in r.get("name", "")]
    assert blood_rows, f"BloodMather row not found in {rows}"
    row = blood_rows[0]
    assert row["kills"] == 12, f"kills expected 12, got {row['kills']}"
    assert row["deaths"] == 9, f"deaths expected 9, got {row['deaths']}"
    assert row["pvpDamage"] == 203
    assert row["pveDamage"] == 767
