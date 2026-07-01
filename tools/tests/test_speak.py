import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "speak.py"
SPEC = importlib.util.spec_from_file_location("speak", MODULE_PATH)
speak = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(speak)


def test_prepare_text_strips_markdown_headings_emphasis_and_links():
    md = "# Primer\n\nListen for the **two arrows** — see [this talk](https://x.test).\n"
    assert speak.prepare_text(md) == "Primer. Listen for the two arrows — see this talk."


def test_prepare_text_flattens_lists_into_sentences():
    md = "- first point\n- second point\n"
    assert speak.prepare_text(md) == "first point. second point."


def test_prepare_text_collapses_blank_lines_and_whitespace():
    md = "one\n\n\n  two   three\n"
    assert speak.prepare_text(md) == "one. two three"


def test_prepare_text_drops_code_blocks():
    md = "before\n```\nuv run something\n```\nafter\n"
    assert speak.prepare_text(md) == "before. after"


def test_chunk_text_splits_on_sentence_boundaries_within_limit():
    text = "One two. Three four. Five six."
    chunks = speak.chunk_text(text, max_chars=20)
    assert chunks == ["One two. Three four.", "Five six."]
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert " ".join(chunks) == text


def test_chunk_text_keeps_oversized_sentence_whole():
    text = "This single sentence is much longer than the limit."
    assert speak.chunk_text(text, max_chars=10) == [text]


def test_say_command_builds_aiff_then_ffmpeg_conversion():
    cmds = speak.say_commands("hello world", Path("/tmp/out.mp3"))
    assert cmds[0][:2] == ["say", "-o"]
    assert cmds[0][2].endswith(".aiff")
    assert cmds[1][0] == "ffmpeg"
    assert cmds[1][-1] == "/tmp/out.mp3"
