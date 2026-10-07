"""Sweep: queue sessions whose SessionEnd never came, and give failed extractions another round.

SessionEnd does not fire when a terminal window is killed or Claude Code crashes, so those sessions
would never be queued. At each session start we look for transcripts that have been idle long enough
to be finished and were never taken (or have grown since). Only `stat` for most files; a transcript's
head and tail are read only when it is otherwise a match.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .inbox import Inbox

_TAIL = 256 * 1024


def _records(lines):
    for line in lines:
        try:
            yield json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue


def entrypoint_of(path: Path) -> str | None:
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, rec in enumerate(_records(f)):
            if isinstance(rec, dict) and rec.get("entrypoint"):
                return rec["entrypoint"]
            if i > 50:
                break
    return None


def last_cwd(path: Path) -> str:
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - _TAIL))
        tail = f.read().decode("utf-8", errors="replace").splitlines()
    for rec in _records(reversed(tail)):
        if isinstance(rec, dict) and rec.get("cwd"):
            return rec["cwd"]
    return ""


def sweep(cfg: Config, clock, dry_run: bool = False) -> list[str]:
    """Return the session ids queued (or that would be, with dry_run)."""
    inbox = Inbox(cfg.inbox_dir)
    now = clock.now_ts()
    if not dry_run:
        for sid in inbox.retry_due(now, cfg.retry_after_hours * 3600, cfg.max_retry_rounds):
            inbox.log(f"{clock.now_iso()} {sid} retry after failure")
    since, idle_before = now - cfg.sweep_lookback_days * 86400, now - cfg.sweep_idle_minutes * 60
    done, queued = inbox.done(), []
    for t in sorted(cfg.projects_dir.glob("*/*.jsonl")):
        try:
            st = t.stat()
        except OSError:
            continue
        sid = t.stem
        if st.st_size < cfg.min_transcript_bytes or not since <= st.st_mtime <= idle_before:
            continue
        if inbox.known(sid):
            continue
        if sid not in done and inbox.was_applied(sid):  # handled before the ledger existed
            if not dry_run:
                inbox.mark_done(sid, st.st_size)
            continue
        if sid in done and st.st_size - done[sid] < cfg.min_transcript_bytes:
            continue
        try:
            if entrypoint_of(t) not in cfg.interactive_entrypoints:
                continue
            cwd = last_cwd(t)
        except OSError:
            continue
        queued.append(sid)
        if not dry_run:
            inbox.enqueue({"session_id": sid, "transcript_path": str(t), "cwd": cwd, "reason": "sweep",
                           "queued_at": clock.now_iso(), "attempts": 0})
            inbox.log(f"{clock.now_iso()} {sid} queued by sweep (no session end seen)")
    return queued
