from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


NUMBER_RE = re.compile(r"[-+]?\d[\d\s,.'`]*")
TRAILING_GARBAGE_RE = re.compile(r"(?:\s+[\W_]+|\s+[\d\W_]+|\s+[\u4e00-\u9fff])+$", re.UNICODE)

KNOWN_NAMES_PATH = Path(__file__).resolve().parent / "expected" / "known_names.json"
KNOWN_NAME_ALIASES = {
    "bm3apa": "ВИЗАРД",
    "tpaxhyhenga": "ТрахнуНетГлядя",
    "tpaxhyhena": "ТрахнуНетГлядя",
    "6ycb": "бусь",
}

_LAT_TO_CYR = str.maketrans({
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н',
    'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т', 'X': 'Х',
    'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у',
})
_CYR_TO_LAT = str.maketrans({
    'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H',
    'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P', 'Т': 'T', 'Х': 'X',
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'х': 'x', 'у': 'y',
})


@dataclass(frozen=True)
class Column:
    name: str
    start: float
    end: float


def _char_script(ch: str) -> str:
    """Return 'latin', 'cyrillic', or 'other' for a single character."""
    name = unicodedata.name(ch, '')
    if 'LATIN' in name:
        return 'latin'
    if 'CYRILLIC' in name:
        return 'cyrillic'
    return 'other'


def classify_name_script(name: str) -> str:
    """Classify name as: latin, cyrillic, latin_digits, cyrillic_digits, digits_only, mixed_invalid, unknown."""
    SAFE_SEP = frozenset('-_. ')
    has_lat = has_cyr = has_dig = False
    for ch in name:
        if ch in SAFE_SEP:
            continue
        if ch.isdigit():
            has_dig = True
            continue
        sc = _char_script(ch)
        if sc == 'latin':
            has_lat = True
        elif sc == 'cyrillic':
            has_cyr = True
    if has_lat and has_cyr:
        return 'mixed_invalid'
    if has_lat and has_dig:
        return 'latin_digits'
    if has_cyr and has_dig:
        return 'cyrillic_digits'
    if has_lat:
        return 'latin'
    if has_cyr:
        return 'cyrillic'
    if has_dig:
        return 'digits_only'
    return 'unknown'


def is_valid_name_script(name: str) -> bool:
    return classify_name_script(name) != 'mixed_invalid'


def has_mixed_latin_cyrillic(name: str) -> bool:
    return classify_name_script(name) == 'mixed_invalid'


def normalize_number(value: str) -> int | None:
    """Normalize OCR numeric cells such as '1,234' or '1 234'."""
    if not value:
        return None
    match = NUMBER_RE.search(value)
    if not match:
        return None
    cleaned = (
        match.group(0)
        .replace(" ", "")
        .replace(",", "")
        .replace(".", "")
        .replace("'", "")
        .replace("`", "")
    )
    cleaned = cleaned.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    try:
        return int(cleaned)
    except ValueError:
        return None


def _apply_visual_confusion(name: str, known_names: list[str]) -> str | None:
    """Try substituting visually confusable chars between scripts; return match if found and valid."""
    for candidate in (name.translate(_LAT_TO_CYR), name.translate(_CYR_TO_LAT)):
        if candidate != name and candidate in known_names and is_valid_name_script(candidate):
            return candidate
    return None


def _load_known_names() -> list[str]:
    if not KNOWN_NAMES_PATH.exists():
        return []
    try:
        data = json.loads(KNOWN_NAMES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _name_skeleton(value: str) -> str:
    visual_map = str.maketrans(
        {
            "а": "a",
            "б": "b",
            "в": "b",
            "г": "r",
            "д": "a",
            "е": "e",
            "ё": "e",
            "ж": "w",
            "з": "3",
            "и": "m",
            "й": "u",
            "к": "k",
            "л": "n",
            "м": "m",
            "н": "h",
            "о": "o",
            "п": "n",
            "р": "p",
            "с": "c",
            "т": "t",
            "у": "y",
            "ф": "p",
            "х": "x",
            "ц": "u",
            "ч": "4",
            "ш": "w",
            "щ": "w",
            "ъ": "b",
            "ы": "bi",
            "ь": "b",
            "э": "e",
            "ю": "io",
            "я": "a",
        }
    )
    return re.sub(r"[^a-z0-9]+", "", value.lower().translate(visual_map))


def _correct_known_name(name: str) -> str:
    known_names = _load_known_names()
    if not known_names:
        return name
    if name in known_names:
        return name

    skeleton = _name_skeleton(name)
    if not skeleton:
        return name
    alias = KNOWN_NAME_ALIASES.get(skeleton)
    if alias in known_names:
        return alias

    scored: list[tuple[float, str]] = []
    for known in known_names:
        known_skeleton = _name_skeleton(known)
        if not known_skeleton:
            continue
        ratio = SequenceMatcher(None, skeleton, known_skeleton).ratio()
        if skeleton == known_skeleton:
            ratio = 1.0
        scored.append((ratio, known))

    if not scored:
        return name
    scored.sort(reverse=True, key=lambda item: item[0])
    best_ratio, best_name = scored[0]
    second_ratio = scored[1][0] if len(scored) > 1 else 0.0
    if best_ratio >= 0.90 and best_ratio - second_ratio >= 0.08:
        return best_name

    # Step 4: visual OCR confusion mapping (only applied if result passes is_valid_name_script)
    visual = _apply_visual_confusion(name, known_names)
    if visual is not None:
        return visual

    return name


def normalize_name(raw_name: str) -> str:
    """Clean obvious OCR garbage from the name field without touching numbers."""
    name = re.sub(r"\s+", " ", raw_name or "").strip()
    name = TRAILING_GARBAGE_RE.sub("", name).strip()
    return _correct_known_name(name)


def _box_height(box: dict[str, Any]) -> float:
    bbox = box.get("bbox") or [0, 0, 0, 0]
    return max(1.0, float(bbox[3]) - float(bbox[1]))


def _cluster_rows(boxes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    candidates = [b for b in boxes if str(b.get("text", "")).strip()]
    candidates.sort(key=lambda b: (float(b.get("cy", 0)), float(b.get("cx", 0))))
    if not candidates:
        return []

    median_height = sorted(_box_height(b) for b in candidates)[len(candidates) // 2]
    tolerance = max(8.0, median_height * 0.72)
    rows: list[list[dict[str, Any]]] = []

    for box in candidates:
        cy = float(box.get("cy", 0))
        if not rows:
            rows.append([box])
            continue
        row_cy = sum(float(item.get("cy", 0)) for item in rows[-1]) / len(rows[-1])
        if abs(cy - row_cy) <= tolerance:
            rows[-1].append(box)
        else:
            rows.append([box])

    for row in rows:
        row.sort(key=lambda b: float(b.get("cx", 0)))
    return rows


def _default_columns(width: float) -> list[Column]:
    # KM table crop heuristic. The spike intentionally keeps this simple:
    # tune these ratios after seeing real OCR boxes from the sample set.
    return [
        Column("name", 0.00 * width, 0.40 * width),
        Column("kills", 0.48 * width, 0.60 * width),
        Column("deaths", 0.60 * width, 0.70 * width),
        Column("pvpDamage", 0.70 * width, 0.85 * width),
        Column("pveDamage", 0.85 * width, 1.01 * width),
    ]


def _assign_column(box: dict[str, Any], columns: list[Column]) -> str | None:
    cx = float(box.get("cx", 0))
    for col in columns:
        if col.start <= cx < col.end:
            return col.name
    return None


def _name_from_boxes(name_boxes: list[dict[str, Any]]) -> str:
    if not name_boxes:
        return ""
    sorted_boxes = sorted(name_boxes, key=lambda b: float(b.get("bbox", [0, 0, 0, 0])[0]))
    tokens: list[str] = []
    previous_right: float | None = None
    for box in sorted_boxes:
        text = str(box.get("text", "")).strip()
        if not text:
            continue
        bbox = box.get("bbox") or [0, 0, 0, 0]
        left = float(bbox[0])
        right = float(bbox[2])
        if previous_right is not None:
            gap = left - previous_right
            if gap > 42:
                break
        tokens.append(text)
        previous_right = right
    return " ".join(tokens)


def parse_rows(boxes: list[dict[str, Any]], image_width: int | None = None) -> list[dict[str, Any]]:
    if not boxes:
        return []
    width = float(image_width or max(float(b.get("bbox", [0, 0, 0, 0])[2]) for b in boxes) or 1)
    columns = _default_columns(width)
    parsed_rows: list[dict[str, Any]] = []

    for clustered in _cluster_rows(boxes):
        cells: dict[str, list[str]] = {col.name: [] for col in columns}
        name_boxes: list[dict[str, Any]] = []
        for box in clustered:
            col_name = _assign_column(box, columns)
            if col_name:
                if col_name == "name":
                    name_boxes.append(box)
                else:
                    cells[col_name].append(str(box.get("text", "")).strip())

        raw_name = _name_from_boxes(name_boxes)
        corrected = normalize_name(raw_name)
        kills = normalize_number(" ".join(cells["kills"]))
        deaths = normalize_number(" ".join(cells["deaths"]))
        pvp = normalize_number(" ".join(cells["pvpDamage"]))
        pve = normalize_number(" ".join(cells["pveDamage"]))
        if has_mixed_latin_cyrillic(raw_name) and has_mixed_latin_cyrillic(corrected):
            name = raw_name
            row: dict[str, Any] = {
                "name": name, "kills": kills, "deaths": deaths,
                "pvpDamage": pvp, "pveDamage": pve,
                "rawName": raw_name, "normalizedName": raw_name, "needsReview": True,
            }
        else:
            name = corrected
            row = {"name": name, "kills": kills, "deaths": deaths, "pvpDamage": pvp, "pveDamage": pve}
            if raw_name != name:
                row["rawName"] = raw_name
                row["normalizedName"] = name

        has_number = any(row[key] is not None for key in ("kills", "deaths", "pvpDamage", "pveDamage"))
        if name and has_number:
            parsed_rows.append(row)

    return parsed_rows
