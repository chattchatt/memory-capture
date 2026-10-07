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

    def known(self, session_id: str) -> bool:
        """Waiting somewhere in the inbox (queued, awaiting confirmation, or failed)."""
        return any((self._dir(k) / f"{_name(session_id)}.json").exists() for k in ("pending", "candidates", "failed"))

    def was_applied(self, session_id: str) -> bool:
        return (self._dir("applied") / f"{_name(session_id)}.json").exists()

    # done.json: session id -> transcript size when it was last extracted, so a resumed session is
    # taken again only after it grew, and a finished one is never taken twice.
    def done(self) -> dict:
        try:
            return json.loads((self.root / "done.json").read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def mark_done(self, session_id: str, size: int) -> None:
        # The sweep (session start) and the worker both write here; a short lock of its own keeps
        # one from dropping the other's entry. Not the worker lock, which the worker already holds.
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / "done.lock", "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                d = self.done()
                d[session_id] = size
                _write_atomic(self.root / "done.json", d)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _requeue(self, item: dict, rounds: int) -> None:
        clean = {k: v for k, v in item.items() if k not in ("error", "last_error")}
        self.enqueue(dict(clean, attempts=0, retry_rounds=rounds))
        (self._dir("failed") / f"{_name(item['session_id'])}.json").unlink(missing_ok=True)

    def retry_due(self, now_ts: float, after_s: float, max_rounds: int) -> list[str]:
        """Move failures older than after_s back to pending, at most max_rounds times per session."""
        ids = []
        folder = self._dir("failed")
        for item in self.failed():
            rounds = int(item.get("retry_rounds", 0))
            try:
                age = now_ts - (folder / f"{_name(item['session_id'])}.json").stat().st_mtime
            except OSError:
                continue
            if rounds < max_rounds and age >= after_s:
                self._requeue(item, rounds + 1)
                ids.append(item["session_id"])
        return ids

    def retry_all(self) -> list[str]:
        """Manual retry: every failure goes back to pending now."""
        ids = []
        for item in self.failed():
            self._requeue(item, int(item.get("retry_rounds", 0)))
            ids.append(item["session_id"])
        return ids

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
