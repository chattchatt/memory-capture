"""Background worker: pending session -> candidates file."""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .extract import ExtractionError, valid
from .inbox import Inbox
from .layout import folder_memory_dir
from .ports import git_root as _git_root
from .transcript import read_dialogue, render_dialogue


def existing_summary(mem_dir: Path) -> str:
    idx = mem_dir / "MEMORY.md"
    if not idx.exists():
        return "(none)"
    lines = [m.group(1) + " — " + m.group(2).strip()
             for m in re.finditer(r"\]\(([^)/]+)\.md\)\s*[—-]?\s*(.*)", idx.read_text())]
    return "\n".join(lines[:80]) or "(none)"


def process_pending(cfg: Config, extractor, clock, git_root=_git_root) -> None:
    inbox = Inbox(cfg.inbox_dir)
    for item in inbox.pending():
        sid = item["session_id"]
        try:
            turns = read_dialogue(Path(item["transcript_path"]))
        except OSError as e:
            inbox.fail(item, f"transcript unreadable: {e}")
            continue
        dialogue = render_dialogue(turns, cfg.max_dialogue_chars)
        ctx = {"cwd": item.get("cwd", ""),
               "existing": existing_summary(folder_memory_dir(cfg, item.get("cwd") or str(cfg.home_dir), git_root))}
        try:
            cands = extractor.extract(dialogue, ctx)
        except ExtractionError as e:
            item["attempts"] = int(item.get("attempts", 0)) + 1
            item["last_error"] = str(e)
            if item["attempts"] >= cfg.max_attempts:
                inbox.fail(item, f"extraction failed: {e}")
            else:
                inbox.update_pending(item)
            inbox.log(f"{clock.now_iso()} {sid} extraction error: {e}")
            continue
        good = [c for c in cands if valid(c)][: cfg.max_candidates]
        if good:
            inbox.write_candidates(sid, {"session_id": sid, "cwd": item.get("cwd", ""),
                                         "extracted_at": clock.now_iso(), "candidates": good})
        inbox.drop_pending(sid)
        inbox.log(f"{clock.now_iso()} {sid} -> {len(good)} candidate(s)")
