"""Settings. Every path is configurable so the tool carries no personal layout."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG = Path("~/.config/memory-capture/config.toml").expanduser()
CAPTURE_REASONS = ("clear", "prompt_input_exit", "logout", "other")
START_SOURCES = ("startup", "clear")
TYPES = ("user", "feedback", "project", "reference")
SCOPES = ("folder", "home")


@dataclass
class Config:
    projects_dir: Path
    home_dir: Path
    inbox_dir: Path
    kernel_dir: Path | None = None
    min_transcript_bytes: int = 20_000
    max_candidates: int = 5
    max_dialogue_chars: int = 60_000
    max_attempts: int = 3
    claude_bin: str = "claude"
    extract_timeout_s: int = 300
    rules_file: Path | None = None
    capture_reasons: tuple = field(default=CAPTURE_REASONS)


def load(path: Path | None = None) -> Config:
    """Read the TOML config (missing file means defaults)."""
    home = Path.home()
    data: dict = {}
    p = path or Path(os.environ.get("MEMORY_CAPTURE_CONFIG", DEFAULT_CONFIG))
    if p.exists():
        data = tomllib.loads(p.read_text())

    def path_of(key, default):
        v = data.get(key, default)
        return Path(v).expanduser() if v else None

    return Config(
        projects_dir=path_of("projects_dir", "~/.claude/projects"),
        home_dir=path_of("home_dir", str(home)),
        inbox_dir=path_of("inbox_dir", "~/.claude/memory-inbox"),
        kernel_dir=path_of("kernel_dir", ""),
        min_transcript_bytes=int(data.get("min_transcript_bytes", 20_000)),
        max_candidates=int(data.get("max_candidates", 5)),
        max_dialogue_chars=int(data.get("max_dialogue_chars", 60_000)),
        max_attempts=int(data.get("max_attempts", 3)),
        claude_bin=str(data.get("claude_bin", "claude")),
        extract_timeout_s=int(data.get("extract_timeout_s", 300)),
        rules_file=path_of("rules_file", ""),
        capture_reasons=tuple(data.get("capture_reasons", CAPTURE_REASONS)),
    )
