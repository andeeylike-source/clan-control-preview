#!/usr/bin/env python3
import argparse
import contextlib
import http.client
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fetch(url: str, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "cc-verify-flow/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body


def ensure_marker(body: str, marker: str, label: str) -> None:
    if marker not in body:
        raise AssertionError(f"{label}: marker not found: {marker}")


def run_local_http_check(repo_root: Path, local_file: Path, marker: str) -> None:
    port = pick_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/{urllib.parse.quote(local_file.name)}"
        last_err = None
        for _ in range(20):
            try:
                status, body = fetch(url, timeout=3.0)
                if status != 200:
                    raise AssertionError(f"local_http: unexpected status {status}")
                ensure_marker(body, marker, "local_http")
                return
            except (OSError, urllib.error.URLError, http.client.HTTPException, AssertionError) as exc:
                last_err = exc
                time.sleep(0.25)
        raise AssertionError(f"local_http: failed to fetch {url}: {last_err}")
    finally:
        server.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=3)
        if server.poll() is None:
            server.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal Clan Control local + preview verify flow.")
    parser.add_argument("--local-file", required=True, help="Path to BASA (1).html relative to repo root")
    parser.add_argument("--preview-url", required=True, help="Preview URL to verify")
    parser.add_argument("--marker", default='id="page-screenshots"', help="HTML marker expected in both local and preview")
    args = parser.parse_args()

    repo_root = Path.cwd()
    local_file = (repo_root / args.local_file).resolve()
    if not local_file.is_file():
        raise SystemExit(f"FAIL local_file missing: {local_file}")

    body = read_text(local_file)
    if "</html>" not in body.lower():
        raise SystemExit("FAIL local_file missing </html>")
    ensure_marker(body, args.marker, "local_file")

    run_local_http_check(repo_root, local_file, args.marker)

    preview_status, preview_body = fetch(args.preview_url, timeout=15.0)
    if preview_status != 200:
        raise SystemExit(f"FAIL preview unexpected status: {preview_status}")
    ensure_marker(preview_body, args.marker, "preview")

    print("VERIFY_OK")
    print(f"local_file={local_file.name}")
    print(f"preview_url={args.preview_url}")
    print(f"marker={args.marker}")
    print("scope=local-file,local-http,preview-http")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        raise SystemExit(f"FAIL {exc}")
