import io
import json

import pytest

from memory_capture import cli
from memory_capture.apply import ApplyError
from memory_capture.inbox import Inbox


def write_config(tmp_path, cfg):
    p = tmp_path / "config.toml"
    p.write_text(f'projects_dir = "{cfg.projects_dir}"\nhome_dir = "{cfg.home_dir}"\n'
                 f'inbox_dir = "{cfg.inbox_dir}"\nkernel_dir = "{cfg.kernel_dir}"\n')
    return p


def test_parse_accept():
    assert cli.parse_accept("3, 1,3") == [1, 3]
    for bad in ("", "a"):
        with pytest.raises(ApplyError):
            cli.parse_accept(bad)


def test_show_lists_numbered_candidates():
    text = cli.render_show([{"session_id": "s1", "cwd": "/w", "candidates": [
        {"type": "feedback", "scope": "home", "title": "T", "summary": "S", "body": "B"}]}])
    assert "1. [feedback/home] T — S" in text and "B" in text


def test_hook_end_always_exits_zero_even_on_garbage(tmp_path, cfg, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert cli.main(["--config", str(write_config(tmp_path, cfg)), "hook-end"]) == 0


def test_hook_start_prints_hook_json(tmp_path, cfg, monkeypatch, capsys):
    Inbox(cfg.inbox_dir).write_candidates("s1", {"session_id": "s1", "candidates": [{"name": "a"}]})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"source": "clear"})))
    assert cli.main(["--config", str(write_config(tmp_path, cfg)), "hook-start"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_apply_error_returns_2(tmp_path, cfg, capsys):
    assert cli.main(["--config", str(write_config(tmp_path, cfg)), "apply", "nope", "--accept", "1"]) == 2
    assert "no candidates" in capsys.readouterr().err
