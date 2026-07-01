# Second Arrow Study Space Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn this repo into a personal Buddhist study space: a guide persona (CLAUDE.md), a talk-ingest pipeline (fetch → captions or local Whisper → library/), local TTS for primers, a curated curriculum, and private journal/memory — per `docs/plans/2026-07-01-study-space-design.md`.

**Architecture:** Standalone `uv run` scripts in `tools/` with inline dependencies (PEP 723), tested with pytest via importlib file-loading (see existing `tools/tests/test_transcribe_talk.py` for the pattern). Private content lives in gitignored `library/`, `journal/`, `STUDY.md`. The guide is plain markdown instructions in `CLAUDE.md`.

**Tech Stack:** Python 3.12+, `uv`, `yt-dlp` (as a Python library — the Homebrew binary is broken on this machine, do NOT shell out to it), `mlx-whisper` (existing), `mlx-audio` + Kokoro for TTS with macOS `say` fallback, `ffmpeg` (installed at `/opt/homebrew/bin/ffmpeg`).

**Environment facts (verified 2026-07-01):**
- `uv` 0.4.29 at `/opt/homebrew/bin/uv`; `ffmpeg` and `/usr/bin/say` work.
- `/opt/homebrew/bin/yt-dlp` fails with "bad interpreter" — unusable as a CLI.
- Existing transcript artifacts: `output/talks/patience.json`, `output/talks/patience.md` (gitignored).
- `tools/transcribe_talk.py` + `tools/tests/test_transcribe_talk.py` exist but are UNTRACKED — commit them first.
- Run all tests with: `uv run --with pytest --with mlx-whisper pytest tools/tests/ -v` — plain `uv run pytest` won't see script inline deps. (Check the Makefile for an existing test target before inventing one.)

---

### Task 0: Commit the previous session's work

**Files:**
- Commit (already exist, untracked): `tools/transcribe_talk.py`, `tools/tests/test_transcribe_talk.py`
- Commit (already modified): `.gitignore`

**Step 1: Run the existing tests to confirm they pass**

Run: `uv run --with pytest --with mlx-whisper pytest tools/tests/test_transcribe_talk.py -v`
Expected: 5 passed. (mlx-whisper is only imported inside `transcribe_audio`, but include it so collection never breaks.)

**Step 2: Commit**

```bash
git add tools/ .gitignore
git commit -m "Add local MLX Whisper transcription tool for dhamma talks"
```

---

### Task 1: Restructure — private study dirs, gitignore, migrate Patience

**Files:**
- Modify: `.gitignore` (append after the `output/` line, around line 56)
- Create (local only, gitignored): `library/patience/transcript.json`, `library/patience/transcript.md`, `library/INDEX.md`, `journal/` (empty dir), `STUDY.md`

**Step 1: Append to `.gitignore`** (in the "Local Codex brainstorming boards" section):

```gitignore
# Private study space: ingested talks, personal journal, guide memory
library/
journal/
STUDY.md
```

**Step 2: Migrate the Patience transcript into the library layout**

```bash
mkdir -p library/patience journal
git mv output/talks/patience.json library/patience/transcript.json 2>/dev/null || mv output/talks/patience.json library/patience/transcript.json
mv output/talks/patience.md library/patience/transcript.md
```

(Plain `mv` — these files are gitignored, not tracked.) Also copy the audio if it still exists: `cp /tmp/second-arrow-patience.mp3 library/patience/audio.mp3` (skip silently if gone; the source URL is in the transcript metadata).

**Step 3: Seed `library/INDEX.md`:**

```markdown
# Library Index

One entry per ingested talk. The guide reads this to find teachings by theme.

## patience
- **Title:** Patience
- **Teacher:** Thanissaro Bhikkhu
- **Source:** https://www.dhammatalks.org/audio/morning/2026/260612-patience.html
- **Themes:** patience, anger, endurance, long-term practice
- **Path:** library/patience/
```

**Step 4: Seed `STUDY.md`:**

```markdown
# Study Memory

The guide reads this at session start and updates it at session end.

## Where we are
- Root cluster: anger, aversion, patience, the two arrows.
- Talk-first learner: prefers listening (eyes closed) and stories over textbook explanations.
- Currently reading *How to Solve Your Human Problems* — useful but hard to hold.

## Studied
- **Patience** (Thanissaro Bhikkhu, 2026-06-12): patience is not grim endurance;
  don't wear the burden all the time; notice strengths, not only weaknesses;
  the carpenter's adze-handle image for invisible long-term progress.

## Open questions
- Eightfold Path: wants to remember it without feeling dumb for forgetting.
- Mind vs brain curiosity (resonance lane, not doctrine).

## Candidate next steps
- An Ajahn Brahm talk on anger (warm, story-rich lane).
```

**Step 5: Verify privacy, then commit**

Run: `git status --short` — `library/`, `journal/`, `STUDY.md` must NOT appear. Then:

```bash
git add .gitignore
git commit -m "Carve out private study space: library/, journal/, STUDY.md"
```

---

### Task 2: The guide — CLAUDE.md

**Files:**
- Create: `CLAUDE.md` (repo root, committed)

**Step 1: Write `CLAUDE.md`.** Content requirements (write it warm and plain, not corporate; roughly this):

```markdown
# Second Arrow — Study Guide

This repo is a personal study space for learning Buddhism and working with
anger. When a session opens here, you are a **guide-teacher using real
teachings**, not a coding assistant and not a syllabus.

## On session start

1. Read `STUDY.md` (memory) and `library/INDEX.md` (what we have).
2. Ask, simply: **"Where are you right now?"** Then meet that answer.

## How to respond

- **"I'm angry" / upset right now** → keep it small: a short grounding
  practice, then ONE teaching drawn from a transcript in `library/`.
  No lecture. The Practice flow in the web app also exists for this.
- **Curious / "I want a story"** → offer a small tray: one talk or story,
  one plain-language concept, one practical reflection, one possible next
  resource. Not more.
- **"I listened to that talk"** → discussion mode: work through the
  transcript together, section by section — what landed, what confused,
  what met resistance.
- **"Play me something short"** → compose a 1–2 minute reflection grounded
  in quotes from studied transcripts, then render it:
  `uv run tools/speak.py --file <reflection.md> -o library/<slug>/custom-<name>.mp3`

## Hard rules

- **Teach from transcripts in `library/`.** If we don't have the source,
  say so and offer to fetch it — never confidently paraphrase a specific
  talk from training-data memory. Transcripts are working aids; the
  original audio is the authority.
- **Anger is the root cluster** (anger, aversion, patience, two arrows);
  other topics radiate out from it.
- AA, NDEs, psychology, mind/brain, AI/spirituality parallels are
  **resonance, not doctrine** — welcome, but never presented as proof.
- Downloads are explicit and single-item. Never bulk-scrape an archive.
- Journal content and STUDY.md are private; never commit or publish them.
- This is study material, not scripture, therapy, or medical advice.

## Tools

- Ingest a talk: `uv run tools/fetch_talk.py <url> --teacher "..." --themes "a, b"`
  (YouTube captions are used when available; otherwise audio is downloaded
  and transcribed locally with MLX Whisper.)
- Transcribe local audio: `uv run tools/transcribe_talk.py <file> --model mlx-community/whisper-large-v3-turbo`
- Speak text: `uv run tools/speak.py --file <md> -o <mp3>` (local Kokoro TTS; `--engine say` fallback)
- Tests: `uv run --with pytest --with mlx-whisper pytest tools/tests/ -v`

## The study loop (a full session)

1. Pick a talk (from `curriculum/`, or one the user brings).
2. Ingest if new (`fetch_talk.py`).
3. Read the transcript; write a 60–90 second **primer** — who the teacher
   is, what to listen for — save as `library/<slug>/primer.md`, optionally
   speak it to `primer.mp3`.
4. The user listens to the actual talk. Step back — that part is between
   them and the teacher.
5. Discuss. Then save a journal entry (`journal/YYYY-MM-DD.md`), update
   the talk's `notes.md`, and update `STUDY.md`.

## Session end

Always leave `STUDY.md` current: what was studied, what landed, open
questions, candidate next steps.

## Working on the code itself

The web app (`backend/`, `frontend/`) is dormant — leave it alone unless
asked. For tool changes: tests first (see `tools/tests/`), never let
private paths (`library/`, `journal/`, `STUDY.md`) become tracked.
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Add guide persona: sessions here open as a study guide"
```

---

### Task 3: fetch_talk.py — URL → library/<slug>/ with transcript

**Files:**
- Create: `tools/fetch_talk.py`
- Test: `tools/tests/test_fetch_talk.py`

The script classifies a URL (YouTube vs direct-audio vs dhammatalks HTML page), fetches captions when possible, downloads audio otherwise, transcribes when needed (by invoking `transcribe_talk.py` as a subprocess), writes `library/<slug>/`, and registers the talk in `library/INDEX.md`.

**Step 1: Write failing tests** — `tools/tests/test_fetch_talk.py`, using the same importlib pattern as the existing test file:

```python
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "fetch_talk.py"
SPEC = importlib.util.spec_from_file_location("fetch_talk", MODULE_PATH)
fetch_talk = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(fetch_talk)


def test_classify_url_youtube_watch_and_short_links():
    assert fetch_talk.classify_url("https://www.youtube.com/watch?v=abc123") == "youtube"
    assert fetch_talk.classify_url("https://youtu.be/abc123") == "youtube"


def test_classify_url_direct_audio():
    assert fetch_talk.classify_url("https://example.org/talks/anger.mp3") == "audio"
    assert fetch_talk.classify_url("https://example.org/talks/anger.m4a?x=1") == "audio"


def test_classify_url_html_page_treated_as_page():
    url = "https://www.dhammatalks.org/audio/morning/2026/260612-patience.html"
    assert fetch_talk.classify_url(url) == "page"


def test_find_audio_link_in_dhammatalks_page():
    html = '<a href="/mp3/morning/2026/260612-patience.mp3">Download</a>'
    base = "https://www.dhammatalks.org/audio/morning/2026/260612-patience.html"
    assert (
        fetch_talk.find_audio_link(html, base)
        == "https://www.dhammatalks.org/mp3/morning/2026/260612-patience.mp3"
    )


def test_find_audio_link_returns_none_when_absent():
    assert fetch_talk.find_audio_link("<p>no audio here</p>", "https://x.test/") is None


def test_parse_vtt_strips_headers_timestamps_and_rolling_duplicates():
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
so the question is

00:00:02.000 --> 00:00:04.000
so the question is
about anger

00:00:04.000 --> 00:00:06.000
about anger
and what to do
"""
    assert fetch_talk.parse_vtt(vtt) == "so the question is about anger and what to do"


def test_parse_vtt_drops_inline_styling_tags():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
<c>hello</c> <00:00:01.000>there</c>
"""
    assert fetch_talk.parse_vtt(vtt) == "hello there"


def test_render_transcript_markdown_has_metadata_and_text():
    md = fetch_talk.render_transcript_markdown(
        text="Hello there.",
        title="On Anger",
        teacher="Ajahn Brahm",
        source_url="https://youtu.be/abc",
        origin="youtube captions",
    )
    assert "# On Anger" in md
    assert "- Teacher: Ajahn Brahm" in md
    assert "- Source: https://youtu.be/abc" in md
    assert "- Origin: youtube captions" in md
    assert "Hello there." in md


def test_index_entry_format():
    entry = fetch_talk.index_entry(
        slug="on-anger",
        title="On Anger",
        teacher="Ajahn Brahm",
        source_url="https://youtu.be/abc",
        themes="anger, forgiveness",
    )
    assert entry.startswith("## on-anger\n")
    assert "- **Themes:** anger, forgiveness" in entry
    assert "- **Path:** library/on-anger/" in entry


def test_update_index_appends_once(tmp_path):
    index = tmp_path / "INDEX.md"
    entry = fetch_talk.index_entry(
        slug="on-anger", title="On Anger", teacher="Ajahn Brahm",
        source_url="https://youtu.be/abc", themes="anger",
    )
    fetch_talk.update_index(index, slug="on-anger", entry=entry)
    fetch_talk.update_index(index, slug="on-anger", entry=entry)
    content = index.read_text()
    assert content.count("## on-anger") == 1
    assert content.startswith("# Library Index")
```

**Step 2: Run tests, verify they fail**

Run: `uv run --with pytest --with yt-dlp pytest tools/tests/test_fetch_talk.py -v`
Expected: import-time failure loading `fetch_talk.py` (file not found).

**Step 3: Implement `tools/fetch_talk.py`:**

```python
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
```

**Step 4: Run tests, verify they pass**

Run: `uv run --with pytest --with yt-dlp pytest tools/tests/test_fetch_talk.py -v`
Expected: all pass. Also re-run the full suite: `uv run --with pytest --with mlx-whisper --with yt-dlp pytest tools/tests/ -v`

**Step 5: Smoke-test against the real world (no commit of outputs — library/ is gitignored)**

Run: `uv run tools/fetch_talk.py 'https://www.dhammatalks.org/audio/morning/2026/260612-patience.html' --title 'Patience Smoke Test' --teacher 'Thanissaro Bhikkhu' --themes 'patience' --model mlx-community/whisper-tiny`
Expected: downloads mp3, transcribes with the tiny model (fast, quality irrelevant here), creates `library/patience-smoke-test/` with `audio.mp3`, `transcript.md`, `transcript.json`, and an INDEX.md entry. Then delete the smoke-test folder and its INDEX entry.

If the yt-dlp Python API fields differ from the plan (e.g. caption track shapes), fix the implementation, not the test expectations — the tests only cover pure functions.

**Step 6: Commit**

```bash
git add tools/fetch_talk.py tools/tests/test_fetch_talk.py
git commit -m "Add fetch_talk: URL to library/ with captions-first transcripts"
```

---

### Task 4: speak.py — local TTS for primers and custom reflections

**Files:**
- Create: `tools/speak.py`
- Test: `tools/tests/test_speak.py`

Two engines: `kokoro` (mlx-audio, default) and `say` (macOS builtin fallback, always works). Markdown in, spoken audio out. TTS engines choke on markdown syntax, so `prepare_text` strips it — that's the testable core.

**Step 1: Write failing tests** — `tools/tests/test_speak.py` (same importlib pattern):

```python
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


def test_say_command_builds_aiff_then_ffmpeg_conversion():
    cmds = speak.say_commands("hello world", Path("/tmp/out.mp3"))
    assert cmds[0][:2] == ["say", "-o"]
    assert cmds[0][2].endswith(".aiff")
    assert cmds[1][0] == "ffmpeg"
    assert cmds[1][-1] == "/tmp/out.mp3"
```

**Step 2: Run tests, verify they fail**

Run: `uv run --with pytest pytest tools/tests/test_speak.py -v`
Expected: FAIL (module not found).

**Step 3: Implement `tools/speak.py`:**

```python
#!/usr/bin/env python3
# /// script
# dependencies = ["mlx-audio"]
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
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = line.replace("**", "").replace("*", "").replace("`", "")
        line = re.sub(r"\s+", " ", line).strip()
        if line:
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
        prefix = str(Path(tmp) / "speech")
        generate_audio(
            text=text,
            model_path=KOKORO_MODEL,
            voice=voice,
            speed=speed,
            file_prefix=prefix,
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
```

**Step 4: Run tests, verify they pass**

Run: `uv run --with pytest pytest tools/tests/test_speak.py -v` — expected: 5 passed.

**Step 5: Smoke-test both engines for real**

```bash
uv run tools/speak.py --text "May you be free from the second arrow." -o /tmp/second-arrow-say.mp3 --engine say
uv run tools/speak.py --text "May you be free from the second arrow." -o /tmp/second-arrow-kokoro.mp3
```

Expected: both produce playable mp3s (verify with `afplay` or `ffprobe`). **The mlx-audio `generate_audio` signature in this plan is from memory — if it differs, read the installed package (`uv run --with mlx-audio python -c "from mlx_audio.tts.generate import generate_audio; help(generate_audio)"`) and adapt `speak_with_kokoro` (and its output-file discovery) to reality.** First Kokoro run downloads the model (~350MB); that's expected. If mlx-audio is fundamentally unusable, keep the `say` engine as default and note it in CLAUDE.md.

**Step 6: Commit**

```bash
git add tools/speak.py tools/tests/test_speak.py
git commit -m "Add speak: local TTS (Kokoro, say fallback) for primers"
```

---

### Task 5: Curriculum Cluster 1 — Anger & the Second Arrow

**Files:**
- Create: `curriculum/README.md`, `curriculum/01-anger-and-the-second-arrow.md` (committed)

**Step 1: Verify every link before writing it.** For each candidate, confirm it resolves (WebFetch, or `curl -sI <url> | head -3` expecting 200/302; for YouTube use `uv run --with yt-dlp python -c "import yt_dlp; print(yt_dlp.YoutubeDL({'quiet': True}).extract_info('<url>', download=False)['title'])"`). Search for real, currently-available items:

- The Sallatha Sutta (SN 36:6, "The Arrow") — suttacentral.net or dhammatalks.org/suttas translation.
- The already-ingested Patience talk: https://www.dhammatalks.org/audio/morning/2026/260612-patience.html
- 2–3 Thanissaro Bhikkhu short morning talks on anger/aversion from dhammatalks.org.
- 2–3 Ajahn Brahm talks on anger/forgiveness from the Buddhist Society of Western Australia YouTube channel (@BuddhistSocietyWA) — search yt-dlp/web for current URLs; do not invent video IDs.

**No invented links.** If a candidate can't be verified, leave it out — the curriculum grows over time.

**Step 2: Write `curriculum/README.md`:**

```markdown
# Curriculum

Curated clusters of real talks and texts — each entry says why it's here and
when to reach for it. Every link is verified before it's added; the guide
checks a URL resolves before appending. Clusters grow out of actual study,
not ahead of it.

Ingest any entry with:
    uv run tools/fetch_talk.py <url> --teacher "..." --themes "..."
```

**Step 3: Write `curriculum/01-anger-and-the-second-arrow.md`** with the verified entries, formatted:

```markdown
# Cluster 1: Anger & the Second Arrow

The root cluster: anger, aversion, patience, and the two-arrows teaching.

## The source teaching

- **The Arrow (Sallatha Sutta, SN 36:6)** — <verified url>
  The original two-arrows text. Short. Read it once early, return often.

## Talks

- **Patience — Thanissaro Bhikkhu (2026-06-12)** — https://www.dhammatalks.org/audio/morning/2026/260612-patience.html
  Already in the library. Patience as not wearing the burden all the time.
  Reach for it when practice feels like grim endurance.

- ... (verified entries, one per talk, each with a "reach for it when" line)
```

**Step 4: Commit**

```bash
git add curriculum/
git commit -m "Add curriculum cluster 1: anger and the second arrow (verified links)"
```

---

### Task 6: End-to-end proof — one real talk, full loop

This task validates the whole design. No new code — just use it.

**Step 1: Pick one Ajahn Brahm anger talk** from the cluster written in Task 5.

**Step 2: Ingest it:**

```bash
uv run tools/fetch_talk.py '<youtube-url>' --teacher 'Ajahn Brahm' --themes 'anger, forgiveness, second arrow'
```

Expected: `library/<slug>/` with `transcript.md` (captions path — BSWA videos usually have captions) and an INDEX.md entry. If captions are missing it downloads audio and transcribes (several minutes with large-v3-turbo — fine).

**Step 3: Read the transcript and write `library/<slug>/primer.md`** — 60–90 seconds spoken length (~150–220 words): who Ajahn Brahm is (one sentence), what this talk is about, 2–3 specific things to listen for, one connection to the Patience talk already studied. Grounded only in the actual transcript.

**Step 4: Speak the primer:**

```bash
uv run tools/speak.py --file library/<slug>/primer.md -o library/<slug>/primer.mp3
afplay library/<slug>/primer.mp3   # spot-check it sounds right
```

**Step 5: Create `library/<slug>/notes.md`** seeded with themes, 2–3 key stories/quotes (with rough timestamps if transcribed locally), and an empty "## My takeaways" section for after the user listens.

**Step 6: Update `STUDY.md`**: move this talk into a "Queued — primer ready" state under Candidate next steps.

**Step 7: Verify the repo is still clean**

Run: `git status --short` — no `library/`, `journal/`, or `STUDY.md` entries. Run full test suite: `uv run --with pytest --with mlx-whisper --with yt-dlp pytest tools/tests/ -v` — all pass.

**Step 8: Update `README.md`** — add a short "Study space" section near the top explaining the new center of gravity (guide sessions via Claude Code, tools, curriculum; app dormant), then commit:

```bash
git add README.md
git commit -m "Point README at the study space: guide, tools, curriculum"
```

**Done when:** the user can open a session, hear a spoken primer, listen to a real talk, and come back to discuss it with the transcript on the table.
