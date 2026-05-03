from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR))

import parser as km_parser
from ocr_spike import run_paddle

PORT = int(os.environ.get("OCR_LOCAL_PORT", 5050))
OUT_DIR = SPIKE_DIR / "out"
TMP_DIR = SPIKE_DIR / "tmp"
OUT_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_path(stem: str, hx: str) -> Path:
    return OUT_DIR / f"{stem}.paddle.{hx[:12]}.json"


@contextmanager
def _per_request_names(known_names: list[str] | None, aliases: dict[str, str] | None):
    """Temporarily override parser name-correction data for one request only."""
    orig_load = km_parser._load_known_names
    orig_aliases = km_parser.KNOWN_NAME_ALIASES
    try:
        if known_names is not None:
            km_parser._load_known_names = lambda: known_names  # type: ignore[assignment]
        if aliases:
            km_parser.KNOWN_NAME_ALIASES = {
                **orig_aliases,
                **{km_parser._name_skeleton(k): v for k, v in aliases.items()},
            }
        yield
    finally:
        km_parser._load_known_names = orig_load  # type: ignore[assignment]
        km_parser.KNOWN_NAME_ALIASES = orig_aliases


def _to_parsed(rows: list[dict]) -> list[dict]:
    """Normalize spike row format to {nick, kills, deaths, pvp, pve}."""
    return [
        {
            "nick": r.get("name", ""),
            "kills": r.get("kills"),
            "deaths": r.get("deaths"),
            "pvp": r.get("pvpDamage"),
            "pve": r.get("pveDamage"),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# OCR pipeline
# ---------------------------------------------------------------------------

def handle_ocr(
    img_bytes: bytes,
    filename: str,
    known_names: list[str] | None,
    aliases: dict[str, str] | None,
) -> dict:
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".png"
    hx = _sha256(img_bytes)
    cache = _cache_path(stem, hx)

    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        boxes = data.get("boxes", [])
        # image_width may be absent in pre-server cache files; pass None → infer from boxes
        with _per_request_names(known_names, aliases):
            rows = km_parser.parse_rows(boxes, image_width=data.get("image_width"))
        return {
            "ok": True, "provider": "paddle_local", "cached": True,
            "hash": hx, "timing_ms": data.get("timing_ms", 0),
            "boxes_count": len(boxes), "rows": rows, "parsed": _to_parsed(rows),
        }

    # Fresh OCR path
    tmp = TMP_DIR / f"{stem}_{hx[:8]}{suffix}"
    tmp.write_bytes(img_bytes)
    try:
        from PIL import Image
        with Image.open(tmp) as im:
            image_width = im.width

        t0 = time.perf_counter()
        boxes = run_paddle(tmp)
        timing_ms = round((time.perf_counter() - t0) * 1000)

        with _per_request_names(known_names, aliases):
            rows = km_parser.parse_rows(boxes, image_width=image_width)

        cache.write_text(
            json.dumps(
                {
                    "hash": hx, "engine": "paddle", "image_width": image_width,
                    "text": "\n".join(b["text"] for b in boxes),
                    "boxes": boxes, "rows": rows, "timing_ms": timing_ms,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "ok": True, "provider": "paddle_local", "cached": False,
            "hash": hx, "timing_ms": timing_ms,
            "boxes_count": len(boxes), "rows": rows, "parsed": _to_parsed(rows),
        }
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: N802
        print(f"  {self.address_string()} {fmt % args}", flush=True)

    def _cors(self) -> None:
        for k, v in _CORS.items():
            self.send_header(k, v)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "engine": "paddle_local"})
        else:
            self._json(404, {"error": "GET /health  or  POST /ocr"})

    def do_POST(self):  # noqa: N802
        if self.path != "/ocr":
            self._json(404, {"error": "POST /ocr"})
            return

        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            self._json(400, {"ok": False, "error": "expected JSON body"})
            return

        raw_b64: str = body.get("base64") or body.get("imageBase64") or ""
        if not raw_b64:
            self._json(400, {"ok": False, "error": "missing 'base64' field"})
            return
        if raw_b64.startswith("data:") and "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]

        try:
            img_bytes = base64.b64decode(raw_b64)
        except Exception:
            self._json(400, {"ok": False, "error": "invalid base64"})
            return

        try:
            result = handle_ocr(
                img_bytes,
                body.get("filename", "upload.png"),
                body.get("known_names") or None,
                body.get("aliases") or None,
            )
            self._json(200, result)
        except Exception as exc:
            self._json(500, {
                "ok": False, "provider": "paddle_local",
                "error": str(exc), "parsed": [],
            })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    srv = HTTPServer(("localhost", PORT), _Handler)
    print(f"OCR local server -> http://localhost:{PORT}", flush=True)
    print(f"  GET  /health", flush=True)
    print(f"  POST /ocr", flush=True)
    srv.serve_forever()
