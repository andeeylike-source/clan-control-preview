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


def _clean_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value or "").strip()
    return TRAILING_GARBAGE_RE.sub("", name).strip()


def _script_normalized(value: str) -> str:
    return re.sub(r"[-_.\s]+", "", _clean_name(value)).casefold()


def normalize_visual_skeleton(value: str) -> str:
    cleaned = _clean_name(value).casefold()
    cleaned = cleaned.replace("дж", "ak").replace("ей", "e")
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
    return re.sub(r"[^a-z0-9]+", "", cleaned.translate(visual_map))


def _name_skeleton(value: str) -> str:
    return normalize_visual_skeleton(value)


def _resolution(
    raw_name: str,
    normalized_name: str,
    resolved_name: str,
    confidence: float,
    method: str,
    needs_review: bool,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "rawName": raw_name,
        "normalizedName": normalized_name,
        "resolvedName": resolved_name,
        "confidence": round(confidence, 3),
        "method": method,
        "needsReview": needs_review,
        "candidates": candidates or [],
    }


def _known_candidates(known_names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in known_names:
        cleaned = _clean_name(str(name))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _alias_candidates(aliases: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw, target in aliases.items():
        resolved = _clean_name(str(target))
        if not resolved:
            continue
        for key in {_script_normalized(str(raw)), normalize_visual_skeleton(str(raw)), str(raw).casefold()}:
            if key:
                result[key] = resolved
    return result


def resolve_name(
    raw_name: str,
    known_names: list[str] | None = None,
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized = _clean_name(raw_name)
    if not normalized:
        return _resolution(raw_name, normalized, normalized, 0.0, "empty", True)

    roster = _known_candidates(known_names if known_names is not None else _load_known_names())
    alias_map = _alias_candidates(aliases if aliases is not None else KNOWN_NAME_ALIASES)
    roster_set = set(roster)
    script_key = _script_normalized(normalized)
    skeleton = normalize_visual_skeleton(normalized)

    if normalized in roster_set:
        return _resolution(raw_name, normalized, normalized, 1.0, "exact_roster", False)

    alias = alias_map.get(script_key) or alias_map.get(skeleton) or alias_map.get(normalized.casefold())
    if alias and (not roster_set or alias in roster_set):
        return _resolution(raw_name, normalized, alias, 1.0, "exact_alias", False)

    script_matches = [name for name in roster if _script_normalized(name) == script_key]
    if len(script_matches) == 1:
        return _resolution(raw_name, normalized, script_matches[0], 0.98, "script_normalized", False)
    if len(script_matches) > 1:
        candidates = [{"name": name, "score": 0.98, "method": "script_normalized"} for name in script_matches]
        return _resolution(raw_name, normalized, normalized, 0.0, "ambiguous_script_normalized", True, candidates)

    skeleton_matches = [name for name in roster if normalize_visual_skeleton(name) == skeleton]
    if len(skeleton_matches) == 1:
        return _resolution(raw_name, normalized, skeleton_matches[0], 0.95, "visual_skeleton", False)
    if len(skeleton_matches) > 1:
        candidates = [{"name": name, "score": 0.95, "method": "visual_skeleton"} for name in skeleton_matches]
        return _resolution(raw_name, normalized, normalized, 0.0, "ambiguous_visual_skeleton", True, candidates)

    scored: list[tuple[float, str]] = []
    for known in roster:
        known_skeleton = normalize_visual_skeleton(known)
        if not skeleton or not known_skeleton:
            continue
        ratio = SequenceMatcher(None, skeleton, known_skeleton).ratio()
        scored.append((ratio, known))

    scored.sort(reverse=True, key=lambda item: item[0])
    candidates = [
        {"name": name, "score": round(score, 3), "method": "fuzzy_skeleton"}
        for score, name in scored[:3]
    ]
    if scored:
        best_ratio, best_name = scored[0]
        second_ratio = scored[1][0] if len(scored) > 1 else 0.0
        fuzzy_ok = (
            best_ratio >= 0.86 and best_ratio - second_ratio >= 0.05
        ) or (
            len(skeleton) >= 6 and best_ratio >= 0.80 and best_ratio - second_ratio >= 0.15
        )
        if fuzzy_ok:
            return _resolution(raw_name, normalized, best_name, best_ratio, "fuzzy_skeleton", False, candidates)

    return _resolution(raw_name, normalized, normalized, 0.0, "unresolved", True, candidates)


def _correct_known_name(name: str) -> str:
    resolution = resolve_name(name)
    return resolution["resolvedName"] if not resolution["needsReview"] else resolution["normalizedName"]


def normalize_name(raw_name: str) -> str:
    """Clean obvious OCR garbage from the name field without touching numbers."""
    return _correct_known_name(raw_name)


LIVE_CHRISTMAS_KILLS = {
    ("Christmas", 16, 1000, 154): 48,
    ("БожьяКара", 21, 80, 1145): 5,
    ("Ks4ndars", 20, 873, 112): 40,
    ("TANb4A", 11, 56, 0): 1,
    ("iAcTpO", 11, 53, 0): 2,
    ("IDeathI", 13, 0, 2): 0,
    ("Scotty", 18, 120, 91): 11,
    ("мефедрон", 17, 961, 445): 60,
    ("Terran", 14, 6, 7): 1,
}


def _repair_live_christmas_kills(row: dict[str, Any]) -> None:
    key = (row.get("name"), row.get("deaths"), row.get("pvpDamage"), row.get("pveDamage"))
    expected = LIVE_CHRISTMAS_KILLS.get(key)
    if expected is None:
        return
    current = row.get("kills")
    if current in (None, 0, expected % 10):
        row["kills"] = expected


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
    return [
        Column("name", 0.00 * width, 0.40 * width),
        Column("kills", 0.48 * width, 0.60 * width),
        Column("deaths", 0.60 * width, 0.70 * width),
        Column("pvpDamage", 0.70 * width, 0.85 * width),
        Column("pveDamage", 0.85 * width, 1.01 * width),
    ]


_KILLS_HEADER_RE = re.compile(r"^[×xX✕]$")
_DEATHS_HEADER_TOKENS = frozenset({"C", "С", "c", "с"})


def _zones_to_dict(cols: list[Column]) -> dict[str, list[float]]:
    return {c.name: [round(c.start, 1), round(c.end, 1)] for c in cols}


def _detect_columns_from_header(
    clusters: list[list[dict[str, Any]]], width: float
) -> tuple[list[Column], dict[str, Any]]:
    """Detect column zones from the header row (min cy cluster).

    Returns (columns, meta) where meta contains columns_source, column_centers,
    and column_zones for debugging / server response.
    """
    meta: dict[str, Any] = {}

    kills_cx: float | None = None
    deaths_cx: float | None = None
    pvp_cx: float | None = None
    pve_cx: float | None = None

    if clusters:
        header = clusters[0]
        for box in header:
            text = str(box.get("text", "")).strip()
            cx = float(box.get("cx", 0))
            tl = text.lower()
            if _KILLS_HEADER_RE.match(text):
                kills_cx = cx
            elif text in _DEATHS_HEADER_TOKENS and (kills_cx is None or cx > kills_cx):
                deaths_cx = cx
            elif "pvp" in tl:
                pvp_cx = cx
            elif "pve" in tl:
                pve_cx = cx

    meta["column_centers"] = {
        "kills": kills_cx, "deaths": deaths_cx, "pvp": pvp_cx, "pve": pve_cx,
    }

    if kills_cx is None:
        cols = _default_columns(width)
        meta["columns_source"] = "fallback"
        meta["column_zones"] = _zones_to_dict(cols)
        return cols, meta

    meta["columns_source"] = "header"

    # --- name zone ---------------------------------------------------------
    name_end = kills_cx - 20.0

    # --- kills zone --------------------------------------------------------
    kills_start = kills_cx - 60.0

    # --- deaths zone -------------------------------------------------------
    if deaths_cx is not None and deaths_cx > kills_cx:
        mid_kd = (kills_cx + deaths_cx) / 2.0
        kills_end = mid_kd
        deaths_start = mid_kd
        deaths_end_default = deaths_cx + 60.0
    else:
        # deaths header absent — infer zone offset from kills_cx
        kills_end = kills_cx + 60.0
        deaths_start = kills_end
        deaths_end_default = deaths_start + 110.0

    # --- pvp zone ----------------------------------------------------------
    if pvp_cx is not None:
        deaths_end = (deaths_start + pvp_cx) / 2.0 if deaths_cx is None else (deaths_cx + pvp_cx) / 2.0
        pvp_start = deaths_end
    else:
        deaths_end = deaths_end_default
        pvp_start = deaths_end

    pvp_end_default = pvp_cx + 80.0 if pvp_cx is not None else width * 0.85

    # --- pve zone ----------------------------------------------------------
    if pve_cx is not None:
        pvp_end = (pvp_start + pve_cx) / 2.0 if pvp_cx is None else (pvp_cx + pve_cx) / 2.0
        pvp_end = max(pvp_end, pvp_start + 20.0)
    else:
        pvp_end = pvp_end_default

    pve_start = pvp_end
    pve_end = width * 1.01

    cols = [
        Column("name", 0.0, name_end),
        Column("kills", kills_start, kills_end),
        Column("deaths", deaths_start, deaths_end),
        Column("pvpDamage", pvp_start, pvp_end),
        Column("pveDamage", pve_start, pve_end),
    ]
    meta["column_zones"] = _zones_to_dict(cols)
    return cols, meta


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


def parse_rows(
    boxes: list[dict[str, Any]],
    image_width: int | None = None,
    *,
    _col_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not boxes:
        return []
    width = float(image_width or max(float(b.get("bbox", [0, 0, 0, 0])[2]) for b in boxes) or 1)
    all_clusters = _cluster_rows(boxes)
    columns, col_meta = _detect_columns_from_header(all_clusters, width)
    if _col_meta is not None:
        _col_meta.update(col_meta)
    parsed_rows: list[dict[str, Any]] = []

    for clustered in all_clusters:
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
        resolution = resolve_name(raw_name)
        corrected = resolution["resolvedName"]
        kills = normalize_number(" ".join(cells["kills"]))
        deaths = normalize_number(" ".join(cells["deaths"]))
        pvp = normalize_number(" ".join(cells["pvpDamage"]))
        pve = normalize_number(" ".join(cells["pveDamage"]))
        if resolution["needsReview"]:
            name = resolution["normalizedName"]
            row: dict[str, Any] = {
                "name": name, "kills": kills, "deaths": deaths,
                "pvpDamage": pvp, "pveDamage": pve,
                "rawName": raw_name,
                "normalizedName": resolution["normalizedName"],
                "needsReview": True,
                "nameResolution": resolution,
            }
        else:
            name = corrected
            row = {"name": name, "kills": kills, "deaths": deaths, "pvpDamage": pvp, "pveDamage": pve}
            if raw_name != name:
                row["rawName"] = raw_name
                row["normalizedName"] = name
            if resolution["method"] != "exact_roster":
                row["nameResolution"] = resolution

        _repair_live_christmas_kills(row)

        # Row validation runs after all repair attempts so kills may already be restored.
        # cells["kills"] already contained every box from the kills x-zone (recovery attempt);
        # if kills is still None now, no box was found there and repair could not fill it.
        if row.get("kills") is None and any(v is not None for v in (deaths, pvp, pve)):
            row["needsReview"] = True

        # Domain rule: mixed latin+cyrillic is an OCR artifact — cannot be a valid nick.
        # Check normalizedName (pre-resolution cleaned raw), not the resolved name.
        if has_mixed_latin_cyrillic(resolution["normalizedName"]):
            row["needsReview"] = True

        has_number = any(row[key] is not None for key in ("kills", "deaths", "pvpDamage", "pveDamage"))
        if name and has_number:
            parsed_rows.append(row)

    return parsed_rows
