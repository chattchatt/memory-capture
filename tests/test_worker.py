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


def test_second_worker_waits_while_first_holds_the_lock(cfg, clock, tmp_path):
    # launchd's worker and a manual `memory-capture work` ran the same item twice; the second run
    # overwrote the first one's 5 candidates with 3.
    queue(cfg, tmp_path)
    fake = FakeExtractor([CAND])
    with Inbox(cfg.inbox_dir).lock() as got:
        assert got
        process_pending(cfg, fake, clock)
    assert fake.calls == [] and [i["session_id"] for i in Inbox(cfg.inbox_dir).pending()] == ["abc123"]
    process_pending(cfg, fake, clock)
    assert len(fake.calls) == 1


def test_extractor_error_retries_then_fails(cfg, clock, tmp_path):
    queue(cfg, tmp_path)
    boom = FakeExtractor(error=ExtractionError("timeout"))
    for _ in range(3):
        process_pending(cfg, boom, clock)
    inbox = Inbox(cfg.inbox_dir)
    assert inbox.pending() == [] and json.dumps(inbox.failed()[0]).count("timeout") >= 1
    assert len(boom.calls) == 3


def test_new_extraction_adds_to_unconfirmed_candidates_instead_of_replacing(cfg, clock, tmp_path):
    # A session swept while still open is extracted once; when it really ends it is extracted again.
    # The user may not have confirmed the first set yet, so nothing from it may disappear.
    queue(cfg, tmp_path)
    process_pending(cfg, FakeExtractor([CAND]), clock)
    queue(cfg, tmp_path)
    later = dict(CAND, name="project_later", title="Later decision")
    process_pending(cfg, FakeExtractor([later]), clock)
    process_pending(cfg, FakeExtractor([]), clock)  # an empty later run changes nothing either
    queue(cfg, tmp_path)
    process_pending(cfg, FakeExtractor([dict(CAND, body="Use tables. (again)")]), clock)  # same name: kept once
    names = [c["name"] for c in Inbox(cfg.inbox_dir).candidates()[0]["candidates"]]
    assert names == ["feedback_tables", "project_later"]
