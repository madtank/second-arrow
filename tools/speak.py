#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-audio", "misaki[en]"]
# ///
"""Speak text aloud into an audio file, locally.

Engines:
- kokoro (default): Kokoro-82M via mlx-audio. Natural voice, Apple Silicon.
- say: macOS built-in TTS. Robotic but dependency-free fallback.

Run with:
    uv run tools/speak.py --file library/<slug>/primer.md -o library/<slug>/primer.mp3
    uv run tools/speak.py --text "Hello" -o /tmp/hello.mp3 --engine say
"""

import argparse
import re
import subprocess
import sys
import tempfile
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


def speak_with_kokoro(text: str, out_path: Path, *, voice: str, speed: float) -> None:
    from mlx_audio.tts.generate import generate_audio

    with tempfile.TemporaryDirectory() as tmp:
        # With join_audio=True this writes a single <tmp>/speech.wav.
        # generate_audio swallows its own exceptions (prints and returns),
        # so the missing-file check below is the real failure detector.
        generate_audio(
            text=text,
            model=KOKORO_MODEL,
            voice=voice,
            speed=speed,
            output_path=tmp,
            file_prefix="speech",
            audio_format="wav",
            join_audio=True,
            verbose=False,
        )
        wav_files = sorted(Path(tmp).glob("speech*.wav"))
        if not wav_files:
            raise RuntimeError("Kokoro produced no audio output")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_files[0]), str(out_path)],
            check=True,
        )


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
