from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image

from parser import parse_rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def polygon_to_bbox(polygon: list[list[float]]) -> list[float]:
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def make_box(text: str, confidence: float | None, polygon: Any) -> dict[str, Any] | None:
    if not text or polygon is None:
        return None
    normalized_polygon = [[float(point[0]), float(point[1])] for point in polygon]
    bbox = polygon_to_bbox(normalized_polygon)
    return {
        "text": text,
        "confidence": None if confidence is None else float(confidence),
        "polygon": normalized_polygon,
        "bbox": bbox,
        "cx": (bbox[0] + bbox[2]) / 2,
        "cy": (bbox[1] + bbox[3]) / 2,
    }


def _extract_from_modern_result(item: Any) -> list[dict[str, Any]]:
    data = getattr(item, "json", None)
    if callable(data):
        data = data()
    if not data:
        data = item
    if isinstance(data, dict) and "res" in data:
        data = data["res"]
    if not isinstance(data, dict):
        return []

    texts = data.get("rec_texts") or []
    scores = data.get("rec_scores") or []
    polys = data.get("rec_polys") or data.get("dt_polys") or []
    boxes: list[dict[str, Any]] = []

    for idx, text in enumerate(texts):
        score = scores[idx] if idx < len(scores) else None
        poly = polys[idx] if idx < len(polys) else None
        box = make_box(str(text).strip(), score, poly)
        if box:
            boxes.append(box)
    return boxes


def _extract_from_legacy_result(item: Any) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    if not isinstance(item, list):
        return boxes
    for entry in item:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        polygon = entry[0]
        rec = entry[1]
        if isinstance(rec, (list, tuple)) and rec:
            text = str(rec[0]).strip()
            confidence = float(rec[1]) if len(rec) > 1 and rec[1] is not None else None
        else:
            text = str(rec).strip()
            confidence = None
        box = make_box(text, confidence, polygon)
        if box:
            boxes.append(box)
    return boxes


def extract_boxes(result: Any) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    pages = result if isinstance(result, list) else [result]
    for page in pages:
        boxes.extend(_extract_from_modern_result(page))
        if not boxes:
            boxes.extend(_extract_from_legacy_result(page))
    return boxes


def run_paddle(input_path: Path) -> list[dict[str, Any]]:
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise RuntimeError(f"failed to import PaddleOCR: {exc}") from exc

    try:
        ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        result = ocr.predict(str(input_path))
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR run failed: {exc}") from exc

    return extract_boxes(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local OCR spike for KM table crop.")
    parser.add_argument("--engine", choices=["paddle"], required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    input_path = args.input
    if not input_path.exists():
        print(f"input file not found: {input_path}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    file_hash = sha256_file(input_path)
    started = time.perf_counter()

    try:
        boxes = run_paddle(input_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    timing_ms = round((time.perf_counter() - started) * 1000)
    with Image.open(input_path) as image:
        image_width = image.width

    rows = parse_rows(boxes, image_width=image_width)
    output = {
        "hash": file_hash,
        "engine": args.engine,
        "text": "\n".join(box["text"] for box in boxes),
        "boxes": boxes,
        "rows": rows,
        "timing_ms": timing_ms,
    }

    output_path = args.out / f"{input_path.stem}.{args.engine}.{file_hash[:12]}.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "timing_ms": timing_ms, "boxes_count": len(boxes), "rows_count": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
