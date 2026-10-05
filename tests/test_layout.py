from conftest import FakeGitRoot

from memory_capture.layout import folder_memory_dir, home_memory_dir, slug_for


def test_slug_matches_claude_code_scheme():
    assert slug_for("/Users/me/dev/r_u_real") == "-Users-me-dev-r_u_real"
    assert slug_for("/Users/me/.claude/projects") == "-Users-me--claude-projects"


def test_folder_memory_uses_git_root(cfg):
    git = FakeGitRoot({"/w/repo/sub": "/w/repo"})
    assert folder_memory_dir(cfg, "/w/repo/sub", git) == cfg.projects_dir / "-w-repo" / "memory"


def test_home_memory_dir(cfg):
    assert home_memory_dir(cfg) == cfg.projects_dir / slug_for(str(cfg.home_dir)) / "memory"
