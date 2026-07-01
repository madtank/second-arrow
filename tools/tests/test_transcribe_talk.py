import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "transcribe_talk.py"
SPEC = importlib.util.spec_from_file_location("transcribe_talk", MODULE_PATH)
transcribe_talk = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(transcribe_talk)


def test_slugify_keeps_talk_names_readable():
    assert transcribe_talk.slugify("260612(short)_Patience.mp3") == "260612-short-patience"
    assert transcribe_talk.slugify("Goodwill Is a Strength!") == "goodwill-is-a-strength"


def test_markdown_includes_source_metadata_and_timestamped_segments():
    result = {
        "text": "Patience means not wearing the burden all the time.",
        "segments": [
            {"start": 0.0, "end": 5.5, "text": "Patience means not wearing the burden."},
            {"start": 65.2, "end": 72.0, "text": "Don't just wear them all the time."},
        ],
    }

    markdown = transcribe_talk.render_markdown(
        result,
        title="Patience",
        teacher="Thanissaro Bhikkhu",
        source_url="https://example.test/patience",
        model="mlx-community/whisper-tiny",
    )

    assert "# Patience" in markdown
    assert "Teacher: Thanissaro Bhikkhu" in markdown
    assert "Source: https://example.test/patience" in markdown
    assert "Model: mlx-community/whisper-tiny" in markdown
    assert "- [00:00-00:05] Patience means not wearing the burden." in markdown
    assert "- [01:05-01:12] Don't just wear them all the time." in markdown


def test_guess_title_from_audio_path_removes_date_prefix_and_extension():
    assert transcribe_talk.guess_title(Path("/tmp/260612(short)_Patience.mp3")) == "Patience"


def test_clean_result_drops_repetitive_trailing_hallucination():
    result = {
        "text": "Real teaching. posted posted posted posted posted posted posted posted posted posted posted posted",
        "segments": [
            {"start": 0.0, "end": 3.0, "text": "Real teaching."},
            {
                "start": 3.0,
                "end": 3.0,
                "text": "posted posted posted posted posted posted posted posted posted posted posted posted",
            },
        ],
    }

    cleaned = transcribe_talk.clean_result(result)

    assert cleaned["text"] == "Real teaching."
    assert cleaned["segments"] == [{"start": 0.0, "end": 3.0, "text": "Real teaching."}]


def test_clean_result_drops_short_phrase_stretched_across_silent_tail():
    result = {
        "text": "Stick with it. Relying on your strengths.",
        "segments": [
            {"start": 220.0, "end": 228.0, "text": "Stick with it."},
            {"start": 228.0, "end": 258.0, "text": "Relying on your strengths."},
        ],
    }

    cleaned = transcribe_talk.clean_result(result)

    assert cleaned["text"] == "Stick with it."
    assert cleaned["segments"] == [{"start": 220.0, "end": 228.0, "text": "Stick with it."}]
