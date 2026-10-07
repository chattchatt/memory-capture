"""Claude Code hook handlers. Both must be fast and must never break the session."""

from __future__ import annotations

import os
from pathlib import Path

from .config import START_SOURCES, Config
from .inbox import Inbox
from .ports import SystemClock
from .sweep import sweep

CHILD_ENV = "MEMORY_CAPTURE_CHILD"


def on_session_end(event: dict, cfg: Config, clock, env=None) -> None:
    """Queue the finished session for background extraction. Never raises."""
    env = os.environ if env is None else env
    inbox = Inbox(cfg.inbox_dir)
    try:
        if env.get(CHILD_ENV):
            return
        if event.get("reason") not in cfg.capture_reasons:
            return
        tp, sid = event.get("transcript_path"), event.get("session_id")
        if not tp or not sid:
            return
        try:
            if Path(tp).stat().st_size < cfg.min_transcript_bytes:
                return
        except OSError:
            return
        inbox.enqueue({"session_id": sid, "transcript_path": tp, "cwd": event.get("cwd", ""),
                       "reason": event["reason"], "queued_at": clock.now_iso(), "attempts": 0})
    except Exception as e:  # a hook must not fail the user's exit
        try:
            inbox.log(f"session_end error: {e!r}")
        except Exception:
            pass


def notice_text(sets: list[dict]) -> str:
    total = sum(len(s.get("candidates", [])) for s in sets)
    folders = sorted({s.get("cwd", "") for s in sets if s.get("cwd")})
    return (
        f"[memory-capture] {total} memory candidate(s) from {len(sets)} earlier session(s) "
        f"({', '.join(folders) or 'unknown folder'}) are waiting for the user's confirmation. "
        "After handling the user's first request, run `memory-capture show`, present each candidate "
        "briefly, and ask which to save. Save only what the user accepts with "
        "`memory-capture apply <session_id> --accept N,M`; discard the rest with "
        "`memory-capture discard <session_id>`. Never save without explicit confirmation."
    )


def on_session_start(event: dict, cfg: Config, env=None, clock=None) -> dict | None:
    """Queue sessions that ended without SessionEnd, then return hook output announcing ready
    candidates, or None. Never raises."""
    env = os.environ if env is None else env
    try:
        if env.get(CHILD_ENV) or event.get("source") not in START_SOURCES:
            return None
        try:
            sweep(cfg, clock or SystemClock())
        except Exception as e:  # the announcement below must still work
            Inbox(cfg.inbox_dir).log(f"sweep error: {e!r}")
        sets = [s for s in Inbox(cfg.inbox_dir).candidates() if s.get("candidates")]
        if not sets:
            return None
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": notice_text(sets)}}
    except Exception:
        return None
