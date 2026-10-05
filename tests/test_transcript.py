from conftest import FIXTURES

from memory_capture.transcript import read_dialogue, render_dialogue


def test_contract_keeps_only_human_and_assistant_text():
    turns = read_dialogue(FIXTURES / "transcript.jsonl")
    assert turns == [
        ("user", "Please write the weekly report as a table, not prose."),
        ("assistant", "Done. I wrote it as a table."),
        ("user", "Good. Always do tables for reports."),
    ]


def test_skips_tool_results_thinking_sidechains_meta_and_bad_lines():
    texts = [t for _, t in read_dialogue(FIXTURES / "transcript.jsonl")]
    assert not any("file-a" in t or "hidden" in t or "sidechain" in t or "/clear" in t for t in texts)


def test_render_truncates_from_the_start_keeping_latest_turns():
    turns = [("user", "x" * 100), ("assistant", "y" * 100), ("user", "last")]
    out = render_dialogue(turns, max_chars=120)
    assert out.endswith("USER: last")
    assert len(out) <= 120
    assert "x" * 100 not in out


def test_missing_file_raises_file_not_found(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        read_dialogue(tmp_path / "nope.jsonl")
