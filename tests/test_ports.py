import subprocess
from types import SimpleNamespace

from memory_capture.ports import git_root


def fake_run(returncode=0, stdout="", raises=None):
    def run(args, **kw):
        if raises:
            raise raises
        return SimpleNamespace(returncode=returncode, stdout=stdout)
    return run


def test_git_root_returns_toplevel():
    assert git_root("/work/repo/sub", runner=fake_run(stdout="/work/repo\n")) == "/work/repo"


def test_git_root_falls_back_to_cwd_outside_repo():
    assert git_root("/tmp/x", runner=fake_run(returncode=128)) == "/tmp/x"


def test_git_root_falls_back_when_git_missing():
    assert git_root("/tmp/x", runner=fake_run(raises=FileNotFoundError())) == "/tmp/x"


def test_git_root_falls_back_on_timeout():
    err = subprocess.TimeoutExpired("git", 5)
    assert git_root("/tmp/x", runner=fake_run(raises=err)) == "/tmp/x"
