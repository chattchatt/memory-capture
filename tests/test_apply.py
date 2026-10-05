import pytest

from conftest import FakeGitRoot

from memory_capture.apply import ApplyError, apply_candidates
from memory_capture.inbox import Inbox
from memory_capture.layout import folder_memory_dir, home_memory_dir

GIT = FakeGitRoot()
FB = {"name": "feedback_tables", "type": "feedback", "scope": "folder", "title": "Reports as tables",
      "summary": "Write reports as tables", "body": "Use tables.\n\n**Why:** asked.\n**How to apply:** reports."}
REF = {"name": "reference_vpn", "type": "reference", "scope": "home", "title": "VPN host",
       "summary": "Office VPN host", "body": "vpn.example.com"}


def stage(cfg, cands, cwd="/w/demo"):
    Inbox(cfg.inbox_dir).write_candidates("s1", {"session_id": "s1", "cwd": cwd, "candidates": cands})


def test_feedback_goes_to_kernel_with_folder_pointer(cfg, clock):
    stage(cfg, [FB])
    apply_candidates(cfg, "s1", [1], GIT, clock)
    body = cfg.kernel_dir / "feedback_tables.md"
    assert "type: feedback" in body.read_text() and "Use tables." in body.read_text()
    assert "(feedback_tables.md)" in (cfg.kernel_dir / "INDEX.md").read_text()
    fdir = folder_memory_dir(cfg, "/w/demo", GIT)
    idx = (fdir / "MEMORY.md").read_text()
    assert "(feedback_tables.md)" in idx and "INDEX.md" in idx.splitlines()[2]
    assert str(body) in (fdir / "feedback_tables.md").read_text()


def test_reference_goes_to_home_memory(cfg, clock):
    stage(cfg, [REF])
    apply_candidates(cfg, "s1", [1], GIT, clock)
    h = home_memory_dir(cfg)
    assert (h / "reference_vpn.md").exists() and "(reference_vpn.md)" in (h / "MEMORY.md").read_text()


def test_without_kernel_bodies_live_in_folder_memory(cfg, clock):
    cfg.kernel_dir = None
    stage(cfg, [FB])
    apply_candidates(cfg, "s1", [1], GIT, clock)
    assert "Use tables." in (folder_memory_dir(cfg, "/w/demo", GIT) / "feedback_tables.md").read_text()


def test_only_accepted_numbers_are_written_and_candidates_file_closed(cfg, clock):
    stage(cfg, [FB, REF])
    apply_candidates(cfg, "s1", [2], GIT, clock)
    assert not (cfg.kernel_dir / "feedback_tables.md").exists()
    assert (home_memory_dir(cfg) / "reference_vpn.md").exists()
    assert Inbox(cfg.inbox_dir).candidates() == []


def test_update_existing_appends_section(cfg, clock):
    cfg.kernel_dir.mkdir(parents=True)
    (cfg.kernel_dir / "feedback_tables.md").write_text("---\nname: feedback_tables\n---\n\nold\n")
    stage(cfg, [dict(FB, update_existing="feedback_tables", body="new rule")])
    apply_candidates(cfg, "s1", [1], GIT, clock)
    text = (cfg.kernel_dir / "feedback_tables.md").read_text()
    assert "old" in text and "new rule" in text and clock.today() in text


def test_refuses_to_overwrite_existing_body(cfg, clock):
    cfg.kernel_dir.mkdir(parents=True)
    (cfg.kernel_dir / "feedback_tables.md").write_text("keep me")
    stage(cfg, [FB])
    with pytest.raises(ApplyError):
        apply_candidates(cfg, "s1", [1], GIT, clock)
    assert (cfg.kernel_dir / "feedback_tables.md").read_text() == "keep me"


def test_refuses_phone_numbers(cfg, clock):
    stage(cfg, [dict(FB, body="call 010-1234-5678")])
    with pytest.raises(ApplyError):
        apply_candidates(cfg, "s1", [1], GIT, clock)
    assert not (cfg.kernel_dir / "feedback_tables.md").exists()


def test_rejects_out_of_range_numbers(cfg, clock):
    stage(cfg, [FB])
    with pytest.raises(ApplyError):
        apply_candidates(cfg, "s1", [3], GIT, clock)
