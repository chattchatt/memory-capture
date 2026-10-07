"""The inbox: pending items (from SessionEnd), candidates (from the worker), failed and applied."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
from pathlib import Path

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _name(session_id: str) -> str:
    return _SAFE.sub("_", session_id)[:120] or "unknown"


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def _read_all(folder: Path) -> list[dict]:
    if not folder.is_dir():
        return []
    items = []
    for p in sorted(folder.glob("*.json")):
        try:
            items.append(json.loads(p.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return items


class Inbox:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, kind: str) -> Path:
        return self.root / kind

    def enqueue(self, item: dict) -> None:
        _write_atomic(self._dir("pending") / f"{_name(item['session_id'])}.json", item)

    def pending(self) -> list[dict]:
        return _read_all(self._dir("pending"))

    def update_pending(self, item: dict) -> None:
        self.enqueue(item)

    def drop_pending(self, session_id: str) -> None:
        (self._dir("pending") / f"{_name(session_id)}.json").unlink(missing_ok=True)

    def write_candidates(self, session_id: str, data: dict) -> None:
        _write_atomic(self._dir("candidates") / f"{_name(session_id)}.json", data)

    def candidates(self) -> list[dict]:
        return _read_all(self._dir("candidates"))

    def get_candidates(self, session_id: str) -> dict | None:
        p = self._dir("candidates") / f"{_name(session_id)}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def close_candidates(self, session_id: str, record: dict) -> None:
        """Move a candidates file to applied/ with what was decided."""
        _write_atomic(self._dir("applied") / f"{_name(session_id)}.json", record)
        (self._dir("candidates") / f"{_name(session_id)}.json").unlink(missing_ok=True)

    def fail(self, item: dict, error: str) -> None:
        _write_atomic(self._dir("failed") / f"{_name(item['session_id'])}.json", dict(item, error=error))
        self.drop_pending(item["session_id"])

    def failed(self) -> list[dict]:
        return _read_all(self._dir("failed"))

    def log(self, line: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "log.txt", "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")

    @contextlib.contextmanager
    def lock(self):
        """One worker at a time. Yields False (without waiting) when another worker holds it."""
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "worker.lock", "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def log(self, line: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "log.txt", "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
