"""Read a Claude Code session transcript (JSONL) down to the human/assistant dialogue."""

from __future__ import annotations

import json
from pathlib import Path


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_dialogue(path: Path) -> list[tuple[str, str]]:
    """Return [(role, text)] for main-thread user/assistant text only.

    Skips tool calls/results, thinking, sidechains (subagents), meta records, slash-command and
    system-reminder wrappers, and malformed lines.
    """
    turns: list[tuple[str, str]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") not in ("user", "assistant") or rec.get("isSidechain") or rec.get("isMeta"):
                continue
            msg = rec.get("message") or {}
            text = _text_of(msg.get("content")).strip()
            if not text or text.startswith("<"):
                continue
            turns.append((msg.get("role", rec["type"]), text))
    return turns


def render_dialogue(turns: list[tuple[str, str]], max_chars: int) -> str:
    """Join turns, keeping the most recent ones when over budget."""
    out: list[str] = []
    used = 0
    for role, text in reversed(turns):
        piece = f"{role.upper()}: {text}"
        cost = len(piece) + (2 if out else 0)
        if used + cost > max_chars:
            break
        out.append(piece)
        used += cost
    return "\n\n".join(reversed(out))
