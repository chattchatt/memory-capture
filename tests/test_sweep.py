"""Sweep: sessions that never sent SessionEnd (window killed, crash) and failures due for a retry."""

import json
import os

from conftest import FakeExtractor, FixedClock

from memory_capture.inbox import Inbox
from memory_capture.sweep import sweep
from memory_capture.worker import process_pending

NOW = FixedClock("2026-10-05T12:00:00")
HOUR = 3600


def transcript(cfg, sid, *, age_h=5.0, entrypoint="cli", cwd="/w/demo", size=200, slug="-w-demo"):
    """A fake transcript whose last write was age_h hours before NOW."""
    d = cfg.projects_dir / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.jsonl"
    recs = [{"type": "user", "entrypoint": entrypoint, "cwd": "/w/start", "sessionId": sid,
             "message": {"role": "user", "content": "x" * size}},
            {"type": "assistant", "entrypoint": entrypoint, "cwd": cwd, "sessionId": sid,
             "message": {"role": "assistant", "content": "ok"}}]
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    t = NOW.now_ts() - age_h * HOUR
    os.utime(p, (t, t))
    return p


def pending_ids(cfg):
    return [i["session_id"] for i in Inbox(cfg.inbox_dir).pending()]


def test_idle_session_without_end_is_queued_with_last_cwd(cfg):
    transcript(cfg, "killed1")
    assert sweep(cfg, NOW) == ["killed1"]
    item = Inbox(cfg.inbox_dir).pending()[0]
    assert item["cwd"] == "/w/demo" and item["reason"] == "sweep" and item["attempts"] == 0


def test_recent_session_is_left_alone(cfg):
    transcript(cfg, "live1", age_h=0.5)  # may still be open
    assert sweep(cfg, NOW) == []


def test_automated_and_old_and_small_sessions_are_skipped(cfg):
    transcript(cfg, "sdk1", entrypoint="sdk-cli")
    transcript(cfg, "old1", age_h=24 * 30)
    cfg.min_transcript_bytes = 10_000
    transcript(cfg, "small1", size=10)
    assert sweep(cfg, NOW) == []


def test_session_already_in_inbox_is_not_queued_twice(cfg):
    transcript(cfg, "s1")
    Inbox(cfg.inbox_dir).write_candidates("s1", {"session_id": "s1", "candidates": [{"name": "a"}]})
    assert sweep(cfg, NOW) == []
    assert sweep(cfg, NOW) == []


def test_processed_session_is_queued_again_only_after_it_grew(cfg, clock):
    p = transcript(cfg, "s1")
    sweep(cfg, NOW)
    process_pending(cfg, FakeExtractor([]), clock)
    assert Inbox(cfg.inbox_dir).done()["s1"] == p.stat().st_size
    assert sweep(cfg, NOW) == []
    transcript(cfg, "s1", size=cfg.min_transcript_bytes + 500)  # resumed and kept going
    assert sweep(cfg, NOW) == ["s1"]


def test_applied_before_ledger_counts_as_done(cfg):
    p = transcript(cfg, "s1")
    Inbox(cfg.inbox_dir).close_candidates("s1", {"session_id": "s1", "accepted": [1]})
    assert sweep(cfg, NOW) == []
    assert Inbox(cfg.inbox_dir).done()["s1"] == p.stat().st_size


def test_dry_run_queues_nothing(cfg):
    transcript(cfg, "killed1")
    assert sweep(cfg, NOW, dry_run=True) == ["killed1"]
    assert pending_ids(cfg) == []


def test_failed_item_is_retried_after_a_while_then_given_up(cfg):
    inbox = Inbox(cfg.inbox_dir)
    item = {"session_id": "f1", "transcript_path": "/t", "cwd": "/w", "attempts": 3}
    for rnd in range(cfg.max_retry_rounds):
        inbox.fail(item, "extraction failed: exit 1")
        f = cfg.inbox_dir / "failed" / "f1.json"
        os.utime(f, (NOW.now_ts() - 1 * HOUR,) * 2)
        sweep(cfg, NOW)
        assert pending_ids(cfg) == []  # not yet
        os.utime(f, (NOW.now_ts() - (cfg.retry_after_hours + 1) * HOUR,) * 2)
        sweep(cfg, NOW)
        got = inbox.pending()
        assert [i["session_id"] for i in got] == ["f1"]
        assert got[0]["attempts"] == 0 and got[0]["retry_rounds"] == rnd + 1
        item = got[0] | {"attempts": 3}
        inbox.drop_pending("f1")
    inbox.fail(item, "still failing")
    os.utime(cfg.inbox_dir / "failed" / "f1.json", (NOW.now_ts() - 100 * HOUR,) * 2)
    sweep(cfg, NOW)
    assert pending_ids(cfg) == [] and [f["session_id"] for f in inbox.failed()] == ["f1"]


def test_retry_all_moves_every_failure_back(cfg):
    inbox = Inbox(cfg.inbox_dir)
    for sid in ("a", "b"):
        inbox.fail({"session_id": sid, "transcript_path": "/t", "attempts": 3, "last_error": "x"}, "x")
    assert sorted(inbox.retry_all()) == ["a", "b"]
    assert inbox.failed() == [] and all(i["attempts"] == 0 and "error" not in i for i in inbox.pending())
