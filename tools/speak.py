#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-audio", "misaki[en]"]
# ///
"""Speak text aloud into an audio file, locally.

Engines:
- kokoro (default): Kokoro-82M via mlx-audio. Natural voice, Apple Silicon.
- say: macOS built-in TTS. Robotic but dependency-free fallback.

The timing map: the kokoro engine renders per-chunk wav files and
concatenates them, so it KNOWS where every chunk starts — measured from
the wav sample counts before encoding, never guessed. Whenever output is
produced via that chunk concat it also writes `<output-stem>.segments.json`
next to the audio ({"segments": [{"start": <seconds>, "text": "<chunk>"}]});
a single-chunk input honestly yields one segment at 0.0. The say engine
renders in one piece and has no chunk timings: it writes NO map and
removes a stale sibling map so the map never outlives the audio it
described. The shelf uses the map to make a spoken reading's text
click-to-seek.

Run with:
    uv run tools/speak.py --file library/<slug>/primer.md -o library/<slug>/primer.mp3
    uv run tools/speak.py --text "Hello" -o /tmp/hello.mp3 --engine say
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

KOKORO_MODEL = "prince-canuma/Kokoro-82M"
DEFAULT_VOICE = "af_heart"


def prepare_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        is_list_item = bool(re.match(r"^[-*+]\s+", line))
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = line.replace("**", "").replace("*", "").replace("`", "")
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            if is_list_item and not line.endswith((".", "!", "?", ":", ";", "—")):
                line += "."
            lines.append(line)
    sentences = []
    for line in lines:
        if sentences and not sentences[-1].rstrip().endswith((".", "!", "?", ":", ";", "—")):
            sentences[-1] = sentences[-1].rstrip() + "."
        sentences.append(line)
    return " ".join(sentences).strip()


def chunk_text(text: str, max_chars: int = 400) -> list[str]:
    """Split text into sentence-boundary chunks of at most max_chars.

    A single sentence longer than max_chars stays whole (its own chunk).
    """
    sentences = [s for s in re.split(r"(?<=[.!?;:])\s+", text.strip()) if s]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        chunks.append(current)
    return chunks


def segments_from_durations(chunks: list[str], durations: list[float]) -> list[dict]:
    """The timing map's offset assembly: chunk i starts where chunks
    0..i-1 end. Pure — durations are measured elsewhere (wav sample
    counts), one total per chunk, and must pair up with the chunks.
    """
    if len(chunks) != len(durations):
        raise ValueError(
            f"{len(chunks)} chunks but {len(durations)} durations — "
            "every chunk needs its measured length"
        )
    segments: list[dict] = []
    offset = 0.0
    for chunk, duration in zip(chunks, durations):
        segments.append({"start": round(offset, 3), "text": chunk})
        offset += duration
    return segments


def wav_duration(path: Path) -> float:
    """Exact seconds from a wav's own sample count — the pre-encode
    truth, so offsets never drift with the mp3 encoder."""
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def write_segments_json(out_path: Path, segments: list[dict]) -> Path:
    """Write the timing map next to the audio: reading.mp3 →
    reading.segments.json, {"segments": [{"start", "text"}]}."""
    path = out_path.with_suffix(".segments.json")
    path.write_text(
        json.dumps({"segments": segments}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def say_commands(text: str, out_path: Path) -> list[list[str]]:
    aiff = str(out_path.with_suffix(".aiff"))
    return [
        ["say", "-o", aiff, text],
        ["ffmpeg", "-y", "-loglevel", "error", "-i", aiff, str(out_path)],
    ]


def speak_with_say(text: str, out_path: Path) -> None:
    for cmd in say_commands(text, out_path):
        subprocess.run(cmd, check=True)
    out_path.with_suffix(".aiff").unlink(missing_ok=True)
    # Honesty over convenience: say renders in one piece, so there are no
    # chunk timings to map — and a stale map from an earlier kokoro run
    # must never outlive the audio it described.
    out_path.with_suffix(".segments.json").unlink(missing_ok=True)


def _patch_kokoro_sinegen() -> None:
    """Work around a length-rounding bug in mlx-audio's Kokoro port.

    SineGen._f02sine round-trips f0 through interpolate() with
    scale_factor=1/300 then 300; interpolate sizes its output with
    ceil(length * scale_factor), and float error makes ceil overshoot by
    one frame for many lengths, so the sine waves come back 300 samples
    longer than uv and crash on broadcast ("Shapes (1,N,1) and (1,N+300,9)
    cannot be broadcast"). Trim to the input length, which is what the
    reference PyTorch implementation guarantees.
    """
    from mlx_audio.tts.models.kokoro import istftnet

    if getattr(istftnet.SineGen, "_second_arrow_trim_patch", False):
        return
    original = istftnet.SineGen._f02sine

    def _f02sine_trimmed(self, f0_values):
        sines = original(self, f0_values)
        return sines[:, : f0_values.shape[1], :]

    istftnet.SineGen._f02sine = _f02sine_trimmed
    istftnet.SineGen._second_arrow_trim_patch = True


def speak_with_kokoro(text: str, out_path: Path, *, voice: str, speed: float) -> None:
    import io
    from contextlib import redirect_stdout

    from mlx_audio.tts.generate import generate_audio
    from mlx_audio.tts.utils import load_model

    _patch_kokoro_sinegen()

    # Kokoro's MLX istftnet crashes on long inputs (broadcast shape
    # mismatch), so feed it small sentence chunks — one generate call per
    # chunk, one wav per internal segment — and concatenate everything
    # ourselves with ffmpeg's concat demuxer.
    # generate_audio swallows its own exceptions (prints them and returns),
    # so a crash can leave partial output. Scanning its captured stdout for
    # error lines is what keeps a mid-chunk crash from becoming silently
    # truncated audio.
    model = load_model(model_path=KOKORO_MODEL)
    chunks = chunk_text(text)
    with tempfile.TemporaryDirectory() as tmp:
        wav_files: list[Path] = []
        chunk_durations: list[float] = []
        for i, chunk in enumerate(chunks):
            prefix = f"chunk{i:03d}"
            log = io.StringIO()
            with redirect_stdout(log):
                generate_audio(
                    text=chunk,
                    model=model,
                    voice=voice,
                    speed=speed,
                    output_path=tmp,
                    file_prefix=prefix,
                    audio_format="wav",
                    join_audio=False,
                    verbose=False,
                )
            errors = [line for line in log.getvalue().splitlines() if "Error" in line]
            if errors:
                raise RuntimeError(f"Kokoro failed on chunk {i}: {errors[0]}")
            chunk_wavs = sorted(
                Path(tmp).glob(f"{prefix}_*.wav"),
                key=lambda p: int(p.stem.rsplit("_", 1)[1]),
            )
            if not chunk_wavs:
                raise RuntimeError(f"Kokoro produced no audio for chunk {i}")
            wav_files.extend(chunk_wavs)
            # A chunk's length is the measured sum of its internal wavs —
            # sample counts, the pre-encode truth (see the module docstring).
            chunk_durations.append(sum(wav_duration(p) for p in chunk_wavs))
        list_file = Path(tmp) / "concat.txt"
        list_file.write_text("".join(f"file '{p}'\n" for p in wav_files), encoding="utf-8")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                str(out_path),
            ],
            check=True,
        )
    # The timing map rides along whenever the chunk concat produced the
    # audio — always, including the honest single-chunk case ([0.0, text]).
    segments = segments_from_durations(chunks, chunk_durations)
    print(f"Wrote {write_segments_json(out_path, segments)} ({len(segments)} segments)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Text to speak")
    source.add_argument("--file", type=Path, help="Markdown/text file to speak")
    parser.add_argument("-o", "--out", type=Path, required=True, help="Output audio file (.mp3)")
    parser.add_argument("--engine", choices=["kokoro", "say"], default="kokoro")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Kokoro voice name")
    parser.add_argument("--speed", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw = args.text if args.text is not None else args.file.read_text(encoding="utf-8")
    text = prepare_text(raw)
    if not text:
        raise SystemExit("Nothing to speak after cleaning the input.")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.engine == "say":
        speak_with_say(text, args.out)
    else:
        try:
            speak_with_kokoro(text, args.out, voice=args.voice, speed=args.speed)
        except Exception as error:  # noqa: BLE001 - fall back rather than fail a study session
            print(f"Kokoro failed ({error}); falling back to macOS say.", file=sys.stderr)
            speak_with_say(text, args.out)

    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
