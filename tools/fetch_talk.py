#!/usr/bin/env python3
# /// script
# dependencies = ["yt-dlp"]
# ///
"""Fetch a dhamma talk into library/<slug>/ with a transcript.

- YouTube URLs: use captions when available (manual preferred over auto);
  otherwise download audio and transcribe locally via transcribe_talk.py.
- Direct audio URLs (.mp3/.m4a/...): download and transcribe.
- HTML pages (e.g. dhammatalks.org): find the audio link, then as above.
- Readings (sutta pages — dhammatalks.org/suttas/, suttacentral.net — or
  any page with no audio link): extract the main text and ingest it as a
  transcript-only entry. No audio, no transcript.json, one explicit page.

Run with:
    uv run tools/fetch_talk.py <url> --teacher "Ajahn Brahm" --themes "anger, patience"
"""

import argparse
import html as html_module
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".opus")
LIBRARY = Path("library")


def slugify(value: str) -> str:
    # Intentionally differs from transcribe_talk.slugify: no Path(value).stem,
    # so titles containing dots keep their full text.
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "talk"


def guess_title_from_filename(filename: str) -> str:
    """Derive a talk title from an audio filename (mirrors transcribe_talk.guess_title)."""
    stem = Path(filename).stem
    title = re.sub(r"^\d{6}(?:\([^)]*\))?[_ -]*", "", stem)
    title = title.replace("_", " ").replace("-", " ").strip().title()
    return title or stem


def youtube_video_id(url: str) -> str | None:
    """The bare video id from watch?v=/youtu.be forms (params in any
    order); None otherwise. This is a talk's canonical identity."""
    match = re.match(
        r"https?://(?:www\.|m\.)?youtube\.com/watch\?(?:[^#\s]*&)?v=([\w-]{6,})", url or ""
    ) or re.match(r"https?://youtu\.be/([\w-]{6,})", url or "")
    return match.group(1) if match else None


def same_source(a: str, b: str) -> bool:
    """One talk, two URL spellings: bare YouTube ids match; else exact."""
    id_a, id_b = youtube_video_id(a), youtube_video_id(b)
    if id_a and id_b:
        return id_a == id_b
    return a == b


def find_existing_slug(index_text: str, url: str) -> str | None:
    """The slug of an INDEX entry whose Source is the same talk, or None.

    The check that stops the same video being ingested twice under two
    titles (it happened): identity is the source URL, not the title.
    """
    for block in re.split(r"\n(?=## )", index_text or ""):
        heading = re.match(r"## (\S+)", block)
        source = re.search(r"- \*\*Source:\*\* (.+)", block)
        if heading and source and same_source(source.group(1).strip(), url):
            return heading.group(1)
    return None


def clean_youtube_title(title: str) -> str:
    """A short human name from a raw YouTube title.

    "| Teacher"/"| date" pipe-tails and trailing dates drop away — teacher
    and date are their own INDEX fields, never part of the title. (Cousin
    of build_shelf.normalize_title, which makes lowercase MATCH keys;
    this one keeps a display title.)
    """
    base = (title or "").split("|")[0].strip()
    for tail in (
        r"[\s\-–—:,(]*\b\d{1,2} \w+ \d{4}\b[\s)]*$",  # (27 January 2023)
        r"[\s\-–—:,(]*\b\w+ \d{1,2},? \d{4}\b[\s)]*$",  # January 27, 2023
        r"[\s\-–—:,(]*\b\d{4}-\d{2}-\d{2}\b[\s)]*$",  # 2023-01-27
    ):
        base = re.sub(tail, "", base).strip(" -–—:,")
    return base or (title or "").strip() or "talk"


MIN_TRANSCRIPT_CHARS = 500  # anything smaller is a failed ingest


def page_title(html: str) -> str | None:
    """The <title> of a fetched page, or None — the probe's handle."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    if not match:
        return None
    title = " ".join(match.group(1).split())
    return title or None


def _match_key(name: str) -> str:
    """normalize_title's twin (kept local — this tool stays standalone)."""
    name = re.sub(r"\([^)]*\)", " ", name or "")
    name = name.split("|")[0]
    name = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    return " ".join(name.split())


def titles_match(expected: str, found: str) -> bool:
    """Fuzzy but not gullible: normalized equality or containment."""
    a, b = _match_key(expected), _match_key(found)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def transcript_chars(talk_dir: Path) -> int:
    """Body size of transcript.md (after the Full Transcript heading)."""
    path = talk_dir / "transcript.md"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    _, _, body = text.partition("## Full Transcript")
    return len((body or text).strip())


def ensure_valid_transcript(talk_dir: Path, fresh: bool) -> None:
    """A trivial transcript means the ingest failed — never shelve junk.

    Fresh ingests are removed wholesale (the INDEX entry is only written
    after this passes, so nothing dangles); refreshes of existing talks
    report loudly but never delete what was already there.
    """
    size = transcript_chars(talk_dir)
    if size >= MIN_TRANSCRIPT_CHARS:
        return
    if fresh:
        shutil.rmtree(talk_dir, ignore_errors=True)
        raise SystemExit(
            f"ingest failed: transcript too small ({size} chars < "
            f"{MIN_TRANSCRIPT_CHARS}) — partial talk removed, nothing indexed"
        )
    raise SystemExit(
        f"refresh failed: new transcript too small ({size} chars) — "
        "the existing talk folder was left as it was"
    )


def format_duration(seconds) -> str:
    """65 -> "1:05", 3725 -> "1:02:05"; unknown/zero -> ""."""
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def pick_thumbnail_url(info: dict) -> str | None:
    """A good medium thumbnail URL from yt-dlp info, or None.

    hq/mq variants keep the page light; the declared best is the
    fallback. Thumbnails are downloaded locally at ingest so the shelf
    never pings YouTube just to show a picture.
    """
    thumbnails = [t for t in info.get("thumbnails") or [] if t.get("url")]
    for wanted in ("hqdefault", "mqdefault", "sddefault"):
        for thumb in thumbnails:
            if wanted in str(thumb["url"]):
                return thumb["url"]
    if info.get("thumbnail"):
        return info["thumbnail"]
    return thumbnails[-1]["url"] if thumbnails else None


# URLs that are readings, not recordings (build_shelf keeps a twin — this
# tool stays standalone): sutta pages ingest as text, never an audio hunt.
READING_URL_RE = re.compile(r"dhammatalks\.org/suttas/|suttacentral\.net")


def classify_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if parsed.path.lower().endswith(AUDIO_EXTENSIONS):
        return "audio"
    if READING_URL_RE.search(url):
        return "reading"
    return "page"


def find_audio_link(html: str, base_url: str) -> str | None:
    for match in re.finditer(r'href="([^"]+)"', html):
        # Hrefs arrive HTML-escaped (&amp;) and may carry spaces/parens —
        # unescape, then percent-encode what urllib can't fetch raw.
        # `%` stays safe so already-encoded links aren't double-encoded.
        href = html_module.unescape(match.group(1))
        if href.lower().split("?")[0].endswith(AUDIO_EXTENSIONS):
            href = urllib.parse.quote(href, safe="%/:?=&()!$,;'@+*~._-")
            return urllib.parse.urljoin(base_url, href)
    return None


# --- readings: text pages ingested as transcript-only entries ------------------

READING_WPM = 200  # a calm reading pace, behind the "~N min read" duration

READING_ORIGIN = (
    "reading — text extracted from the source page (no audio; "
    "the page is the authority)"
)


def reading_minutes(words: int) -> int:
    """An approximate read time in minutes — never zero."""
    return max(1, round(words / READING_WPM))


def fetch_page(url: str) -> str:
    """One GET, decoded tolerantly — the single network door for pages
    (and the one seam tests mock)."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "second-arrow-study/1.0"}
    )
    with urllib.request.urlopen(request) as resp:
        return resp.read().decode("utf-8", errors="replace")


_BOILERPLATE_RE = re.compile(
    r"<(script|style|nav|header|footer|aside|head)\b.*?</\1\s*>", re.I | re.S
)

# The known reading shapes, most specific first: dhammatalks.org suttas
# live in <div id="sutta">…</div><!--end:sutta-->; then any <main> or
# <article>. No match falls back to the whole body minus boilerplate —
# the largest block of text a simple reader can find.
_MAIN_BLOCK_PATTERNS = (
    r'<div[^>]*\bid="sutta"[^>]*>(.*?)</div>\s*<!--\s*end:sutta\s*-->',
    r"<main\b[^>]*>(.*?)</main\s*>",
    r"<article\b[^>]*>(.*?)</article\s*>",
)


def html_to_text(fragment: str) -> str:
    """Block-aware tag stripping: paragraph breaks survive as blank lines."""
    text = re.sub(r"(?i)<(?:/p|/h[1-6]|/li|/blockquote|/div|br\s*/?)\s*>", "\n\n", fragment)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        line = " ".join(line.split())
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def clean_page_title(title: str) -> str:
    """'SN 36:6 The Arrow | Sallattha Sutta | sutta on dhammatalks.org'
    -> 'SN 36:6 The Arrow' — site tails drop away, the name stays."""
    return (title or "").split("|")[0].strip() or (title or "").strip()


def extract_reading(html: str, url: str) -> dict:
    """{"title", "text"} from a reading page's HTML.

    Honest, dependency-light extraction: boilerplate (scripts, styles,
    nav, header, footer) is dropped, then the known site shapes are tried
    (_MAIN_BLOCK_PATTERNS) with the body as the generic fallback. The
    original page stays the authority — the transcript header downstream
    says plainly that this is an extraction.
    """
    stripped = _BOILERPLATE_RE.sub(" ", html or "")
    fragment = None
    for pattern in _MAIN_BLOCK_PATTERNS:
        match = re.search(pattern, stripped, re.I | re.S)
        if match:
            fragment = match.group(1)
            break
    if fragment is None:
        body = re.search(r"<body\b[^>]*>(.*)</body\s*>", stripped, re.I | re.S)
        fragment = body.group(1) if body else stripped
    title = clean_page_title(page_title(html) or "") or guess_title_from_filename(
        Path(urllib.parse.urlparse(url).path).name
    )
    return {"title": title, "text": html_to_text(fragment)}


_SUTTACENTRAL_URL_RE = re.compile(
    r"https?://(?:www\.)?suttacentral\.net/([\w.\-]+)/([a-z]{2,3})/([\w.\-]+)"
)


def fetch_suttacentral_reading(url: str) -> dict:
    """suttacentral.net is a JS app — its pages carry no text. The public
    bilara API does: /api/bilarasuttas/<uid>/<author>?lang=<lang> answers
    a segment map plus keys_order. Segments group into paragraphs by
    their section number; the section-0 headings feed the title.
    Needs the full URL shape /<uid>/<lang>/<translator>."""
    match = _SUTTACENTRAL_URL_RE.match(url)
    if not match:
        raise SystemExit(
            "suttacentral.net needs the full sutta URL — "
            f"https://suttacentral.net/<uid>/<lang>/<translator> (got {url})"
        )
    uid, lang, author = match.groups()
    api = f"https://suttacentral.net/api/bilarasuttas/{uid}/{author}?lang={lang}"
    data = json.loads(fetch_page(api))
    segments = data.get("translation_text") or {}
    order = data.get("keys_order") or sorted(segments)
    title = ""
    paragraphs: list[str] = []
    last_section = None
    for key in order:
        piece = (segments.get(key) or "").strip()
        if not piece:
            continue
        section = key.split(":")[-1].split(".")[0]
        if section == "0":
            title = piece  # the last heading line wins (the sutta's name)
            continue
        if section != last_section:
            paragraphs.append(piece)
            last_section = section
        else:
            paragraphs[-1] += " " + piece
    return {"title": title or uid, "text": "\n\n".join(paragraphs)}


def fetch_reading(url: str) -> dict:
    """One reading, fetched and extracted — the site-shape dispatch."""
    if "suttacentral.net" in urllib.parse.urlparse(url).netloc.lower():
        return fetch_suttacentral_reading(url)
    return extract_reading(fetch_page(url), url)


def ingest_reading(
    *, library: Path, url: str, title: str, teacher: str, themes: str,
    text: str, existing: str | None,
) -> str:
    """Write one reading into library/<slug>/: transcript.md only (the
    honest extraction header), validated like any ingest, then the INDEX
    entry (Origin: reading, Duration: "~N min read"). Returns the slug."""
    slug = existing or slugify(title)
    talk_dir = library / slug
    talk_dir.mkdir(parents=True, exist_ok=True)
    (talk_dir / "transcript.md").write_text(
        render_transcript_markdown(
            text=text, title=title, teacher=teacher,
            source_url=url, origin=READING_ORIGIN,
        ),
        encoding="utf-8",
    )
    ensure_valid_transcript(talk_dir, fresh=existing is None)
    if existing:
        return slug
    update_index(
        library / "INDEX.md",
        slug=slug,
        entry=index_entry(
            slug=slug, title=title, teacher=teacher, source_url=url,
            themes=themes or "untagged",
            duration=f"~{reading_minutes(len(text.split()))} min read",
            origin="reading", ingested=date.today().isoformat(),
        ),
    )
    return slug


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


_VTT_TIMING = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})\.(\d{3})\s+-->\s+(?:(\d+):)?(\d{1,2}):(\d{2})\.(\d{3})"
)


def _vtt_seconds(hours, minutes, seconds, millis) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_vtt_segments(vtt: str) -> list[dict]:
    """parse_vtt with the timing kept: [{"start", "end", "text"}, ...].

    Same rolling-caption dedupe, line by line: a repeated line extends the
    earlier segment instead of duplicating it, a grown line replaces it.
    Invariant (tested): joining the segment texts reproduces parse_vtt's
    plain transcript exactly.
    """
    segments: list[dict] = []
    start = end = 0.0
    for raw in vtt.splitlines():
        line = raw.strip()
        timing = _VTT_TIMING.match(line)
        if timing:
            groups = timing.groups()
            start, end = _vtt_seconds(*groups[:4]), _vtt_seconds(*groups[4:])
            continue
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
        if segments and line == segments[-1]["text"]:
            segments[-1]["end"] = max(segments[-1]["end"], end)
            continue
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": line})
    deduped: list[dict] = []
    for seg in segments:
        if deduped and deduped[-1]["text"].endswith(seg["text"]):
            deduped[-1]["end"] = max(deduped[-1]["end"], seg["end"])
            continue
        if deduped and seg["text"].startswith(deduped[-1]["text"]):
            deduped[-1]["text"] = seg["text"]
            deduped[-1]["end"] = max(deduped[-1]["end"], seg["end"])
            continue
        deduped.append(seg)
    return deduped


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


def index_entry(
    *,
    slug: str,
    title: str,
    teacher: str,
    source_url: str,
    themes: str,
    date: str = "",
    duration: str = "",
    origin: str = "",
    ingested: str = "",
) -> str:
    """One INDEX entry, every field every time (blank beats missing).

    Title is the short human name (no teacher, no date — those are their
    own fields); Source is the talk's canonical identity; Origin says how
    the transcript was made (youtube captions | whisper | captions+whisper).
    """
    return "\n".join(
        [
            f"## {slug}",
            f"- **Title:** {title}",
            f"- **Teacher:** {teacher}",
            f"- **Source:** {source_url}",
            f"- **Date:** {date}",
            f"- **Duration:** {duration}",
            f"- **Origin:** {origin}",
            f"- **Ingested:** {ingested}",
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


YDL_COMMON = {"quiet": True, "no_warnings": True, "noplaylist": True}


def probe_youtube(url: str) -> dict:
    """Video metadata without downloading anything: title, uploader,
    thumbnail URL, duration (formatted), upload date (ISO)."""
    import yt_dlp

    with yt_dlp.YoutubeDL(dict(YDL_COMMON)) as ydl:
        info = ydl.extract_info(url, download=False)
    upload = str(info.get("upload_date") or "")
    return {
        "title": info.get("title") or "talk",
        "uploader": info.get("uploader") or "",
        "thumbnail_url": pick_thumbnail_url(info),
        "duration": format_duration(info.get("duration")),
        "date": f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else "",
    }


def fetch_youtube_captions(url: str, talk_dir: Path) -> dict | None:
    """Download English captions (manual preferred over auto) into talk_dir.

    YouTube's timedtext URLs reject plain urllib clients, so the subtitle
    download goes through yt-dlp itself. Returns {"text", "segments"}
    (segments carry start/end timing for the transcript player), or None
    when no usable captions exist.
    """
    import yt_dlp

    # Genuine English tracks only — "en.*" would also match auto-translated
    # tracks (en-de, en-ja, ...) whose downloads can 429 and abort the run.
    languages = ["en", "en-en", "en-orig"]
    opts = {
        **YDL_COMMON,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": languages,
        "subtitlesformat": "vtt",
        "outtmpl": str(talk_dir / "captions"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError:
        pass  # a partial failure may still have written usable .vtt files
    vtt_files = sorted(talk_dir.glob("captions*.vtt"))
    if not vtt_files:
        return None
    by_name = {f.name: f for f in vtt_files}
    chosen = next(
        (by_name[f"captions.{lang}.vtt"] for lang in languages if f"captions.{lang}.vtt" in by_name),
        vtt_files[0],
    )
    vtt = chosen.read_text(encoding="utf-8", errors="replace")
    text = parse_vtt(vtt)
    segments = parse_vtt_segments(vtt)
    for vtt_file in vtt_files:
        vtt_file.unlink()
    if not text:
        return None
    return {"text": text, "segments": segments}


def download_youtube_audio(url: str, talk_dir: Path) -> Path:
    import yt_dlp

    opts = {
        **YDL_COMMON,
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(talk_dir / "audio.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    audio_path = next(iter(sorted(talk_dir.glob("audio.*"))), None)
    if audio_path is None:
        raise SystemExit(f"YouTube audio download produced no file in {talk_dir}")
    return audio_path


def download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "second-arrow-study/1.0"})
    with urllib.request.urlopen(request) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
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
    # Rename whatever the subprocess actually wrote — transcribe_talk slugifies
    # the title its own way, so recomputing the slug here can silently miss.
    for pattern in ("*.json", "*.md"):
        for produced in sorted(talk_dir.glob(pattern)):
            if produced.name.startswith("transcript."):
                continue
            produced.rename(talk_dir / f"transcript{produced.suffix}")
    if not (talk_dir / "transcript.md").exists():
        raise SystemExit(f"Transcription produced no transcript.md in {talk_dir}")


def _reading_probe(reading: dict, url: str) -> dict:
    """The probe shape for a reading: kind, title, ~word count, the text
    itself (carried so the ingest never fetches twice)."""
    words = len(reading["text"].split())
    return {
        "kind": "reading",
        "title": reading["title"],
        "teacher": "",
        "duration": f"~{reading_minutes(words)} min read",
        "final_url": url,
        "text": reading["text"],
        "words": words,
    }


def probe_source(url: str) -> dict:
    """Look before downloading: {kind, title, teacher, duration, final_url}.

    YouTube probes via extract_info(download=False); pages are fetched
    once for their <title> and audio link (the link is the final URL);
    bare audio URLs read their filename. A reading URL — or any page
    with no audio to offer — probes as a reading: title, ~word count,
    and the extracted text itself. Nothing is created at this point.
    """
    kind = classify_url(url)
    if kind == "youtube":
        meta = probe_youtube(url)
        return {
            "kind": "youtube",
            "title": meta["title"],
            "teacher": meta["uploader"],
            "duration": meta["duration"],
            "final_url": url,
        }
    if kind == "reading":
        return _reading_probe(fetch_reading(url), url)
    if kind == "page":
        html = fetch_page(url)
        audio_url = find_audio_link(html, url)
        if not audio_url:
            # A page with no recording IS a reading — the text itself.
            return _reading_probe(extract_reading(html, url), url)
        return {
            "kind": "page",
            "title": page_title(html) or guess_title_from_filename(
                Path(urllib.parse.urlparse(audio_url).path).name
            ),
            "teacher": "",
            "duration": "",
            "final_url": audio_url,
        }
    filename = Path(urllib.parse.urlparse(url).path).name
    return {
        "kind": "audio",
        "title": guess_title_from_filename(filename),
        "teacher": "",
        "duration": "",
        "final_url": url,
    }


def parse_index_entries(index_text: str) -> list[dict]:
    """{"slug", lowercase field -> value} per INDEX entry (the same shape
    build_shelf.parse_index yields; duplicated to keep this tool standalone)."""
    entries = []
    for block in re.split(r"\n(?=## )", index_text or ""):
        heading = re.match(r"## (\S+)", block)
        if not heading:
            continue
        entry = {"slug": heading.group(1)}
        for key, value in re.findall(r"- \*\*(\w+):\*\* (.+)", block):
            entry[key.lower()] = value.strip()
        entries.append(entry)
    return entries


def download_thumbnail(url: str, talk_dir: Path) -> bool:
    """Best-effort local thumbnail (privacy: the shelf never asks YouTube
    for pictures at view time). Returns whether one now exists."""
    dest = talk_dir / "thumbnail.jpg"
    if dest.exists():
        return True
    try:
        info = probe_youtube(url)
        if not info["thumbnail_url"]:
            return False
        download_file(info["thumbnail_url"], dest)
        return True
    except Exception as error:  # noqa: BLE001 — thumbnails are a nicety
        print(f"  thumbnail fetch failed (non-fatal): {error}")
        return False


def backfill_thumbnails(library: Path) -> None:
    """Fetch thumbnail.jpg for YouTube-sourced INDEX entries missing one."""
    index_path = library / "INDEX.md"
    if not index_path.exists():
        raise SystemExit(f"No {index_path} found — nothing to backfill.")
    for entry in parse_index_entries(index_path.read_text(encoding="utf-8")):
        source = entry.get("source", "")
        if not youtube_video_id(source):
            continue
        talk_dir = library / entry["slug"]
        if (talk_dir / "thumbnail.jpg").exists():
            print(f"{entry['slug']}: thumbnail already present")
            continue
        talk_dir.mkdir(parents=True, exist_ok=True)
        ok = download_thumbnail(source, talk_dir)
        print(f"{entry['slug']}: {'thumbnail.jpg written' if ok else 'no thumbnail'}")


def backfill_transcripts(library: Path) -> None:
    """Re-fetch captions for YouTube-sourced entries missing transcript.json.

    Regenerates transcript.md and transcript.json together (metadata
    headers kept, from the INDEX entry) so the two never drift apart.
    """
    index_path = library / "INDEX.md"
    if not index_path.exists():
        raise SystemExit(f"No {index_path} found — nothing to backfill.")
    for entry in parse_index_entries(index_path.read_text(encoding="utf-8")):
        source = entry.get("source", "")
        if not youtube_video_id(source):
            continue
        talk_dir = library / entry["slug"]
        if (talk_dir / "transcript.json").exists():
            print(f"{entry['slug']}: transcript.json already present")
            continue
        talk_dir.mkdir(parents=True, exist_ok=True)
        captions = fetch_youtube_captions(source, talk_dir)
        if not captions:
            print(f"{entry['slug']}: no captions available — skipped")
            continue
        write_transcript(
            talk_dir,
            captions,
            title=entry.get("title", entry["slug"]),
            teacher=entry.get("teacher", ""),
            source_url=source,
        )
        print(f"{entry['slug']}: transcript.md + transcript.json regenerated")


def write_transcript(talk_dir: Path, captions: dict, *, title: str, teacher: str, source_url: str) -> None:
    """transcript.md (metadata headers + text) and transcript.json together."""
    (talk_dir / "transcript.md").write_text(
        render_transcript_markdown(
            text=captions["text"], title=title, teacher=teacher,
            source_url=source_url, origin="youtube captions",
        ),
        encoding="utf-8",
    )
    if captions.get("segments"):
        (talk_dir / "transcript.json").write_text(
            json.dumps({"segments": captions["segments"]}, ensure_ascii=False),
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "url", nargs="?",
        help="Source URL: YouTube, direct audio, a page containing an audio "
             "link, or a reading (sutta/text page — ingested as text)",
    )
    parser.add_argument("--title", help="Talk title (defaults to cleaned metadata or URL filename)")
    parser.add_argument("--teacher", default="", help="Teacher name (defaults to YouTube uploader if known)")
    parser.add_argument("--themes", default="", help="Comma-separated themes for the library index")
    parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="MLX Whisper model used when local transcription is needed",
    )
    parser.add_argument("--library", type=Path, default=LIBRARY, help="Library root directory")
    parser.add_argument(
        "--expect-title", default=None,
        help="abort (before any download) unless the probed title fuzzily "
             "matches this — use the curriculum's title",
    )
    parser.add_argument(
        "--probe-only", action="store_true",
        help="probe the source (title/teacher/duration/final URL) and exit "
             "without downloading anything",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="when the talk is already in the library, refresh its captions/"
             "transcript.json/thumbnail in place instead of skipping",
    )
    parser.add_argument(
        "--backfill-thumbnails", action="store_true",
        help="no URL: fetch thumbnail.jpg for YouTube talks missing one",
    )
    parser.add_argument(
        "--backfill-transcripts", action="store_true",
        help="no URL: re-fetch captions for YouTube talks missing transcript.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.backfill_thumbnails or args.backfill_transcripts:
        if args.backfill_thumbnails:
            backfill_thumbnails(args.library)
        if args.backfill_transcripts:
            backfill_transcripts(args.library)
        return
    if not args.url:
        raise SystemExit("Give a talk URL (or a --backfill-* mode).")
    kind = classify_url(args.url)

    # Canonical identity is the source URL: the same video under any
    # spelling never becomes a second folder with a second title.
    index_path = args.library / "INDEX.md"
    existing = (
        find_existing_slug(index_path.read_text(encoding="utf-8"), args.url)
        if index_path.exists()
        else None
    )
    if existing and not args.refresh and not args.probe_only:
        print(f"already in library as {existing} — nothing to do "
              "(use --refresh to update captions/thumbnail in place)")
        return

    # Look first. Nothing is created until the probe (and any expected
    # title) checks out — a wrong link aborts empty-handed.
    probe = probe_source(args.url)
    print(f"probe: {probe['title']!r}"
          + (" — reading" if probe["kind"] == "reading" else "")
          + (f" — {probe['teacher']}" if probe['teacher'] else "")
          + (f" — ~{probe['words']} words" if probe.get("words") else "")
          + (f" — {probe['duration']}" if probe['duration'] else "")
          + f" — {probe['final_url']}")
    if args.expect_title and not titles_match(args.expect_title, probe["title"]):
        raise SystemExit(
            f"title mismatch: expected {args.expect_title!r}, found "
            f"{probe['title']!r} — nothing created"
        )
    if args.probe_only:
        return

    if probe["kind"] == "reading":
        # A text source: transcript.md only (the extraction, honestly
        # labeled), no audio, no transcript.json. Explicit and single-item
        # like every ingest — no links are ever followed from the page.
        slug = ingest_reading(
            library=args.library,
            url=args.url,
            title=args.title or probe["title"],
            teacher=args.teacher or "Unknown",
            themes=args.themes,
            text=probe["text"],
            existing=existing,
        )
        print(
            f"Refreshed library/{existing}/ in place"
            if existing
            else f"Ingested into library/{slug}/ (reading)"
        )
        return
    if kind == "youtube":
        meta = probe_youtube(args.url)
        title = args.title or clean_youtube_title(meta["title"])
        teacher = args.teacher or meta["uploader"] or "Unknown"
        slug = existing or slugify(title)
        talk_dir = args.library / slug
        talk_dir.mkdir(parents=True, exist_ok=True)
        captions = fetch_youtube_captions(args.url, talk_dir)
        origin = "youtube captions"
        if captions:
            write_transcript(talk_dir, captions, title=title, teacher=teacher,
                             source_url=args.url)
        else:
            origin = "whisper"
            audio_path = download_youtube_audio(args.url, talk_dir)
            transcribe(audio_path, talk_dir=talk_dir, title=title, teacher=teacher,
                       source_url=args.url, model=args.model)
        ensure_valid_transcript(talk_dir, fresh=existing is None)
        download_thumbnail(args.url, talk_dir)
        if existing:
            print(f"Refreshed library/{existing}/ in place")
            return
        update_index(
            index_path,
            slug=slug,
            entry=index_entry(
                slug=slug, title=title, teacher=teacher, source_url=args.url,
                themes=args.themes or "untagged", date=meta["date"],
                duration=meta["duration"], origin=origin,
                ingested=date.today().isoformat(),
            ),
        )
        print(f"Ingested into library/{slug}/")
        return
    else:  # noqa: RET505 — kept symmetric with the youtube branch above
        audio_url = probe["final_url"]
        filename = Path(urllib.parse.urlparse(audio_url).path).name
        title = args.title or guess_title_from_filename(filename)
        teacher = args.teacher or "Unknown"
        slug = existing or slugify(title)
        talk_dir = args.library / slug
        audio_path = download_file(audio_url, talk_dir / f"audio{Path(filename).suffix or '.mp3'}")
        transcribe(audio_path, talk_dir=talk_dir, title=title, teacher=teacher,
                   source_url=args.url, model=args.model)
        ensure_valid_transcript(talk_dir, fresh=existing is None)
        if existing:
            print(f"Refreshed library/{existing}/ in place")
            return

    update_index(
        index_path,
        slug=slug,
        entry=index_entry(
            slug=slug, title=title, teacher=teacher, source_url=args.url,
            themes=args.themes or "untagged", origin="whisper",
            ingested=date.today().isoformat(),
        ),
    )
    print(f"Ingested into library/{slug}/")


if __name__ == "__main__":
    main()
