import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def normalize_verify_command(repo_root: Path) -> list[str]:
    return [
        sys.executable,
        ".agents/skills/cc-fix-preview/scripts/verify_flow.py",
        "--local-file",
        "BASA (1).html",
        "--preview-url",
        "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html",
    ]


def run_verify(repo_root: Path):
    command = normalize_verify_command(repo_root)
    proc = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    return command, proc.returncode, stdout, stderr


def codex_cli_path() -> str | None:
    return shutil.which("codex")


def run_codex_exec(repo_root: Path, trigger: dict):
    """Launch Codex CLI in a new VISIBLE terminal window.

    Prompt is written to a temp file so it can be piped into the new window.
    Output goes to the new window (user can see it).
    Result for bridge_result.json is obtained from verify_flow.py after Codex exits.
    """
    preview_url = trigger.get(
        "preview_url",
        "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html",
    )
    prompt = (
        "Read .agents/bridge_result.json as source of truth.\n"
        "VERIFY-ONLY task — do NOT modify any files.\n"
        "Run exactly this command and report its output:\n"
        "  python .agents/skills/cc-fix-preview/scripts/verify_flow.py"
        ' --local-file "BASA (1).html"'
        f' --preview-url "{preview_url}"\n'
        "If exit code is 0 output VERIFY_OK. If non-zero output VERIFY_FAIL.\n"
        "Do not change any file. Only run the verify command and report."
    )

    prompt_path = repo_root / ".agents" / "_codex_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    visible_command = ["codex", "--yolo", "exec", "-"]
    try:
        if sys.platform == "win32":
            # start /WAIT opens a visible cmd window and blocks until it closes.
            # /C closes the window when the command finishes.
            inner = "type .agents\\_codex_prompt.txt | cmd /c codex --yolo exec -"
            launch_cmd = ["cmd", "/c", "start", "/WAIT", "Codex Agent", "cmd", "/C", inner]
        else:
            inner = "cat .agents/_codex_prompt.txt | codex --yolo exec -"
            launch_cmd = ["bash", "-c", f'xterm -e \'bash -c "{inner}; read -p Done\\ press\\ Enter"\' ']
        subprocess.run(launch_cmd, cwd=str(repo_root), timeout=240)
    except subprocess.TimeoutExpired:
        print("CODEX_WINDOW_TIMEOUT")
    finally:
        try:
            prompt_path.unlink()
        except OSError:
            pass

    # Codex ran in its own window; run verify here to get the authoritative result.
    verify_cmd, returncode, stdout, stderr = run_verify(repo_root)
    return visible_command, returncode, stdout, stderr


def should_skip(trigger: dict, handled_ids: set) -> bool:
    trigger_id = trigger.get("trigger_id")
    if not trigger_id:
        return False
    return trigger_id in handled_ids


def handle_trigger(repo_root: Path, trigger_path: Path, result_path: Path, handled_ids: set) -> int:
    if not trigger_path.exists():
        print(f"WAITING_FOR_TRIGGER {trigger_path.as_posix()}")
        return 2

    trigger = load_json(trigger_path)
    status = trigger.get("status", "")
    print(f"TRIGGER_STATUS={status}")

    if status in {"fail", "not_ready"}:
        print("TRIGGER_NOT_READY")
        return 0

    if status != "ready_for_codex":
        print("TRIGGER_IGNORED")
        return 0

    if should_skip(trigger, handled_ids):
        print("TRIGGER_ALREADY_HANDLED")
        return 0

    print("TRIGGER_READY_FOR_CODEX")
    codex_path = codex_cli_path()
    if codex_path:
        print(f"CODEX_CLI_FOUND={codex_path}")
        print("LAUNCHING_REAL_CODEX")
        command, returncode, stdout, stderr = run_codex_exec(repo_root, trigger)
        surrogate = "codex-cli"
    else:
        print("CODEX_CLI_NOT_FOUND")
        print("FALLBACK_SURROGATE=verify_flow.py")
        command, returncode, stdout, stderr = run_verify(repo_root)
        surrogate = "verify_flow.py (surrogate fallback — codex CLI not found)"
    print("VERIFY_COMMAND=" + " ".join(command))
    print(f"VERIFY_EXIT={returncode}")
    if stdout:
        print("VERIFY_STDOUT_BEGIN")
        print(stdout)
        print("VERIFY_STDOUT_END")
    if stderr:
        print("VERIFY_STDERR_BEGIN")
        print(stderr)
        print("VERIFY_STDERR_END")

    result = {
        "trigger_id": trigger.get("trigger_id"),
        "source_status": status,
        "status": "verify_completed" if returncode == 0 else "verify_failed",
        "surrogate": surrogate,
        "task": trigger.get("task"),
        "last_writer": trigger.get("last_writer"),
        "next_agent": trigger.get("next_agent"),
        "next_step": trigger.get("next_step"),
        "preview_url": trigger.get("preview_url"),
        "verify_command": command,
        "verify_exit_code": returncode,
        "verify_stdout": stdout,
        "verify_stderr": stderr,
        "handled_at": utc_now(),
    }
    save_json(result_path, result)
    print(f"RESULT_WRITTEN={result_path.as_posix()}")
    trigger_id = trigger.get("trigger_id")
    if trigger_id:
        handled_ids.add(trigger_id)
    return 0 if returncode == 0 else 1


def main():
    # Force stdout to UTF-8 on Windows (default console may be cp1251)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default=".agents/bridge_trigger.json")
    parser.add_argument("--result", default=".agents/bridge_result.json")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd()
    trigger_path = repo_root / args.trigger
    result_path = repo_root / args.result

    handled_ids: set = set()

    if args.once:
        raise SystemExit(handle_trigger(repo_root, trigger_path, result_path, handled_ids))

    print("BRIDGE_WATCHER_STARTED")
    print(f"TRIGGER_PATH={trigger_path.as_posix()}")
    print(f"RESULT_PATH={result_path.as_posix()}")
    while True:
        exit_code = handle_trigger(repo_root, trigger_path, result_path, handled_ids)
        if exit_code == 1:
            time.sleep(args.poll_interval)
        elif exit_code == 2:
            time.sleep(args.poll_interval)
        else:
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
