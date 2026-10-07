"""memory-capture command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .apply import ApplyError, apply_candidates, discard
from .config import load
from .extract import ClaudeCliExtractor
from .hooks import on_session_end, on_session_start
from .inbox import Inbox
from .ports import SystemClock, git_root
from .sweep import sweep
from .worker import process_pending


def _stdin_json() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def cmd_hook_end(cfg, args) -> int:
    on_session_end(_stdin_json(), cfg, SystemClock())
    return 0  # never fail the user's exit


def cmd_hook_start(cfg, args) -> int:
    out = on_session_start(_stdin_json(), cfg, clock=SystemClock())
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_work(cfg, args) -> int:
    extra = cfg.rules_file.read_text() if cfg.rules_file and cfg.rules_file.exists() else ""
    ex = ClaudeCliExtractor(cfg.claude_bin, cfg.extract_timeout_s, cfg.max_candidates, extra,
                            model=cfg.model, cwd=str(cfg.inbox_dir))
    process_pending(cfg, ex, SystemClock())
    return 0


def cmd_sweep(cfg, args) -> int:
    ids = sweep(cfg, SystemClock(), dry_run=args.dry_run)
    print(("would queue" if args.dry_run else "queued") + f" {len(ids)} session(s)")
    for sid in ids:
        print(f"  {sid}")
    return 0


def cmd_retry(cfg, args) -> int:
    ids = Inbox(cfg.inbox_dir).retry_all()
    print(f"moved {len(ids)} failed session(s) back to pending")
    return 0


def render_show(sets: list[dict]) -> str:
    if not sets:
        return "No memory candidates waiting."
    out = []
    for s in sets:
        out.append(f"## session {s['session_id']}  (folder: {s.get('cwd') or '-'})")
        for i, c in enumerate(s.get("candidates", []), 1):
            upd = f"  [updates {c['update_existing']}]" if c.get("update_existing") else ""
            out.append(f"{i}. [{c['type']}/{c['scope']}] {c['title']} — {c['summary']}{upd}")
            out.extend("     " + line for line in c["body"].strip().splitlines())
        out.append("")
    return "\n".join(out)


def cmd_show(cfg, args) -> int:
    print(render_show(Inbox(cfg.inbox_dir).candidates()))
    return 0


def parse_accept(text: str) -> list[int]:
    try:
        nums = [int(x) for x in text.replace(" ", "").split(",") if x]
    except ValueError as e:
        raise ApplyError(f"--accept takes numbers like 1,3 (got {text!r})") from e
    if not nums:
        raise ApplyError("--accept needs at least one number")
    return sorted(set(nums))


def cmd_apply(cfg, args) -> int:
    for r in apply_candidates(cfg, args.session_id, parse_accept(args.accept), git_root, SystemClock()):
        print(r)
    return 0


def cmd_discard(cfg, args) -> int:
    discard(cfg, args.session_id, SystemClock())
    print(f"discarded {args.session_id}")
    return 0


def cmd_status(cfg, args) -> int:
    inbox = Inbox(cfg.inbox_dir)
    print(f"inbox: {cfg.inbox_dir}\npending: {len(inbox.pending())}  candidates: {len(inbox.candidates())}  failed: {len(inbox.failed())}")
    for f in inbox.failed():
        print(f"  failed {f['session_id']}: {f.get('error')}")
    return 0


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>dev.memory-capture.worker</string>
  <key>ProgramArguments</key><array><string>{exe}</string><string>work</string></array>
  <key>WatchPaths</key><array><string>{pending}</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{path}</string></dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
"""


def cmd_install(cfg, args) -> int:
    exe = args.exe or "memory-capture"
    hooks = {"SessionEnd": [{"hooks": [{"type": "command", "command": f"{exe} hook-end"}]}],
             "SessionStart": [{"matcher": "startup|clear", "hooks": [{"type": "command", "command": f"{exe} hook-start"}]}]}
    print("# 1) Add these entries to ~/.claude/settings.json under \"hooks\" (keep existing entries):")
    print(json.dumps(hooks, indent=2))
    print("\n# 2) Save as ~/Library/LaunchAgents/dev.memory-capture.worker.plist, then `launchctl load` it:")
    import os
    print(PLIST.format(exe=exe, pending=cfg.inbox_dir / "pending", path=os.environ.get("PATH", "/usr/bin:/bin"),
                       log=cfg.inbox_dir / "worker.log"))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="memory-capture", description=__doc__)
    p.add_argument("--config", type=Path, help="config TOML (default ~/.config/memory-capture/config.toml)")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook-end", help="SessionEnd hook (reads hook JSON on stdin)")
    sub.add_parser("hook-start", help="SessionStart hook (reads hook JSON on stdin)")
    sub.add_parser("work", help="extract candidates for pending sessions")
    sub.add_parser("show", help="list waiting candidates")
    a = sub.add_parser("apply", help="save accepted candidates")
    a.add_argument("session_id")
    a.add_argument("--accept", required=True, help="candidate numbers, e.g. 1,3")
    d = sub.add_parser("discard", help="drop all candidates of a session")
    d.add_argument("session_id")
    sub.add_parser("status", help="inbox counts and failures")
    w = sub.add_parser("sweep", help="queue sessions that ended without a SessionEnd hook (killed window, crash)")
    w.add_argument("--dry-run", action="store_true", help="only list what would be queued")
    sub.add_parser("retry", help="move every failed session back to pending")
    i = sub.add_parser("install", help="print hook and launchd snippets")
    i.add_argument("--exe", help="absolute path of the memory-capture executable")
    args = p.parse_args(argv)
    cfg = load(args.config)
    handler = {"hook-end": cmd_hook_end, "hook-start": cmd_hook_start, "work": cmd_work, "show": cmd_show,
               "apply": cmd_apply, "discard": cmd_discard, "status": cmd_status, "install": cmd_install,
               "sweep": cmd_sweep, "retry": cmd_retry}[args.cmd]
    try:
        return handler(cfg, args)
    except ApplyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
