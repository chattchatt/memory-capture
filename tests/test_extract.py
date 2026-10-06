import json
import subprocess

import pytest

from memory_capture.extract import ClaudeCliExtractor, ExtractionError, parse_candidates


class FakeRun:
    """Test double for subprocess.run (the process seam)."""

    def __init__(self, stdout="", returncode=0, exc=None):
        self.stdout, self.returncode, self.exc, self.calls = stdout, returncode, exc, []

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "err")


def wrap(obj):
    return json.dumps({"type": "result", "result": "```json\n" + json.dumps(obj) + "\n```"})


def test_parse_accepts_fenced_json():
    assert parse_candidates("```json\n{\"candidates\": [{\"name\": \"a\"}]}\n```") == [{"name": "a"}]


def test_parse_rejects_garbage():
    with pytest.raises(ExtractionError):
        parse_candidates("I could not find anything")


def test_cli_runs_bare_child_with_guard_env_and_returns_candidates():
    run = FakeRun(stdout=wrap({"candidates": [{"name": "a"}]}))
    ex = ClaudeCliExtractor(claude_bin="claude", run=run, base_env={"PATH": "/bin"})
    assert ex.extract("USER: hi", {"cwd": "/w"}) == [{"name": "a"}]
    args, kw = run.calls[0]
    assert args[:2] == ["claude", "-p"]
    assert "--bare" not in args  # bare mode skips OAuth login, so subscription users fail
    assert '"disableAllHooks": true' in args[args.index("--settings") + 1]
    assert kw["env"]["MEMORY_CAPTURE_CHILD"] == "1" and kw["timeout"] > 0


def test_cli_passes_model_when_configured():
    run = FakeRun(stdout=wrap({"candidates": []}))
    ClaudeCliExtractor(run=run, base_env={}, model="sonnet").extract("x", {})
    args = run.calls[0][0]
    assert args[args.index("--model") + 1] == "sonnet"


def test_cli_nonzero_exit_and_timeout_become_extraction_errors():
    with pytest.raises(ExtractionError):
        ClaudeCliExtractor(run=FakeRun(returncode=1), base_env={}).extract("x", {})
    with pytest.raises(ExtractionError):
        ClaudeCliExtractor(run=FakeRun(exc=subprocess.TimeoutExpired("claude", 1)), base_env={}).extract("x", {})
