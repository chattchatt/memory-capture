import json

from conftest import FIXTURES, load_fixture

from memory_capture import hooks
from memory_capture.inbox import Inbox


def end_event(tmp_path, **over):
    ev = load_fixture("session_end.json")
    t = tmp_path / "t.jsonl"
    t.write_text((FIXTURES / "transcript.jsonl").read_text())
    ev["transcript_path"] = str(t)
    ev.update(over)
    return ev


def test_session_end_enqueues_pending_item(cfg, clock, tmp_path):
    hooks.on_session_end(end_event(tmp_path), cfg, clock, env={})
    items = Inbox(cfg.inbox_dir).pending()
    assert [i["session_id"] for i in items] == ["abc123"]
    assert items[0]["reason"] == "clear" and items[0]["queued_at"] == clock.iso


def test_session_end_ignores_resume_and_unknown_reasons(cfg, clock, tmp_path):
    hooks.on_session_end(end_event(tmp_path, reason="resume"), cfg, clock, env={})
    assert Inbox(cfg.inbox_dir).pending() == []


def test_session_end_skips_short_transcripts(cfg, clock, tmp_path):
    cfg.min_transcript_bytes = 10_000_000
    hooks.on_session_end(end_event(tmp_path), cfg, clock, env={})
    assert Inbox(cfg.inbox_dir).pending() == []


def test_session_end_is_noop_inside_extraction_child(cfg, clock, tmp_path):
    hooks.on_session_end(end_event(tmp_path), cfg, clock, env={"MEMORY_CAPTURE_CHILD": "1"})
    assert Inbox(cfg.inbox_dir).pending() == []


def test_session_end_never_raises_on_bad_input(cfg, clock):
    hooks.on_session_end({"reason": "clear"}, cfg, clock, env={})  # no transcript_path
    hooks.on_session_end({}, cfg, clock, env={})


def test_session_start_without_candidates_outputs_nothing(cfg):
    assert hooks.on_session_start(load_fixture("session_start.json"), cfg, env={}) is None


def test_session_start_announces_ready_candidates(cfg):
    inbox = Inbox(cfg.inbox_dir)
    inbox.write_candidates("abc123", {"session_id": "abc123", "cwd": "/w/demo", "candidates": [{"name": "a"}, {"name": "b"}]})
    out = hooks.on_session_start(load_fixture("session_start.json"), cfg, env={})
    ctx = out["hookSpecificOutput"]
    assert ctx["hookEventName"] == "SessionStart"
    assert "2" in ctx["additionalContext"] and "memory-capture show" in ctx["additionalContext"]
    json.dumps(out)


def test_session_start_ignores_compact_and_resume(cfg):
    Inbox(cfg.inbox_dir).write_candidates("abc123", {"session_id": "abc123", "candidates": [{"name": "a"}]})
    ev = load_fixture("session_start.json")
    for src in ("compact", "resume"):
        ev["source"] = src
        assert hooks.on_session_start(ev, cfg, env={}) is None
