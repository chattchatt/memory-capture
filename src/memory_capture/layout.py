"""Where memory lives: Claude Code's per-project memory folders, keyed by a path slug."""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config


def slug_for(path: str) -> str:
    """Claude Code's project folder name: path separators and dots become dashes."""
    return re.sub(r"[/.]", "-", path)


def folder_memory_dir(cfg: Config, cwd: str, git_root) -> Path:
    return cfg.projects_dir / slug_for(git_root(cwd)) / "memory"


def home_memory_dir(cfg: Config) -> Path:
    return cfg.projects_dir / slug_for(str(cfg.home_dir)) / "memory"
