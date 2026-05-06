"""
Name resolution tests.
Covers: cyrillic nick recovery from OCR-garbled latin input,
exact roster match preservation, and unresolvable garbage handling.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import parser

ROSTER = [
    "Christmas", "БожьяКара", "Ks4ndars", "TANb4A", "iAcTpO", "IDeathI",
    "Scotty", "мефедрон", "Terran", "БратРевыч", "Джейк", "ВИЗАРД",
    "Шут", "Умра", "Акс", "бусь",
]


def _ok(raw: str, expected: str) -> None:
    r = parser.resolve_name(raw, ROSTER, {})
    assert r["resolvedName"] == expected, (
        f"{raw!r}: expected {expected!r}, got {r['resolvedName']!r} via {r['method']}"
    )
    assert not r["needsReview"], f"{raw!r} unexpectedly got needsReview (method={r['method']})"


def _review(raw: str) -> None:
    r = parser.resolve_name(raw, ROSTER, {})
    assert r["needsReview"], f"{raw!r}: expected needsReview but got resolvedName={r['resolvedName']!r}"


# --- positive: OCR-garbled cyrillic nicks ------------------------------------

def test_boxbakapa_resolves():
    _ok("boxbaKapa", "БожьяКара")


def test_bowbakapa_resolves():
    _ok("BowbaKapa", "БожьяКара")


def test_bratrewych_resolves():
    _ok("BpaTPeebl4", "БратРевыч")


def test_akek_resolves_to_jake():
    _ok("Akek", "Джейк")


# --- positive: normal roster names preserved as-is --------------------------

def test_latin_names_not_corrupted():
    for name in ("Christmas", "Scotty", "Terran", "Ks4ndars", "TANb4A", "iAcTpO", "IDeathI"):
        _ok(name, name)


def test_mixed_script_like_nicks_preserved():
    # latin+digits nicks that are in roster must not be corrupted
    _ok("Ks4ndars", "Ks4ndars")
    _ok("TANb4A", "TANb4A")


# --- negative: unknown names with no roster match ---------------------------

def test_garbage_latin_needs_review():
    _review("xZq99FooBarBazUnknown")


def test_short_garbage_needs_review():
    _review("Qqz")


def test_empty_name_needs_review():
    r = parser.resolve_name("", ROSTER, {})
    assert r["needsReview"]
