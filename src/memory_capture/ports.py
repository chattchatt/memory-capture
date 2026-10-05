"""Seams: everything that touches the outside world is passed in, so tests can swap in doubles."""

from __future__ import annotations

import datetime as _dt
import subprocess
from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str: ...
    def today(self) -> str: ...


class SystemClock:
    def now_iso(self) -> str:
        return _dt.datetime.now().isoformat(timespec="seconds")

    def today(self) -> str:
        return _dt.date.today().isoformat()


class Extractor(Protocol):
    def extract(self, dialogue: str, context: dict) -> list[dict]: ...


def git_root(cwd: str) -> str:
    """Resolve the git top-level for cwd (Claude Code keys project memory by repo root)."""
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return cwd
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else cwd
