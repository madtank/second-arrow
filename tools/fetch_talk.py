#!/usr/bin/env python3
# /// script
# dependencies = ["yt-dlp"]
# ///
"""Fetch a dhamma talk into library/<slug>/ with a transcript.

- YouTube URLs: use captions when available (manual preferred over auto);
  otherwise download audio and transcribe locally via transcribe_talk.py.
- Direct audio URLs (.mp3/.m4a/...): download and transcribe.
- HTML pages (e.g. dhammatalks.org): find the audio link, then as above.

Run with:
    uv run tools/fetch_talk.py <url> --teacher "Ajahn Brahm" --themes "anger, patience"
"""

import argparse
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".opus")
LIBRARY = Path("library")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "talk"


def classify_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if parsed.path.lower().endswith(AUDIO_EXTENSIONS):
        return "audio"
    return "page"


def find_audio_link(html: str, base_url: str) -> str | None:
    for match in re.finditer(r'href="([^"]+)"', html):
        href = match.group(1)
        if href.lower().split("?")[0].endswith(AUDIO_EXTENSIONS):
            return urllib.parse.urljoin(base_url, href)
    return None


def parse_vtt(vtt: str) -> str:
    lines = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if (
            not line
            or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE"))
            or "-->" in line
            or line.isdigit()
        ):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        # Rolling captions repeat the previous line; keep only new text.
        if lines and line == lines[-1]:
            continue
        lines.append(line)
    deduped = []
    for line in lines:
        if deduped and deduped[-1].endswith(line):
            continue
        if deduped and line.startswith(deduped[-1]):
            deduped[-1] = line
            continue
        deduped.append(line)
    return " ".join(deduped)


def render_transcript_markdown(*, text: str, title: str, teacher: str, source_url: str, origin: str) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- Teacher: {teacher}",
            f"- Source: {source_url}",
            f"- Origin: {origin}",
            "",
            "## Full Transcript",
            "",
            text.strip(),
            "",
        ]
    )


def index_entry(*, slug: str, title: str, teacher: str, source_url: str, themes: str) -> str:
    return "\n".join(
        [
            f"## {slug}",
            f"- **Title:** {title}",
            f"- **Teacher:** {teacher}",
            f"- **Source:** {source_url}",
            f"- **Themes:** {themes}",
            f"- **Path:** library/{slug}/",
            "",
        ]
    )


def update_index(index_path: Path, *, slug: str, entry: str) -> None:
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
    else:
        content = (
            "# Library Index\n\n"
            "One entry per ingested talk. The guide reads this to find teachings by theme.\n\n"
        )
    if f"## {slug}\n" in content:
        return
    if not content.endswith("\n\n"):
        content = content.rstrip("\n") + "\n\n"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(content + entry, encoding="utf-8")


def fetch_youtube(url: str, talk_dir: Path) -> dict:
    """Return {'title', 'uploader', 'transcript_text' or None, 'audio_path' or None}."""
    import yt_dlp

    common = {"quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(common) as ydl:
        info = ydl.extract_info(url, download=False)
    title = info.get("title") or "talk"
    uploader = info.get("uploader") or ""

    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    caption_tracks = None
    for source in (subs, autos):
        for lang, tracks in source.items():
            if lang.startswith("en"):
                caption_tracks = tracks
                break
        if caption_tracks:
            break

    if caption_tracks:
        vtt_url = next((t["url"] for t in caption_tracks if t.get("ext") == "vtt"), None)
        if vtt_url:
            with urllib.request.urlopen(vtt_url) as resp:
                vtt = resp.read().decode("utf-8", errors="replace")
            text = parse_vtt(vtt)
            if text:
                return {"title": title, "uploader": uploader, "transcript_text": text, "audio_path": None}

    audio_target = talk_dir / "audio.m4a"
    opts = {
        **common,
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(talk_dir / "audio.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    audio_path = next(talk_dir.glob("audio.*"), audio_target)
    return {"title": title, "uploader": uploader, "transcript_text": None, "audio_path": audio_path}


def download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "second-arrow-study/1.0"})
    with urllib.request.urlopen(request) as resp, open(dest, "wb") as out:
        out.write(resp.read())
    return dest


def transcribe(audio_path: Path, *, talk_dir: Path, title: str, teacher: str, source_url: str, model: str) -> None:
    tool = Path(__file__).resolve().parent / "transcribe_talk.py"
    subprocess.run(
        [
            "uv", "run", str(tool), str(audio_path),
            "--title", title, "--teacher", teacher,
            "--source-url", source_url, "--model", model,
            "--out-dir", str(talk_dir),
        ],
        check=True,
    )
    slug = slugify(title)
    for ext in ("json", "md"):
        produced = talk_dir / f"{slug}.{ext}"
        if produced.exists():
            produced.rename(talk_dir / f"transcript.{ext}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Talk URL: YouTube, direct audio, or a page containing an audio link")
    parser.add_argument("--title", help="Talk title (defaults to metadata or URL filename)")
    parser.add_argument("--teacher", default="", help="Teacher name (defaults to YouTube uploader if known)")
    parser.add_argument("--themes", default="", help="Comma-separated themes for the library index")
    parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="MLX Whisper model used when local transcription is needed",
    )
    parser.add_argument("--library", type=Path, default=LIBRARY, help="Library root directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    kind = classify_url(args.url)

    if kind == "youtube":
        provisional = args.title or "talk"
        talk_dir = args.library / slugify(provisional)
        talk_dir.mkdir(parents=True, exist_ok=True)
        result = fetch_youtube(args.url, talk_dir)
        title = args.title or result["title"]
        teacher = args.teacher or result["uploader"] or "Unknown"
        slug = slugify(title)
        final_dir = args.library / slug
        if final_dir != talk_dir:
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            talk_dir.rename(final_dir)
        if result["transcript_text"]:
            (final_dir / "transcript.md").write_text(
                render_transcript_markdown(
                    text=result["transcript_text"], title=title, teacher=teacher,
                    source_url=args.url, origin="youtube captions",
                ),
                encoding="utf-8",
            )
        else:
            audio_path = next(final_dir.glob("audio.*"))
            transcribe(audio_path, talk_dir=final_dir, title=title, teacher=teacher,
                       source_url=args.url, model=args.model)
    else:
        if kind == "page":
            request = urllib.request.Request(args.url, headers={"User-Agent": "second-arrow-study/1.0"})
            with urllib.request.urlopen(request) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            audio_url = find_audio_link(html, args.url)
            if not audio_url:
                raise SystemExit(f"No audio link found on page: {args.url}")
        else:
            audio_url = args.url
        filename = Path(urllib.parse.urlparse(audio_url).path).name
        title = args.title or re.sub(r"^\d{6}(?:\([^)]*\))?[_ -]*", "", Path(filename).stem).replace("_", " ").replace("-", " ").strip().title()
        teacher = args.teacher or "Unknown"
        slug = slugify(title)
        talk_dir = args.library / slug
        audio_path = download_file(audio_url, talk_dir / f"audio{Path(filename).suffix or '.mp3'}")
        transcribe(audio_path, talk_dir=talk_dir, title=title, teacher=teacher,
                   source_url=args.url, model=args.model)

    slug = slugify(title)
    update_index(
        args.library / "INDEX.md",
        slug=slug,
        entry=index_entry(slug=slug, title=title, teacher=teacher, source_url=args.url,
                          themes=args.themes or "untagged"),
    )
    print(f"Ingested into library/{slug}/")


if __name__ == "__main__":
    main()
