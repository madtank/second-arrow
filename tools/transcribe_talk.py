#!/usr/bin/env python3
# /// script
# dependencies = ["mlx-whisper"]
# ///
"""Transcribe a local Dhamma talk audio file into reusable notes.

Run with:
    uv run tools/transcribe_talk.py /path/to/talk.mp3 --source-url https://...
"""

import argparse
import json
import re
from pathlib import Path


def slugify(value: str) -> str:
    stem = Path(value).stem
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return slug or "talk"


def guess_title(audio_path: Path) -> str:
    title = audio_path.stem
    title = re.sub(r"^\d{6}(?:\([^)]*\))?[_ -]*", "", title)
    title = title.replace("_", " ").replace("-", " ").strip()
    return title or audio_path.stem


def render_markdown(result: dict, *, title: str, teacher: str, source_url: str, model: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Teacher: {teacher}",
        f"- Source: {source_url}",
        f"- Model: {model}",
        "",
        "## Full Transcript",
        "",
        str(result.get("text", "")).strip(),
        "",
        "## Segments",
        "",
    ]

    for segment in result.get("segments", []):
        start = format_timestamp(float(segment.get("start", 0)))
        end = format_timestamp(float(segment.get("end", 0)))
        text = str(segment.get("text", "")).strip()
        if text:
            lines.append(f"- [{start}-{end}] {text}")

    lines.append("")
    return "\n".join(lines)


def clean_result(result: dict) -> dict:
    segments = list(result.get("segments", []))
    while segments and is_trailing_artifact(segments[-1]):
        segments.pop()

    if len(segments) == len(result.get("segments", [])):
        return result

    cleaned = dict(result)
    cleaned["segments"] = segments
    cleaned["text"] = " ".join(str(segment.get("text", "")).strip() for segment in segments).strip()
    return cleaned


def is_repetitive_hallucination(text: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if len(words) < 10:
        return False
    return len(set(words)) <= 2


def is_trailing_artifact(segment: dict) -> bool:
    text = str(segment.get("text", ""))
    if is_repetitive_hallucination(text):
        return True

    words = re.findall(r"[a-zA-Z']+", text)
    duration = float(segment.get("end", 0)) - float(segment.get("start", 0))
    return duration >= 12 and 0 < len(words) <= 6


def format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def transcribe_audio(audio_path: Path, *, model: str) -> dict:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model,
        verbose=False,
        language="en",
        initial_prompt="Dhamma talk. Thanissaro Bhikkhu. Ajaan Fuang. Buddhism. Patience. Defilements. Adze.",
    )
    return clean_result(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Local audio file to transcribe")
    parser.add_argument("--title", help="Talk title. Defaults to a title guessed from the filename.")
    parser.add_argument("--teacher", default="Thanissaro Bhikkhu", help="Teacher/source name")
    parser.add_argument("--source-url", default="", help="Original web page or audio URL")
    parser.add_argument(
        "--model",
        default="mlx-community/whisper-tiny",
        help="MLX Whisper model repo, e.g. mlx-community/whisper-large-v3-turbo",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("output/talks"), help="Directory for outputs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audio_path = args.audio.expanduser().resolve()
    if not audio_path.exists():
        raise SystemExit(f"Audio file not found: {audio_path}")

    title = args.title or guess_title(audio_path)
    slug = slugify(title)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    result = transcribe_audio(audio_path, model=args.model)
    json_path = args.out_dir / f"{slug}.json"
    markdown_path = args.out_dir / f"{slug}.md"

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(
        render_markdown(
            result,
            title=title,
            teacher=args.teacher,
            source_url=args.source_url,
            model=args.model,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
