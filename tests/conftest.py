import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_capture.config import Config  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class FixedClock:
    """Test double for the clock seam."""

    def __init__(self, iso="2026-10-05T12:00:00"):
        self.iso = iso

    def now_iso(self):
        return self.iso

    def today(self):
        return self.iso[:10]


class FakeGitRoot:
    """Test double for the git-root seam: maps a cwd to a fixed project root."""

    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def __call__(self, cwd):
        return self.mapping.get(cwd, cwd)


class FakeExtractor:
    """Test double for the model seam: returns canned candidates or raises."""

    def __init__(self, candidates=None, error=None):
        self.candidates = candidates or []
        self.error = error
        self.calls = []

    def extract(self, dialogue, context):
        self.calls.append((dialogue, context))
        if self.error:
            raise self.error
        return self.candidates


@pytest.fixture
def cfg(tmp_path):
    home = tmp_path / "home"
    return Config(
        projects_dir=home / ".claude" / "projects",
        home_dir=home,
        inbox_dir=home / ".claude" / "memory-inbox",
        kernel_dir=home / "kernel",
        min_transcript_bytes=10,
        max_candidates=5,
    )


@pytest.fixture
def clock():
    return FixedClock()


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())
