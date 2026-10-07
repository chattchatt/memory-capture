"""Real-extractor smoke test: runs the real `claude -p` once on a tiny fake dialogue.

Not part of `make test` / `make check` (it needs a login and costs a model call).
Catches fake-vs-real drift, e.g. a CLI flag that the test double accepts but the real CLI rejects.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_capture.extract import ClaudeCliExtractor, ExtractionError  # noqa: E402

DIALOGUE = ("USER: Please always write reports as tables, not bullet lists.\n"
            "ASSISTANT: Understood, I will use tables for reports from now on.\n"
            "USER: Good. Remember that.\n")


def main() -> int:
    try:
        cands = ClaudeCliExtractor(timeout_s=120).extract(DIALOGUE, {"existing": "(none)"})
    except ExtractionError as e:
        print(f"FAIL: {e}")
        return 1
    print(f"OK: real extractor returned {len(cands)} candidate(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
