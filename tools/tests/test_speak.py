import importlib.util
import json
import sys
import types
import wave
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


# --- the timing map: every chunk's start offset, measured, never guessed ---


def _write_wav(path: Path, seconds: float, framerate: int = 8000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(framerate)
        handle.writeframes(b"\x00\x00" * int(framerate * seconds))


def test_segments_from_durations_accumulates_offsets():
    segments = speak.segments_from_durations(
        ["First chunk.", "Second chunk.", "Third chunk."], [1.5, 2.25, 3.0]
    )
    assert segments == [
        {"start": 0.0, "text": "First chunk."},
        {"start": 1.5, "text": "Second chunk."},
        {"start": 3.75, "text": "Third chunk."},
    ]


def test_segments_from_durations_single_chunk_is_honest():
    # One chunk really does start at 0.0 — a single segment, no invention.
    assert speak.segments_from_durations(["All of it."], [4.2]) == [
        {"start": 0.0, "text": "All of it."}
    ]


def test_segments_from_durations_rejects_mismatched_lengths():
    import pytest

    with pytest.raises(ValueError):
        speak.segments_from_durations(["a", "b"], [1.0])


def test_wav_duration_reads_the_sample_count(tmp_path):
    path = tmp_path / "chunk.wav"
    _write_wav(path, seconds=1.5)
    assert speak.wav_duration(path) == 1.5


def test_write_segments_json_shape_and_sibling_path(tmp_path):
    out = tmp_path / "reading.mp3"
    written = speak.write_segments_json(
        out, [{"start": 0.0, "text": "One."}, {"start": 2.5, "text": "Two."}]
    )
    assert written == tmp_path / "reading.segments.json"
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data == {
        "segments": [
            {"start": 0.0, "text": "One."},
            {"start": 2.5, "text": "Two."},
        ]
    }


def test_speak_with_say_emits_no_map_and_removes_a_stale_one(
    monkeypatch, tmp_path
):
    # say renders in one piece — it has no chunk timings, so it writes no
    # map, and a stale map from an earlier kokoro run must not outlive
    # the audio it described.
    out = tmp_path / "reading.mp3"
    stale = tmp_path / "reading.segments.json"
    stale.write_text('{"segments": []}')
    monkeypatch.setattr(
        speak.subprocess, "run", lambda cmd, check: out.write_bytes(b"\x00")
    )
    speak.speak_with_say("hello", out)
    assert not stale.exists()


def _fake_mlx_audio(monkeypatch, tmp_path, chunk_wav_seconds):
    """Install a fake mlx_audio tree: generate_audio writes silent wavs of
    scripted durations (one call per chunk, possibly several wavs each)."""
    calls = iter(chunk_wav_seconds)

    def generate_audio(*, text, model, voice, speed, output_path,
                       file_prefix, audio_format, join_audio, verbose):
        for j, seconds in enumerate(next(calls)):
            _write_wav(Path(output_path) / f"{file_prefix}_{j:03d}.wav", seconds)

    class SineGen:
        def _f02sine(self, f0_values):
            return f0_values

    istftnet = types.ModuleType("mlx_audio.tts.models.kokoro.istftnet")
    istftnet.SineGen = SineGen
    kokoro = types.ModuleType("mlx_audio.tts.models.kokoro")
    kokoro.istftnet = istftnet
    models = types.ModuleType("mlx_audio.tts.models")
    models.kokoro = kokoro
    generate = types.ModuleType("mlx_audio.tts.generate")
    generate.generate_audio = generate_audio
    utils = types.ModuleType("mlx_audio.tts.utils")
    utils.load_model = lambda model_path: object()
    tts = types.ModuleType("mlx_audio.tts")
    tts.generate, tts.utils, tts.models = generate, utils, models
    mlx_audio = types.ModuleType("mlx_audio")
    mlx_audio.tts = tts
    for name, module in {
        "mlx_audio": mlx_audio,
        "mlx_audio.tts": tts,
        "mlx_audio.tts.generate": generate,
        "mlx_audio.tts.utils": utils,
        "mlx_audio.tts.models": models,
        "mlx_audio.tts.models.kokoro": kokoro,
        "mlx_audio.tts.models.kokoro.istftnet": istftnet,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_speak_with_kokoro_writes_the_measured_timing_map(monkeypatch, tmp_path):
    # Two chunks; the first renders as TWO internal wavs (1.0s + 0.5s) —
    # the second chunk's start is their measured sum, 1.5s.
    long_a = "Aa " * 130 + "ends here."   # > 400 chars: forces two chunks
    long_b = "Bb " * 100 + "closes now."
    text = f"{long_a} {long_b}"
    assert len(speak.chunk_text(text)) == 2
    _fake_mlx_audio(monkeypatch, tmp_path, [[1.0, 0.5], [2.0]])

    def fake_run(cmd, check):
        assert cmd[0] == "ffmpeg"
        Path(cmd[-1]).write_bytes(b"\x00")  # the concat "produces" the mp3

    monkeypatch.setattr(speak.subprocess, "run", fake_run)
    out = tmp_path / "reading.mp3"
    speak.speak_with_kokoro(text, out, voice="af_heart", speed=1.0)
    data = json.loads((tmp_path / "reading.segments.json").read_text())
    starts = [seg["start"] for seg in data["segments"]]
    texts = [seg["text"] for seg in data["segments"]]
    assert starts == [0.0, 1.5]
    assert texts == speak.chunk_text(text)
