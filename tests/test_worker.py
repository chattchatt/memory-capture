import json

from conftest import FIXTURES, FakeExtractor

from memory_capture.extract import ExtractionError
from memory_capture.inbox import Inbox
from memory_capture.worker import process_pending


def queue(cfg, tmp_path, transcript=True):
    t = tmp_path / "t.jsonl"
    if transcript:
        t.write_text((FIXTURES / "transcript.jsonl").read_text())
    Inbox(cfg.inbox_dir).enqueue({"session_id": "abc123", "transcript_path": str(t), "cwd": "/w/demo", "reason": "clear", "queued_at": "x"})


CAND = {"name": "feedback_tables", "type": "feedback", "scope": "home", "title": "Reports as tables",
        "summary": "Write reports as tables", "body": "Use tables.\n\n**Why:** asked.\n**How to apply:** reports."}


def test_worker_writes_candidates_and_clears_pending(cfg, clock, tmp_path):
    queue(cfg, tmp_path)
    fake = FakeExtractor([CAND])
    process_pending(cfg, fake, clock)
    inbox = Inbox(cfg.inbox_dir)
    assert inbox.pending() == []
    got = inbox.candidates()
    assert got[0]["session_id"] == "abc123" and got[0]["candidates"][0]["name"] == "feedback_tables"
    dialogue, ctx = fake.calls[0]
    assert "Always do tables" in dialogue and ctx["cwd"] == "/w/demo"


def test_worker_caps_candidates(cfg, clock, tmp_path):
    cfg.max_candidates = 1
    queue(cfg, tmp_path)
    process_pending(cfg, FakeExtractor([CAND, dict(CAND, name="feedback_other")]), clock)
    assert len(Inbox(cfg.inbox_dir).candidates()[0]["candidates"]) == 1


def test_worker_drops_invalid_candidates(cfg, clock, tmp_path):
    queue(cfg, tmp_path)
    bad = [dict(CAND, name="../evil"), dict(CAND, type="secret"), {"name": "x"}]
    process_pending(cfg, FakeExtractor(bad + [CAND]), clock)
    assert [c["name"] for c in Inbox(cfg.inbox_dir).candidates()[0]["candidates"]] == ["feedback_tables"]


def test_no_candidates_means_no_notice(cfg, clock, tmp_path):
    queue(cfg, tmp_path)
    process_pending(cfg, FakeExtractor([]), clock)
    assert Inbox(cfg.inbox_dir).candidates() == [] and Inbox(cfg.inbox_dir).pending() == []


def test_missing_transcript_is_failed_not_retried(cfg, clock, tmp_path):
    queue(cfg, tmp_path, transcript=False)
    process_pending(cfg, FakeExtractor([CAND]), clock)
    inbox = Inbox(cfg.inbox_dir)
    assert inbox.pending() == [] and inbox.failed()[0]["error"].startswith("transcript")


def test_extractor_error_retries_then_fails(cfg, clock, tmp_path):
    queue(cfg, tmp_path)
    boom = FakeExtractor(error=ExtractionError("timeout"))
    for _ in range(3):
        process_pending(cfg, boom, clock)
    inbox = Inbox(cfg.inbox_dir)
    assert inbox.pending() == [] and json.dumps(inbox.failed()[0]).count("timeout") >= 1
    assert len(boom.calls) == 3
