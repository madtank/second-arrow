#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""Render a calm, self-contained HTML study shelf over library/.

Reads library/INDEX.md, probes each talk folder for primers, notes, audio,
and transcript, matches "Reach for it when ..." lines from curriculum/*.md
by Source URL, and writes library/shelf.html (private, gitignored). Paths
in the page are relative so audio plays over file://.

The page is two panes: a sidebar (title, the path, one nav entry per talk,
a Sessions list fed from /api/sessions in served mode) and a main pane
showing one view at a time — #home or #talk/<slug> — routed by a tiny
hashchange handler. With JS off the views simply render stacked (hiding
happens only under a runtime "js" class). YouTube-sourced talks get a
click-to-load embedded player: nothing third-party loads until the user
presses "Play here". The guide chat panel sits below the active view and
stays put across views; each POST carries the open talk's slug ("view")
as ambient context and the session id it continues.

Run with:
    uv run tools/build_shelf.py
Then:
    open library/shelf.html
"""

import argparse
import json
import re
from pathlib import Path

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".aac", ".opus")


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def youtube_embed_url(source_url: str) -> str | None:
    """Privacy-enhanced embed URL for a YouTube video link, else None.

    Handles watch?v=<id> (with extra params in any order) and youtu.be/<id>
    forms. Channel/playlist/anything-else URLs get None — only a single
    video can be embedded.
    """
    url = source_url or ""
    match = re.match(
        r"https?://(?:www\.|m\.)?youtube\.com/watch\?(?:[^#\s]*&)?v=([\w-]{6,})", url
    ) or re.match(r"https?://youtu\.be/([\w-]{6,})", url)
    if not match:
        return None
    return f"https://www.youtube-nocookie.com/embed/{match.group(1)}"


def duration_to_seconds(text) -> int | None:
    """"56:04" -> 3364, "1:03:52" -> 3832; unknown/garbled -> None.

    The INDEX Duration field becomes a per-talk cap for the guide's seek
    cues — a cue past the end is silently invalid.
    """
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", (text or "").strip())
    if not match:
        return None
    hours, minutes, seconds = (
        int(match.group(1) or 0), int(match.group(2)), int(match.group(3))
    )
    return hours * 3600 + minutes * 60 + seconds


def format_time(seconds) -> str:
    """65 -> "1:05", 3725 -> "1:02:05" — segment stamps and durations."""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def load_listening(library: Path) -> dict[str, dict]:
    """slug -> {"count", "last"} from library/.listening.jsonl (tolerant).

    The server writes it (POST /api/listened); the shelf renders it as a
    quiet "listened ✓" line. The log is append-only: "mark unheard"
    appends {slug, at, retract: true} and the LATEST entry wins — a talk
    whose newest entry is a retraction reads as not-heard (dropped from
    the summary), and a listen after that counts again. Corrupt lines
    and a missing file read as silence, never an error.
    """
    path = library / ".listening.jsonl"
    if not path.exists():
        return {}
    per_slug: dict[str, list] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        slug, at = record.get("slug"), record.get("at")
        if not isinstance(slug, str) or not isinstance(at, str):
            continue
        per_slug.setdefault(slug, []).append((at, record.get("retract") is True))
    summary: dict[str, dict] = {}
    for slug, entries in per_slug.items():
        if max(entries)[1]:
            continue  # the latest word on this talk is a retraction
        listens = [at for at, retracted in entries if not retracted]
        if listens:
            summary[slug] = {"count": len(listens), "last": max(listens)}
    return summary


def normalize_segments(data) -> list[dict]:
    """[{"start", "end", "text"}] from a transcript.json of either shape.

    Whisper's segments carry extra keys (id/seek/tokens/...); the captions
    parser writes bare start/end/text. Both normalize to the same three
    fields; junk entries drop out; anything unusable gives [].
    """
    if not isinstance(data, dict):
        return []
    segments: list[dict] = []
    for seg in data.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        text = seg.get("text")
        start = seg.get("start")
        if not isinstance(text, str) or not text.strip():
            continue
        if not isinstance(start, (int, float)) or isinstance(start, bool):
            continue
        end = seg.get("end")
        if not isinstance(end, (int, float)) or isinstance(end, bool):
            end = start
        segments.append(
            {"start": float(start), "end": float(end), "text": text.strip()}
        )
    return segments


def parse_moments(text: str, cap: float | None = None) -> list[dict]:
    """The guide's curated jump-to moments out of a talk's notes.md.

    A "## Moments" section holds machine-parseable lines —
    `- 13:23 — how he lands the eggs story` (mm:ss or h:mm:ss; en dash
    or a spaced hyphen tolerated) — and becomes the card's "Listen for"
    chips. Tolerant by design: junk lines, other sections, and a missing
    section all read as no moments. `cap` (seconds — the transcript.json
    range) silently drops any moment past the end of the talk.

    Returns [{"start": seconds, "label": text}] in file order.
    """
    moments: list[dict] = []
    in_section = False
    for line in (text or "").splitlines():
        heading = re.match(r"#{1,6} (.+)", line)
        if heading:
            in_section = heading.group(1).strip().lower() == "moments"
            continue
        if not in_section or not line.startswith("- "):
            continue
        match = re.match(r"- ([\d:]+)\s*(?:—|–| - )\s*(\S.*)", line)
        if not match:
            continue
        start = duration_to_seconds(match.group(1))
        if start is None:
            continue
        if cap and start > cap:
            continue  # past the end of the talk — never render a dead seek
        moments.append({"start": start, "label": match.group(2).strip()})
    return moments


def parse_index(text: str) -> list[dict]:
    """Parse library/INDEX.md into one dict per `## <slug>` entry."""
    talks = []
    for block in re.split(r"\n(?=## )", text):
        heading = re.match(r"## (\S+)", block)
        if not heading:
            continue
        talk = {"slug": heading.group(1)}
        for key, value in re.findall(r"- \*\*(\w+):\*\* (.+)", block):
            talk[key.lower()] = value.strip()
        talks.append(talk)
    return talks


def reach_lines(text: str) -> dict[str, str]:
    """Map each curriculum entry's URL to its 'Reach for it when ...' sentence."""
    reach = {}
    for entry in re.split(r"\n(?=- \*\*)", text):
        if not entry.startswith("- **"):
            continue
        url = re.search(r"https?://[^\s)]+", entry)
        if not url:
            continue
        joined = " ".join(line.strip() for line in entry.splitlines())
        sentence = re.search(r"Reach for it when .*?\.", joined)
        if sentence:
            reach[url.group(0)] = sentence.group(0)
    return reach


def md_to_html(text: str) -> str:
    """Markdown-lite for wherever humans read: #–### headings, dashed and
    numbered lists, > blockquotes, **bold**, paragraphs. Escapes HTML —
    markdown is the machine layer; this is its human rendering.
    """
    out: list[str] = []
    state = {"ul": False, "ol": False, "quote": False}
    closers = {"ul": "</ul>", "ol": "</ol>", "quote": "</blockquote>"}

    def close(*names: str) -> None:
        for name in names:
            if state[name]:
                out.append(closers[name])
                state[name] = False

    def inline(content: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(content))

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            close("ul", "ol", "quote")
            continue
        heading = re.match(r"(#{1,3}) (.+)", line)
        if heading:
            close("ul", "ol", "quote")
            level = len(heading.group(1)) + 2  # keep below the page h1/h2
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
        elif line.startswith("- "):
            close("ol", "quote")
            if not state["ul"]:
                out.append("<ul>")
                state["ul"] = True
            out.append(f"<li>{inline(line[2:])}</li>")
        elif re.match(r"\d+\. ", line):
            close("ul", "quote")
            if not state["ol"]:
                out.append("<ol>")
                state["ol"] = True
            out.append(f"<li>{inline(re.sub(r'^\d+\. ', '', line))}</li>")
        elif line == ">" or line.startswith("> "):
            close("ul", "ol")
            if not state["quote"]:
                out.append("<blockquote>")
                state["quote"] = True
            content = line[2:].strip()
            if content:
                out.append(f"<p>{inline(content)}</p>")
        else:
            close("ul", "ol", "quote")
            out.append(f"<p>{inline(line)}</p>")
    close("ul", "ol", "quote")
    return "\n".join(out)


def parse_study(text: str) -> dict:
    """Pull the path out of STUDY.md: studied / queued / parked name lists.

    Tolerant by design (STUDY.md is hand- and guide-edited): missing
    sections or plain prose give empty lists. Only top-level `- ` items
    inside `## Studied` / `## Queued` count; an item's name is its leading
    **bold** span, else the text before the first " — " or ": "
    separator. Wrapped continuation lines are ignored. A QUEUED item whose
    first-line note says "parked" is a state, not a section — it goes to
    "parked" (set aside, no obligation) instead of the queue.
    """
    path: dict = {"studied": [], "queued": [], "parked": []}
    section = None
    for line in text.splitlines():
        heading = re.match(r"#{2,} (.+)", line)
        if heading:
            name = heading.group(1).strip().lower()
            section = name if name in ("studied", "queued") else None
            continue
        if section is None or not line.startswith("- "):
            continue
        item = line[2:].strip()
        bold = re.match(r"\*\*(.+?)\*\*", item)
        name = bold.group(1) if bold else re.split(r" — |: ", item)[0]
        rest = item[bold.end():] if bold else item[len(name):]
        name = name.strip().rstrip(".")
        if not name:
            continue
        if section == "queued" and re.search(r"\bparked\b", rest, re.I):
            path["parked"].append(name)
        else:
            path[section].append(name)
    return path


def normalize_title(name: str) -> str:
    """One talk, two spellings, one key.

    STUDY.md writes "Anger Eating Demons (Ajahn Brahm)"; INDEX.md writes
    "Dealing with people that irritate us | Ajahn Brahm". Parentheticals
    and "| Teacher" tails drop away, punctuation flattens, case folds —
    so both sides meet in the middle.
    """
    name = re.sub(r"\([^)]*\)", " ", name or "")
    name = name.split("|")[0]
    name = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    return " ".join(name.split())


def talk_states(path: dict, talks: list[dict]) -> tuple[dict[str, str], list[str]]:
    """(slug -> "studied"|"queued", queued names not yet fetched).

    Matches parse_study names against library titles via normalize_title.
    Two states, matching the sidebar's marks: parked collapses into
    "studied" — done for the shelf's purposes; its "set aside" nuance
    stays in STUDY.md's own words. Library talks absent from STUDY.md
    simply get no state; queued names with no library match come back as
    `unfetched`, so the path ahead stays visible in the sidebar.
    """
    by_title = {
        normalize_title(talk.get("title", talk["slug"])): talk["slug"]
        for talk in talks
    }
    states: dict[str, str] = {}
    unfetched: list[str] = []
    for state in ("studied", "parked", "queued"):
        for name in path.get(state, []):
            slug = by_title.get(normalize_title(name))
            if slug:
                states.setdefault(slug, "studied" if state == "parked" else state)
            elif state == "queued":
                unfetched.append(name)
    return states, unfetched


# URLs that are readings, not recordings — a sutta page can't be fetched
# as a talk, so its stub room asks the guide instead of offering a fetch.
# A "for now" heuristic, matching the curriculum's current shape.
_READING_URL_RE = re.compile(r"dhammatalks\.org/suttas/|suttacentral\.net")


def curriculum_entries(curriculum: Path) -> list[dict]:
    """Everything the curriculum knows per entry, for the stub rooms.

    [{title, teacher, url, why, fetchable}] from curriculum/*.md
    (README skipped). An entry is its `- **Title — Teacher (meta)**`
    line plus the contiguous description lines under it; the first URL
    is its source. fetchable means a URL exists and looks like a
    recording (reading pages — suttas — stay ask-the-guide). Tolerant:
    junk entries simply contribute less.
    """
    entries: list[dict] = []
    files = sorted(curriculum.glob("*.md")) if curriculum.is_dir() else []
    for path in files:
        if path.name.lower() == "readme.md":
            continue
        for block in re.split(r"\n(?=- \*\*)", path.read_text(encoding="utf-8")):
            if not block.startswith("- **"):
                continue
            bold = re.match(r"- \*\*(.+?)\*\*", block)
            if not bold:
                continue
            head = bold.group(1)
            title, teacher = head, ""
            if " — " in head:
                title, teacher = head.split(" — ", 1)
                teacher = re.sub(r"\([^)]*\)", "", teacher).strip()
            first_line, _, rest = block.partition("\n")
            why_lines = []
            for line in rest.splitlines():
                if not line.strip():
                    break  # entries are blank-line separated
                why_lines.append(line.strip())
            url = re.search(r"https?://[^\s)]+", first_line) or re.search(
                r"https?://[^\s)]+", block
            )
            url_text = url.group(0) if url else ""
            entries.append(
                {
                    "title": title.strip(),
                    "teacher": teacher,
                    "url": url_text,
                    "why": " ".join(why_lines),
                    "fetchable": bool(url_text)
                    and not _READING_URL_RE.search(url_text),
                }
            )
    return entries


def stub_slug(name: str) -> str:
    """A rooms-in-waiting view id for an unfetched path item.

    Prefixed "queued-" so it can never collide with a real talk folder
    (fetch_talk picks the real slug later; the stub room simply gives
    way to the real one on the next shelf swap).
    """
    flat = re.sub(r"[^a-z0-9]+", "-", normalize_title(name)).strip("-")
    return f"queued-{flat or 'talk'}"


def curriculum_stub(name: str, entries: list[dict]) -> dict:
    """What the curriculum knows about one unfetched path item.

    Matches `name` (a STUDY.md Queued line) against curriculum entries
    with the same tolerance the sidebar hints use (normalize_title,
    either-way containment). No match still returns a bare stub — the
    room exists either way, its button just asks instead of fetching.
    """
    key = normalize_title(name)
    stub = {
        "name": name,
        "slug": stub_slug(name),
        "title": name,
        "teacher": "",
        "url": "",
        "why": "",
        "fetchable": False,
    }
    for entry in entries:
        ekey = normalize_title(entry["title"])
        if key == ekey or key in ekey or ekey in key:
            stub.update(
                title=entry["title"],
                teacher=entry["teacher"],
                url=entry["url"],
                why=entry["why"],
                fetchable=entry["fetchable"],
            )
            break
    return stub


def render_path_strip(path: dict) -> str:
    """A small calm strip: studied talks with a check, queued with an arrow.

    Rendered in the #home view (the sidebar's talks list carries these
    states inline now). Returns "" when there is nothing to show, so a
    missing or empty STUDY.md leaves the page untouched (it must stay
    statically shareable).
    """
    marks = (
        ("studied", "✓", "path-done"),
        ("queued", "→", "path-next"),
        ("parked", "·", "path-parked"),
    )
    items = [
        f'<span class="{css}">{mark} {escape(name)}</span>'
        for key, mark, css in marks
        for name in path.get(key, [])
    ]
    if not items:
        return ""
    return (
        '<div class="path-strip">\n<h2>The path</h2>\n'
        '<p class="path-items">\n' + "\n".join(items) + "\n</p>\n</div>"
    )


def probe(talk_dir: Path) -> dict:
    """See which study artifacts a talk folder actually has."""
    audio = next(
        (p for p in sorted(talk_dir.glob("audio.*")) if p.suffix.lower() in AUDIO_EXTENSIONS),
        None,
    )
    return {
        "primer_mp3": (talk_dir / "primer.mp3").exists(),
        "primer_md": (talk_dir / "primer.md").exists(),
        "notes_md": (talk_dir / "notes.md").exists(),
        "transcript_md": (talk_dir / "transcript.md").exists(),
        "audio": audio.name if audio else None,
        "artifacts": sorted(p.name for p in (talk_dir / "artifacts").glob("*.html")),
        "thumbnail": (talk_dir / "thumbnail.jpg").exists(),
        "transcript_json": (talk_dir / "transcript.json").exists(),
    }


STYLE = """
  body { background: #faf7f2; color: #3c3833; margin: 0;
         font: 17px/1.6 -apple-system, "Helvetica Neue", Arial, sans-serif; }
  #layout { display: flex; min-height: 100vh; align-items: stretch; }
  #sidebar { width: 260px; flex-shrink: 0; box-sizing: border-box;
             background: #f5f0e6; border-right: 1px solid #e8e0d3;
             padding: 2rem 1.25rem 1.5rem; position: sticky; top: 0;
             height: 100vh; overflow-y: auto; }
  #sidebar h1 { font-size: 1.35rem; margin: 0 0 0.2rem; }
  #sidebar h2 { font-size: 0.95rem; color: #8a7f70; margin: 1.75rem 0 0.5rem;
                text-transform: lowercase; letter-spacing: 0.03em; }
  .epigraph { color: #8a7f70; font-style: italic; margin-top: 0;
              font-size: 0.9rem; }
  #talk-nav { list-style: none; margin: 0; padding: 0; }
  #talk-nav a { display: block; padding: 0.45rem 0.6rem; border-radius: 8px;
                color: #5a4d3a; text-decoration: none; font-size: 0.95rem;
                line-height: 1.35; }
  #talk-nav a:hover { background: #efe7d9; }
  #talk-nav a.active { background: #efe7d9; }
  .nav-teacher { display: block; color: #a99e8e; font-size: 0.8rem; }
  .nav-state { font-size: 0.85rem; }
  .nav-done { color: #6d5f4b; }
  .nav-next { color: #a99e8e; }
  .nav-legend { margin: 0.6rem 0 0; padding: 0 0.6rem; color: #a99e8e;
                font-size: 0.75rem; }
  .nav-unfetched a { color: #a99e8e; } /* a room-in-waiting: muted, real */
  .side-muted { color: #a99e8e; font-size: 0.85rem; font-style: italic; }
  .begin-link { display: inline-block; margin: 1rem 0 0; color: #6d5f4b;
                font-size: 0.92rem; text-decoration: none;
                border-bottom: 1px solid #d8cbb4; }
  .how-lines { color: #5a4d3a; font-size: 0.95rem; }
  .how-lines p { margin: 0.45rem 0; }
  #sidebar footer { margin-top: 2.5rem; }
  #sidebar-toggle { display: none; position: fixed; top: 0.7rem; left: 0.7rem;
                    z-index: 3; font: inherit; color: #5a4d3a;
                    background: #efe7d9; border: 1px solid #e8e0d3;
                    border-radius: 8px; padding: 0.2rem 0.7rem;
                    cursor: pointer; }
  main { flex: 1; min-width: 0; max-width: 680px; margin: 0 auto;
         padding: 2rem 1.5rem 11rem; } /* room for the fixed tray */
  .js .view { display: none; }
  .js .view.active { display: block; }
  .js .view.audible { display: block; position: fixed;
                      left: -10000px; top: 0; width: 640px;
                      pointer-events: none; } /* playing, parked offscreen */
  /* The collapser is a fletched arrow — this is Second Arrow, after all.
     One glyph, drawn once: it points left to tuck the sidebar away and
     is mirrored (scaleX) to point right when offering it back. Quiet ink
     that deepens on hover; a comfortable ~2.2rem hit target. */
  #sidebar-collapse { position: absolute; top: 0.8rem; right: 0.4rem;
                      width: 2.2rem; height: 2.2rem; display: flex;
                      align-items: center; justify-content: center;
                      color: #a99e8e; background: none;
                      border: none; border-radius: 8px;
                      padding: 0; cursor: pointer;
                      transition: color 0.15s ease, background 0.15s ease; }
  #sidebar-collapse svg { width: 1.35rem; height: 1.35rem; }
  #sidebar-collapse:hover { background: #efe7d9; color: #5a4d3a; }
  /* z-index 5: like the now-playing capsule, the reopen arrow stays
     reachable above the conversation overlay (z-index 4) — the sidebar
     must never be out of reach while talking with the guide. */
  #sidebar-reopen { display: none; position: fixed; top: 0.8rem;
                    left: 0.7rem; z-index: 5; width: 2.4rem; height: 2.4rem;
                    align-items: center; justify-content: center;
                    color: #5a4d3a; background: #efe7d9;
                    border: 1px solid #e8e0d3; border-radius: 8px;
                    padding: 0; cursor: pointer;
                    transition: color 0.15s ease, background 0.15s ease; }
  #sidebar-reopen svg { width: 1.35rem; height: 1.35rem;
                        transform: scaleX(-1); } /* same arrow, flying back */
  #sidebar-reopen:hover { background: #e7dcc8; color: #4a4038; }
  @media (min-width: 721px) {
    #sidebar { transition: margin-left 0.25s ease; }
    body.sidebar-collapsed #sidebar { margin-left: -260px;
                                      visibility: hidden; }
    body.sidebar-collapsed #guide-chat { left: 0; }
    body.sidebar-collapsed #sidebar-reopen { display: flex; }
  }
  @media (max-width: 720px) {
    #sidebar-toggle { display: block; }
    #sidebar-collapse { display: none; } /* mobile keeps its own drawer */
    #sidebar { position: fixed; z-index: 2; left: -290px;
               transition: left 0.2s ease; box-shadow: none; }
    #sidebar.open { left: 0; box-shadow: 0 0 24px rgba(60, 56, 51, 0.25); }
    main { padding-top: 3.5rem; }
    #guide-chat { left: 0; }
  }
  h1, h2, h3, h4, h5 { font-family: Georgia, "Times New Roman", serif;
                       font-weight: normal; color: #4a4038; }
  h1 { font-size: 1.7rem; margin-bottom: 0.2rem; }
  .card { background: #fffdf9; border: 1px solid #e8e0d3; border-radius: 10px;
          padding: 1.5rem 1.75rem; margin: 2rem 0; }
  .card h2 { font-size: 1.3rem; margin: 0 0 0.2rem; }
  .meta { color: #8a7f70; font-size: 0.9rem; margin: 0 0 1rem; }
  .reach { color: #6d5f4b; }
  .path-strip { margin-top: 1.25rem; }
  .path-strip h2 { font-size: 0.95rem; color: #8a7f70; margin: 0 0 0.2rem; }
  .path-items { display: flex; flex-wrap: wrap; gap: 0.3rem 1.2rem;
                margin: 0.4rem 0 0; font-size: 0.92rem; }
  .path-done { color: #6d5f4b; }
  .path-next { color: #a99e8e; }
  .path-parked { color: #c2b8a6; }
  .player-label { margin: 1rem 0 0.3rem; font-size: 0.9rem; color: #6d5f4b; }
  .listened-line { margin: 0.4rem 0 0; color: #8a9a70; font-size: 0.85rem; }
  .listened-replay { font: inherit; font-size: 0.85rem; color: #7a6a50;
                     background: none; border: none; padding: 0;
                     cursor: pointer; text-decoration: underline; }
  .mark-heard, .mark-unheard { font: inherit; font-size: 0.82rem;
                color: #a99e8e;
                background: none; border: none; padding: 0; cursor: pointer;
                border-bottom: 1px dotted #d8cbb4; }
  .mark-heard:hover, .mark-unheard:hover { color: #7a6a50; }
  .mark-heard:disabled, .mark-unheard:disabled { color: #c2b8a6;
                         cursor: default;
                         border-bottom-color: transparent; }
  .card-status { margin: 0.7rem 0 0.2rem; display: flex; align-items: center;
                 flex-wrap: wrap; gap: 0.3rem 0.9rem; }
  .status-mark { font-size: 0.9rem; }
  .status-done { color: #6d5f4b; }
  .status-next { color: #a99e8e; }
  .status-heard { color: #8a9a70; }
  .done-for-now { font: inherit; font-size: 0.92rem; color: #5a4d3a;
                  background: #efe7d9; border: 1px solid #d8cbb4;
                  border-radius: 999px; padding: 0.45rem 1.1rem;
                  cursor: pointer; }
  .done-for-now:hover { background: #e7dcc8; }
  .done-for-now:disabled { color: #a99e8e; cursor: default; }
  .wrap-up-talk { font: inherit; font-size: 0.85rem; color: #7a6a50;
                  background: none; border: none; padding: 0;
                  cursor: pointer; border-bottom: 1px dotted #d8cbb4; }
  .wrap-up-talk:hover { color: #5a4d3a; }
  .state-note { margin: 0.5rem 0 0; color: #a99e8e; font-size: 0.85rem;
                font-style: italic; }
  audio { width: 100%; }
  .source-link { display: inline-block; margin-top: 1rem; padding: 0.5rem 1rem;
                 background: #efe7d9; border-radius: 8px; color: #5a4d3a;
                 text-decoration: none; }
  .yt-embed { margin-top: 1rem; }
  .yt-play { font: inherit; color: #5a4d3a; background: #efe7d9; border: none;
             border-radius: 8px; padding: 0.5rem 1rem; cursor: pointer; }
  .yt-frame { aspect-ratio: 16 / 9; }
  .yt-frame iframe { width: 100%; height: 100%; border: 0;
                     border-radius: 8px; }
  .yt-thumb { position: relative; display: block; width: 100%; padding: 0;
              border: none; background: none; cursor: pointer;
              border-radius: 8px; overflow: hidden; }
  .yt-thumb img { display: block; width: 100%; }
  .yt-glyph { position: absolute; top: 50%; left: 50%;
              transform: translate(-50%, -50%); width: 3.2rem;
              height: 3.2rem; line-height: 3.2rem; border-radius: 999px;
              background: rgba(40, 35, 28, 0.72); color: #fdf9f0;
              font-size: 1.25rem; text-align: center; }
  .yt-thumb:hover .yt-glyph { background: rgba(40, 35, 28, 0.9); }
  .yt-duration { position: absolute; right: 0.5rem; bottom: 0.5rem;
                 background: rgba(40, 35, 28, 0.75); color: #fdf9f0;
                 font-size: 0.78rem; border-radius: 6px;
                 padding: 0.05rem 0.45rem; }
  .seg { cursor: pointer; margin: 0.5rem 0; border-radius: 6px;
         padding: 0.1rem 0.3rem; }
  .seg:hover { background: #f2ece1; }
  .seg.active { background: #efe7d9; }
  .seg-time { color: #a99e8e; font-size: 0.8rem; margin-right: 0.4rem; }
  #now-playing { position: fixed; top: 0.9rem; right: 1.2rem; z-index: 5;
                 display: flex; align-items: center; gap: 0.1rem;
                 background: #fffdf9; border: 1px solid #e8e0d3;
                 border-radius: 999px; padding: 0.22rem 0.45rem 0.22rem 0.3rem;
                 box-shadow: 0 4px 14px rgba(60, 56, 51, 0.13); }
  #now-playing[hidden] { display: none; } /* flex must not defeat hidden */
  #np-body { display: flex; align-items: center; gap: 0.5rem; font: inherit;
             background: none; border: none; cursor: pointer;
             color: #5a4d3a; padding: 0.1rem 0.3rem; min-width: 0; }
  #np-thumb { width: 2rem; height: 2rem; object-fit: cover;
              border-radius: 999px; display: block; }
  #np-glyph { width: 2rem; height: 2rem; line-height: 2rem;
              text-align: center; background: #efe7d9;
              border-radius: 999px; font-size: 0.8rem; }
  #np-title { max-width: 10.5rem; white-space: nowrap; overflow: hidden;
              text-overflow: ellipsis; font-size: 0.88rem; }
  #np-time { color: #a99e8e; font-size: 0.8rem;
             font-variant-numeric: tabular-nums; }
  #np-play, #np-stop, #np-expand { font: inherit; font-size: 0.85rem;
             color: #5a4d3a; background: none; border: none;
             cursor: pointer; padding: 0.35rem 0.5rem;
             border-radius: 999px; }
  #np-play:hover, #np-stop:hover, #np-expand:hover { background: #efe7d9; }
  .cluster { border-top: 1px solid #f0e9dd; margin-top: 1.25rem;
             padding-top: 0.75rem; }
  .cur-onshelf { color: #6d5f4b; }
  .cur-hint { color: #a99e8e; font-size: 0.85rem; font-style: italic; }
  blockquote { margin: 0.75rem 0 0.75rem 0.25rem; padding: 0.1rem 0 0.1rem 0.9rem;
               border-left: 3px solid #d8cbb4; color: #6d5f4b; }
  .artifact-list { list-style: none; margin: 0.5rem 0 0; padding: 0; }
  .artifact-item { margin: 0.75rem 0; }
  .artifact-name { color: #6d5f4b; font-size: 0.95rem; }
  .artifact-open { margin-left: 0.75rem; font-size: 0.85rem; color: #a99e8e; }
  .artifact-note { color: #a99e8e; font-size: 0.85rem; font-style: italic; }
  .make-interactive, .mark-moments, .make-primer, .make-notes,
  .more-moments, .fetch-stub, .ask-stub {
                      font: inherit; font-size: 0.92rem; color: #5a4d3a;
                      background: #f6f1e7; border: 1px dashed #d8cbb4;
                      border-radius: 999px; padding: 0.45rem 1.1rem;
                      cursor: pointer; }
  .make-interactive:hover, .mark-moments:hover, .make-primer:hover,
  .make-notes:hover, .more-moments:hover, .fetch-stub:hover,
  .ask-stub:hover { background: #efe7d9; }
  /* The uniform ✦ pattern: an empty section still renders, holding its
     generate button and one quiet line saying what it creates. */
  .gen-empty { display: flex; flex-direction: column;
               align-items: flex-start; gap: 0.3rem; }
  .gen-desc { color: #a99e8e; font-size: 0.85rem; font-style: italic; }
  .gen-more { margin: 0.6rem 0 0; }
  .more-moments { font-size: 0.85rem; padding: 0.3rem 0.9rem; }
  .fetch-stub { background: #efe7d9; border-style: solid; } /* the primary */
  .fetch-stub:hover { background: #e7dcc8; }
  /* "Listen for": the guide's curated jump-to moments — anchored
     listening chips, each one a transcript-click-shaped seek. */
  .moments { display: flex; flex-direction: column; align-items: flex-start;
             gap: 0.4rem; margin-top: 0.5rem; }
  .moment-chip { font: inherit; font-size: 0.88rem; color: #5a4d3a;
                 text-align: left; background: #f9f5ec;
                 border: 1px solid #e8e0d3; border-radius: 12px;
                 padding: 0.35rem 0.9rem; cursor: pointer; }
  .moment-chip:hover { background: #efe7d9; }
  .moment-time { color: #a9853f; font-variant-numeric: tabular-nums; }
  /* The full transcript: a quiet sub-expander behind the moments —
     the front layer invites, the segments wait. */
  details.full-transcript { margin-top: 0.9rem; border-top: none;
                            padding-top: 0; }
  details.full-transcript summary { font-size: 0.88rem; color: #a99e8e; }
  /* Prompt chips: quiet one-tap suggestions over a focused, EMPTY input.
     Same gentle rise as the peek — no layout shove, no stolen focus. */
  #prompt-chips { display: flex; flex-wrap: wrap; gap: 0.4rem;
                  margin: 0.15rem 0.6rem 0.1rem;
                  animation: peek-rise 0.25s ease; }
  #prompt-chips[hidden] { display: none; } /* flex must not defeat hidden */
  .prompt-chip { font: inherit; font-size: 0.85rem; color: #5a4d3a;
                 background: #f6f1e7; border: 1px dashed #d8cbb4;
                 border-radius: 999px; padding: 0.3rem 0.9rem;
                 cursor: pointer; }
  .prompt-chip:hover { background: #efe7d9; }
  .artifact-frame { display: block; width: 100%; height: 480px;
                    margin-top: 0.5rem; border: 1px solid #e8e0d3;
                    border-radius: 8px; background: #fffdf9;
                    resize: vertical; overflow: auto; }
  details { margin-top: 1rem; border-top: 1px solid #f0e9dd; padding-top: 0.75rem; }
  summary { cursor: pointer; color: #8a7f70; font-size: 0.95rem; }
  .raw-link { font-size: 0.85rem; margin: 0.5rem 0 0.3rem; }
  .raw-link a { color: #a99e8e; }
  .scroll-box { max-height: 24em; overflow-y: auto; background: #fbf8f2;
                border: 1px solid #f0e9dd; border-radius: 8px;
                padding: 0.25rem 1rem; font-size: 0.95rem; }
  details > *:not(summary) { margin-left: 0.25rem; }
  a { color: #7a6a50; }
  footer { color: #a99e8e; font-size: 0.85rem; margin-top: 3rem;
           border-top: 1px solid #e8e0d3; padding-top: 1rem; }
  code { background: #f2ece1; padding: 0.1em 0.35em; border-radius: 4px;
         font-size: 0.85em; }
  /* The tray is ONE immutable fixture: same node, same fixed position,
     same width in every state and every room — content scrolls beneath
     it (main's bottom padding keeps everything reachable). Docked it is
     just the floating bar; conversation stretches the SAME layer to the
     top and fills in the stream above the unmoved bar. */
  #guide-chat { position: fixed; left: 260px; right: 0; bottom: 0;
                z-index: 4; margin: 0; border: none; border-radius: 0;
                background: transparent; box-shadow: none;
                display: flex; flex-direction: column;
                justify-content: flex-end;
                padding: 0 max(1.5rem, calc(50% - 340px)) 1rem;
                transition: left 0.25s ease;
                pointer-events: none; }
  #guide-chat > * { pointer-events: auto; }
  #chat-messages { max-height: 38vh; min-height: 5rem; overflow-y: auto;
                   padding: 0.25rem 0; border-top: 1px solid #f0e9dd; }
  .chat-msg { white-space: pre-wrap; margin: 0.6rem 0; padding: 0.5rem 0.8rem;
              border-radius: 8px; font-size: 0.95rem; }
  .chat-user { background: #e7dcc8; margin-left: 2.5rem;
               border-radius: 10px 4px 10px 10px; }
  .chat-guide { background: #f9f5ec; margin-right: 2.5rem;
                border: 1px solid #eee4d2;
                border-radius: 4px 10px 10px 10px; }
  .chat-thinking { color: #a99e8e; font-style: italic; }
  .chat-system { background: none; text-align: center; color: #a99e8e;
                 font-size: 0.8rem; font-style: italic; padding: 0; }
  #chat-identity { font-size: 0.8rem; }
  #chat-identity a { color: #a99e8e; text-decoration: none;
                     border-bottom: 1px dotted #d8cbb4; }
  #chat-identity a:hover { color: #5a4d3a; }
  #chat-model { font: inherit; font-size: 0.85rem;
                color: #5a4d3a; background: #fffdf9;
                border: 1px solid #e8e0d3; border-radius: 8px;
                padding: 0.15rem 0.4rem; max-width: 15rem;
                margin: 0.2rem 0 0 1.7rem; display: block; }
  #machinery { margin-top: 1.8rem; padding-top: 1rem;
               border-top: 1px solid #f0e9dd; }
  .machinery-link a { color: #a99e8e; font-size: 0.85rem;
                      text-decoration: none;
                      border-bottom: 1px dotted #d8cbb4; }
  .machinery-link a:hover { color: #5a4d3a; }
  #machinery-list { list-style: none; padding: 0; margin: 0; }
  #machinery-list li { display: flex; justify-content: space-between;
                  gap: 1rem; font-size: 0.85rem; color: #5a4d3a;
                  padding: 0.15rem 0; }
  .machinery-state { color: #a99e8e; text-align: right; }
  .set-group { margin-top: 1.6rem; padding-top: 1rem;
               border-top: 1px solid #f0e9dd; }
  .set-group h3 { font-size: 0.95rem; color: #8a7f70; margin: 0 0 0.45rem; }
  .set-headline { color: #5a4d3a; line-height: 1.55; }
  .set-state { color: #a99e8e; }
  .set-fine { color: #a99e8e; font-size: 0.85rem; line-height: 1.55; }
  .set-fine code, .set-headline code { background: #f3ecdd;
                border-radius: 4px; padding: 0 0.25rem; font-size: 0.8rem; }
  .pick-rows { margin: 0.5rem 0 0.2rem; }
  .pick-row { display: flex; gap: 0.55rem; align-items: center;
              padding: 0.22rem 0; font-size: 0.92rem; color: #5a4d3a;
              cursor: pointer; }
  .pick-row input { accent-color: #a9853f; margin: 0; }
  .pick-row input:disabled { cursor: default; }
  .pick-row input:disabled + span { color: #c2b8a6; }
  .prep-btn { font: inherit; font-size: 0.85rem; color: #5a4d3a;
              background: #efe7d9; border: 1px solid #d8cbb4;
              border-radius: 999px; padding: 0.25rem 0.9rem;
              cursor: pointer; margin-right: 0.5rem; }
  .prep-btn:hover { background: #e7dcc8; }
  .prep-btn:disabled { color: #a99e8e; cursor: default; }
  .side-settings { display: inline-block; margin-top: 0.5rem;
                   color: #a99e8e; text-decoration: none;
                   border-bottom: 1px dotted #d8cbb4; }
  .side-settings:hover { color: #7a6a50; }
  .chat-row { display: flex; gap: 0.5rem; align-items: flex-start;
              margin: 0.6rem 0; }
  .chat-row-user { flex-direction: row-reverse; }
  .chat-avatar { width: 1.7rem; height: 1.7rem; flex-shrink: 0;
                 margin-top: 0.15rem; }
  .chat-avatar svg { width: 100%; height: 100%; display: block; }
  .chat-row:not(.chat-run-start) .chat-avatar { visibility: hidden; }
  .chat-body { flex: 1; min-width: 0; }
  .chat-row-user .chat-body { display: flex; flex-direction: column;
                              align-items: flex-end; }
  .chat-label { color: #a99e8e; font-size: 0.75rem; margin: 0 0.2rem 0.15rem; }
  .chat-row .chat-msg { margin: 0; max-width: 92%; }
  .chat-go { display: block; margin-top: 0.6rem; font: inherit;
             font-size: 0.85rem; color: #5a4d3a; background: #efe7d9;
             border: none; border-radius: 999px; padding: 0.25rem 0.9rem;
             cursor: pointer; }
  .chat-go:hover { background: #e7dcc8; }
  #chat-minimize { display: none; }
  .chat-conversation #chat-minimize { display: block; position: absolute;
                 top: 1rem; right: 1.2rem; font: inherit; font-size: 0.92rem;
                 color: #5a4d3a; background: #efe7d9; border: none;
                 border-radius: 999px; padding: 0.5rem 1.2rem;
                 cursor: pointer; }
  .chat-conversation #chat-minimize:hover { background: #e7dcc8; }
  .chat-conversation-mode #now-playing { top: 4.4rem; }
  #guide-chat.chat-docked h2,
  .chat-docked #chat-messages { display: none; }
  #guide-chat.chat-docked #chat-identity { opacity: 0.55;
                margin: 0 0.6rem 0.3rem; text-align: right; }
  #guide-chat.chat-docked #chat-identity:hover,
  #guide-chat.chat-docked #chat-identity:focus-within { opacity: 1; }
  #guide-chat.chat-conversation { top: 0; background: #fcf9f3;
                pointer-events: auto; padding-top: 2rem; }
  #guide-chat.chat-conversation #chat-messages { flex: 1; max-height: none;
                                                 font-size: 1.02rem; }
  #chat-peek { display: flex; align-items: flex-start; gap: 0.55rem;
               background: #f9f5ec; border: 1px solid #eee4d2;
               border-radius: 14px; padding: 0.6rem 0.7rem;
               margin-bottom: 0.5rem;
               box-shadow: 0 6px 18px rgba(60, 56, 51, 0.10);
               animation: peek-rise 0.25s ease; }
  #chat-peek[hidden] { display: none; } /* flex must not defeat hidden */
  @keyframes peek-rise {
    from { opacity: 0; transform: translateY(7px); }
    to { opacity: 1; transform: none; }
  }
  #peek-mark { width: 1.5rem; height: 1.5rem; flex-shrink: 0;
               margin-top: 0.1rem; }
  #peek-mark svg { width: 100%; height: 100%; display: block; }
  #peek-body { flex: 1; min-width: 0; text-align: left; font: inherit;
               color: inherit; background: none; border: none;
               padding: 0; cursor: pointer; }
  #peek-text { display: -webkit-box; -webkit-line-clamp: 3;
               -webkit-box-orient: vertical; overflow: hidden;
               white-space: pre-wrap; font-size: 0.93rem; }
  #peek-more { display: none; color: #a9853f; font-size: 0.8rem; }
  .peek-settled #peek-more { display: inline; }
  #peek-action { flex-shrink: 0; }
  #peek-action .chat-go { margin-top: 0; }
  #peek-dismiss { font: inherit; font-size: 0.8rem; color: #a99e8e;
                  background: none; border: none; cursor: pointer;
                  padding: 0.1rem 0.35rem; flex-shrink: 0; }
  .guide-lock { font: inherit; font-size: 0.8rem; background: none;
                border: none; cursor: pointer; padding: 0.3rem 0.4rem;
                border-radius: 999px; opacity: 0.7; }
  .guide-lock:hover { opacity: 1; background: #efe7d9; }
  .room-lock { position: absolute; top: 1.1rem; right: 1.2rem; }
  .card.view { position: relative; } /* anchors the room lock */
  #fresh-chip { display: block; width: 100%; text-align: center;
                font: inherit; font-size: 0.85rem; color: #5a4d3a;
                background: #f6f1e7; border: 1px dashed #d8cbb4;
                border-radius: 999px; padding: 0.3rem 0.9rem;
                margin-bottom: 0.5rem; cursor: pointer; }
  #fresh-chip:hover { background: #efe7d9; }
  #fresh-chip[hidden] { display: none; } /* the chip lesson, again */
  .working { position: relative; }
  .working::after { content: ""; position: absolute; right: 0.4rem;
                    top: 50%; transform: translateY(-50%);
                    width: 0.45rem; height: 0.45rem; border-radius: 999px;
                    background: #a9853f;
                    animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse {
    0%, 100% { opacity: 0.25; }
    50% { opacity: 1; }
  }
  #reflection-chip { display: flex; align-items: center; gap: 0.3rem;
                     margin-top: 0.5rem; }
  #reflection-chip[hidden] { display: none; } /* flex must not defeat hidden */
  #reflection-send { flex: 1; text-align: left; font: inherit;
                     font-size: 0.85rem; color: #5a4d3a; background: #f6f1e7;
                     border: 1px dashed #d8cbb4; border-radius: 999px;
                     padding: 0.3rem 0.9rem; cursor: pointer; }
  #reflection-send:hover { background: #efe7d9; }
  #reflection-dismiss { font: inherit; font-size: 0.8rem; color: #a99e8e;
                        background: none; border: none; cursor: pointer;
                        padding: 0.2rem 0.4rem; }
  /* The quiet working line: always-on visibility while a turn streams —
     the current tool-progress text (or "the guide is thinking…") plus
     the ▢ stop control. Sits just above the input, in every chat state. */
  #chat-working { display: flex; align-items: center; gap: 0.6rem;
                  color: #a99e8e; font-size: 0.82rem; font-style: italic;
                  margin: 0.15rem 0.6rem 0; }
  #chat-working[hidden] { display: none; } /* flex must not defeat hidden */
  #working-text { flex: 1; min-width: 0; white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; }
  #chat-stop { font: inherit; font-size: 0.78rem; font-style: normal;
               color: #7a6a50; background: none; flex-shrink: 0;
               border: 1px solid #d8cbb4; border-radius: 999px;
               padding: 0.05rem 0.6rem; cursor: pointer; }
  #chat-stop:hover { background: #efe7d9; }
  /* The queued note: a send while the guide is busy is never dropped —
     it waits here, visibly, and goes the moment the turn ends. */
  #chat-queued { color: #a99e8e; font-size: 0.82rem; font-style: italic;
                 margin: 0.15rem 0.6rem 0; }
  #chat-form { display: flex; gap: 0.45rem; margin: 0.6rem 0 0;
               align-items: flex-end; background: #fffdf9;
               border: 1px solid #e6ddcc; border-radius: 22px;
               padding: 0.45rem;
               box-shadow: 0 10px 30px rgba(60, 56, 51, 0.14); }
  #chat-form textarea { flex: 1; font: inherit; color: inherit; resize: none;
               background: #fbf8f2; border: 1px solid transparent;
               border-radius: 14px; padding: 0.6rem 0.9rem;
               line-height: 1.45; max-height: 6.4rem;
               box-shadow: inset 0 1px 3px rgba(60, 56, 51, 0.05); }
  #chat-form textarea::placeholder { color: #b3a893; font-style: italic; }
  #chat-form textarea:focus { outline: none; border-color: #d3bd92;
               box-shadow: inset 0 1px 3px rgba(60, 56, 51, 0.05),
                           0 0 0 3px rgba(169, 133, 63, 0.14); }
  #chat-send { width: 2.6rem; height: 2.6rem; flex-shrink: 0; display: flex;
               align-items: center; justify-content: center;
               color: #fdf9f0; background: #a9853f; border: none;
               border-radius: 999px; cursor: pointer;
               transition: background 0.15s ease, opacity 0.15s ease; }
  #chat-send:hover:not(:disabled) { background: #8f6f33; }
  #chat-send:disabled { opacity: 0.35; cursor: default; }
  #chat-send svg { width: 1.15rem; height: 1.15rem; }
  #chat-open { width: 2.6rem; height: 2.6rem; flex-shrink: 0; display: flex;
               align-items: center; justify-content: center;
               color: #8a7f70; background: none; border: none;
               border-radius: 999px; cursor: pointer; }
  #chat-open:hover { background: #efe7d9; color: #5a4d3a; }
  #chat-open svg { width: 1.3rem; height: 1.3rem; }
  .chat-conversation #chat-open { display: none; }
"""


# The panel starts hidden and only appears when /health answers — so the
# static file:// shelf keeps working unchanged. Guide replies stream in as
# chunked plain text (fetch + ReadableStream); errors before the stream
# starts arrive as JSON. The pill toggle picks which brain each message is
# sent to (per-request "brain" field), driven by /health's availability
# map. Replies are rendered with textContent (never innerHTML): model
# output stays inert text.
CHAT_PANEL = """<section class="chat-docked" id="guide-chat" hidden>
<template id="avatar-guide">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21.2 C9.6 18.4 4.9 15.7 4.9 10.7 C4.9 6.6 8 3.6 12 2.9 C16 3.6 19.1 6.6 19.1 10.7 C19.1 15.7 14.4 18.4 12 21.2 Z" fill="none" stroke="#a9853f" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><path d="M12 5.6 V18.4" fill="none" stroke="#a9853f" stroke-width="1.1" stroke-linecap="round" opacity="0.65"/></svg>
</template>
<template id="avatar-user">
<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.4" r="3.4" fill="#7a6a50"/><path d="M4.6 20c1.6-4 5-5.6 7.4-5.6s5.8 1.6 7.4 5.6" fill="none" stroke="#7a6a50" stroke-width="2.4" stroke-linecap="round"/></svg>
</template>
<h2>the guide</h2>
<button type="button" id="chat-minimize" title="back to the page — everything stays as you left it">▾ back to the room</button>
<p class="meta" id="chat-identity" hidden>
<a href="#settings" id="identity-link" title="settings — the guide's brain, fallbacks, nightly prep"></a>
</p>
<div id="chat-messages"></div>
<div id="chat-peek" hidden>
<span id="peek-mark" aria-hidden="true"></span>
<button type="button" id="peek-body" title="open the conversation">
<span id="peek-text"></span>
<span id="peek-more">…more</span>
</button>
<span id="peek-action"></span>
<button type="button" id="peek-dismiss" aria-label="dismiss">✕</button>
</div>
<div id="reflection-chip" hidden>
<button type="button" id="reflection-send"></button>
<button type="button" id="reflection-dismiss" aria-label="dismiss">✕</button>
</div>
<button type="button" id="fresh-chip" hidden>the shelf has new content — refresh</button>
<div id="chat-working" hidden>
<span id="working-text">the guide is thinking…</span>
<button type="button" id="chat-stop" title="stop this reply — what arrived stays">▢ stop</button>
</div>
<p id="chat-queued" hidden></p>
<div id="prompt-chips" hidden></div>
<form id="chat-form">
<button type="button" id="chat-open" title="open the conversation" aria-label="open the conversation">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 5.5h15v10.5h-9l-4 3.5v-3.5h-2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
</button>
<textarea id="chat-input" rows="1" placeholder="Where are you right now?"></textarea>
<button type="submit" id="chat-send" title="Send" aria-label="Send" disabled>
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V6M6.5 11.5 12 6l5.5 5.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
</button>
</form>
</section>

<script>
(function () {
  var panel = document.getElementById("guide-chat");
  var list = document.getElementById("chat-messages");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var send = document.getElementById("chat-send");
  var identityRow = document.getElementById("chat-identity");
  var identityLink = document.getElementById("identity-link");
  var history = [];
  var brain = null; // which brain the next message goes to (/health default)
  var session = null; // which conversation the next message continues
  var model = null; // which installed local model the ollama brain uses
  var modelList = null; // /api/models payload, kept for settings re-renders
  var hermes = null; // /health's hermes entry: wired, reason, model, routes
  var hermesRoute = null; // the picked route alias (null = profile default)
  var healthInfo = null; // the last /health payload (settings + machinery)

  function add(role, text) {
    var div = document.createElement("div");
    div.className = "chat-msg chat-" + role;
    div.textContent = text; // textContent only — model output stays inert text
    if (role !== "user" && role !== "guide") {
      list.appendChild(div); // system lines stay centered, unbubbled
      list.scrollTop = list.scrollHeight;
      return div;
    }
    // Who is speaking, unmistakably: avatar + label on the first bubble
    // of each same-speaker run; later bubbles in the run stay bare.
    var row = document.createElement("div");
    row.className = "chat-row chat-row-" + role;
    var prev = list.lastElementChild;
    var runStart = !prev || !prev.classList.contains("chat-row-" + role);
    if (runStart) row.classList.add("chat-run-start");
    var avatar = document.createElement("span");
    avatar.className = "chat-avatar";
    var tpl = document.getElementById(
      role === "user" ? "avatar-user" : "avatar-guide");
    if (tpl && tpl.content && tpl.content.firstElementChild) {
      // Cloned from the static template — never built from message text.
      avatar.appendChild(tpl.content.firstElementChild.cloneNode(true));
    }
    row.appendChild(avatar);
    var body = document.createElement("div");
    body.className = "chat-body";
    if (runStart) {
      var label = document.createElement("div");
      label.className = "chat-label";
      label.textContent = role === "user" ? "you" : "the guide";
      body.appendChild(label);
    }
    body.appendChild(div);
    row.appendChild(body);
    list.appendChild(row);
    list.scrollTop = list.scrollHeight;
    return div;
  }

  // --- two states, nothing between: docked (looking at the page) and
  // conversation (talking — generous, most of the pane). The page under
  // a conversation is hidden, never unmounted: audio keeps playing and
  // every scroll position is exactly where you left it.
  var chatState = "docked"; // always start docked: the room owns the screen
  var busy = false; // a reply in flight (independent of empty-input dimming)

  function updateSendState() {
    // Dim Send only when there is nothing to send — while the guide is
    // busy a send is still meaningful: it queues (sendOrQueue below).
    send.disabled = !input.value.trim();
  }

  // --- busy, visibly: the working line, the stop control, the queue ------
  // While a turn streams, one quiet line near the input always says so —
  // the current tool-progress text, or "the guide is thinking…" — with a
  // small ▢ stop beside it. And no send is EVER silently dropped: while
  // busy, the newest message waits in ONE visible queue slot and goes
  // the moment the turn ends.
  var workingLine = document.getElementById("chat-working");
  var workingText = document.getElementById("working-text");
  var queuedNote = document.getElementById("chat-queued");
  var queuedMessage = null; // one slot; a newer message replaces it

  function setWorking(text) {
    if (!text) { workingLine.hidden = true; return; }
    workingLine.hidden = false;
    workingText.textContent = text;
  }

  function renderQueuedNote() {
    if (!queuedMessage) { queuedNote.hidden = true; return; }
    var brief = queuedMessage.length > 60
      ? queuedMessage.slice(0, 60) + "…" : queuedMessage;
    queuedNote.hidden = false;
    queuedNote.textContent =
      "queued — the guide is finishing something: “" + brief + "”";
  }

  function sendOrQueue(text) {
    if (!text) return;
    if (busy) {
      queuedMessage = text; // the newest ask wins the one slot
      renderQueuedNote();
      return;
    }
    sendMessage(text);
  }

  document.getElementById("chat-stop").addEventListener("click", function () {
    // Abort the in-flight turn server-side; the stream then ends with a
    // quiet "— stopped —" line and whatever arrived stays.
    fetch("/api/chat/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: session }),
    }).catch(function () { /* nothing streaming: the line clears itself */ });
  });

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  }

  input.addEventListener("input", function () {
    updateSendState();
    autoGrow();
    // Typing is intent: the suggestion strip steps aside on the first
    // keystroke and returns when the input is empty again.
    if (input.value) hidePromptChips();
    else showPromptChips();
  });

  // --- prompt chips: quiet suggestions over a focused, EMPTY input ------
  // Context-aware one-tap asks, built with createElement + textContent.
  // They never steal focus and never shove the layout (the strip rises
  // gently, like the peek); a tap sends through the queue-aware door.
  // Keyboard-friendly: Tab reaches the chips (focusout's relatedTarget
  // keeps the strip open while focus stays in the tray), Enter sends.
  var promptChips = document.getElementById("prompt-chips");

  function chipSuggestions(view) {
    if (view) {
      return [
        "mark the moments in this talk",
        "make an interactive guide with jump-to links",
        "what should I listen for?"
      ];
    }
    return [
      "where are we on the path?",
      "what's next for me?",
      "play me something short"
    ];
  }

  function showPromptChips() {
    if (busy || input.value.trim()) return;
    while (promptChips.firstChild) promptChips.removeChild(promptChips.firstChild);
    chipSuggestions(currentView()).forEach(function (text) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "prompt-chip";
      chip.textContent = text;
      promptChips.appendChild(chip);
    });
    promptChips.hidden = false;
  }

  function hidePromptChips() {
    promptChips.hidden = true;
  }

  function chipFocusOut(event) {
    var next = event.relatedTarget;
    if (next === input || promptChips.contains(next)) return;
    hidePromptChips();
  }

  input.addEventListener("focus", showPromptChips);
  input.addEventListener("focusout", chipFocusOut);
  promptChips.addEventListener("focusout", chipFocusOut);
  promptChips.addEventListener("click", function (event) {
    var chip = event.target.closest(".prompt-chip");
    if (!chip) return;
    hidePromptChips();
    sendOrQueue(chip.textContent);
  });
  // A room change re-draws a visible strip in the new context.
  window.addEventListener("hashchange", function () {
    if (!promptChips.hidden) showPromptChips();
  });

  function setChatState(next) {
    chatState = next;
    panel.classList.remove("chat-docked", "chat-conversation");
    panel.classList.add("chat-" + next);
    // The capsule steps down under the minimize pill while talking.
    document.body.classList.toggle(
      "chat-conversation-mode", next === "conversation");
    if (window.saUpdateCapsule) window.saUpdateCapsule();
    if (next === "conversation") list.scrollTop = list.scrollHeight;
    if (next === "docked") maybeApplyPendingReload(); // a calm moment
  }

  document.getElementById("chat-open").addEventListener("click", function () {
    setChatState("conversation"); // open without sending
  });
  // System lines from the layout side (lock toggles, cue results).
  window.saAnnounce = function (line) { add("system", line); };

  // --- the peek: replies land in the room, not over it -------------------
  // Sending from docked no longer opens the overlay. The reply streams
  // into this compact strip above the bar, then settles into a
  // dismissible bubble (leaf mark, ~3 lines, "…more" opens the overlay).
  // It stays until dismissed, expanded, or the next message replaces it.
  var peek = document.getElementById("chat-peek");
  var peekText = document.getElementById("peek-text");
  var peekAction = document.getElementById("peek-action");
  (function () {
    var mark = document.getElementById("peek-mark");
    var tpl = document.getElementById("avatar-guide");
    if (tpl && tpl.content && tpl.content.firstElementChild) {
      mark.appendChild(tpl.content.firstElementChild.cloneNode(true));
    }
  })();

  function peekUpdate(text, done) {
    if (chatState !== "docked") { peek.hidden = true; return; }
    peek.hidden = false; // entrance: a gentle rise, CSS-side
    peek.classList.toggle("peek-settled", !!done);
    peekText.textContent = text;
  }

  document.getElementById("peek-body").addEventListener("click", function () {
    peek.hidden = true;
    setChatState("conversation"); // the full exchange, deliberately
  });
  document.getElementById("peek-dismiss").addEventListener("click", function () {
    peek.hidden = true;
  });

  // "✦ create interactive tools" — composes and SENDS the ask through
  // the one send path; the peek carries the build narrative from there.
  // Delegated, never per-button: the button also lives in rooms the
  // soft refresh swaps in later.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".make-interactive");
    if (!button) return;
    sendOrQueue("Please create interactive tools for "
      + JSON.stringify(button.getAttribute("data-title"))
      + " from its transcript and notes — remember I prefer listening-first.");
  });
  // "✦ ask the guide to mark the moments" — the Transcript block's
  // front layer when no moments exist yet, same queue-aware send.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".mark-moments");
    if (!button) return;
    sendOrQueue("Read this talk's transcript and mark 3-6 moments worth "
      + "returning to — write them under '## Moments' in the notes as "
      + "'- mm:ss — why', timestamps grounded in transcript.json, then "
      + "rebuild the shelf.");
  });
  // "✦ more like this" — with moments already marked, ask for a few
  // more; the ask itself forbids duplicates and keeps the grounding.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".more-moments");
    if (!button) return;
    sendOrQueue("Mark 2-3 MORE moments in this talk beyond the ones "
      + "already in '## Moments' — same format ('- mm:ss — why'), "
      + "no duplicates, grounded in transcript.json, then rebuild "
      + "the shelf.");
  });
  // "✦ ask the guide to write & speak a primer" — the empty Primer
  // section's generator: transcript → '## Primer' in notes → primer.mp3.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".make-primer");
    if (!button) return;
    sendOrQueue("Read this talk's transcript and write a 60-90 second "
      + "primer — who the teacher is, what to listen for — into the "
      + "notes under '## Primer', speak it to primer.mp3 with the "
      + "speak tool, then rebuild the shelf.");
  });
  // "✦ ask the guide to start notes for this talk" — the empty Notes
  // section's generator, same uniform pattern.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".make-notes");
    if (!button) return;
    sendOrQueue("Please start notes for this talk — a few lines on "
      + "what it covers and a '## My takeaways' section to grow, then "
      + "rebuild the shelf.");
  });
  // The stub rooms' one primary action: an explicit single-item fetch
  // (recording URL known) or a plain ask (reading/no URL) — both through
  // the queue-aware send, never silently dropped.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".fetch-stub");
    if (!button) return;
    sendOrQueue("Please fetch " + button.getAttribute("data-title")
      + " (" + button.getAttribute("data-teacher") + ") — curriculum URL "
      + button.getAttribute("data-url") + ". Single explicit download I'm "
      + "asking for; full ritual: probe and say what you found, verify the "
      + "transcript, notes with a short primer, speak it, update the path, "
      + "rebuild the shelf.");
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".ask-stub");
    if (!button) return;
    sendOrQueue("Tell me about " + button.getAttribute("data-title")
      + " on my path — what is it, and how should we approach it?");
  });
  // The optimistic sidebar flip for done (✓) and reopen (→): the entry
  // changes immediately; returns an undo for the failure path. The soft
  // refresh replaces the whole nav with the real state soon after.
  function markSidebarState(slug, css, glyph) {
    var link = document.querySelector('#talk-nav a[href="#talk/' + slug + '"]');
    if (!link || link.querySelector(".nav-state." + css)) return null;
    var old = link.querySelector(".nav-state");
    var mark = document.createElement("span");
    mark.className = "nav-state " + css;
    mark.textContent = glyph;
    if (old) link.replaceChild(mark, old);
    else link.insertBefore(mark, link.firstChild);
    return function () {
      if (!mark.parentNode) return; // a swap already brought the truth
      if (old) link.replaceChild(old, mark);
      else link.removeChild(mark);
    };
  }

  // A server-first card action: optimistic UI confirmed by the endpoint
  // (only a network/500 error reverts), the rebuilt page's mtime adopted
  // (so the version poll doesn't double-refresh), the room swapped in
  // place, and THEN the guide follow-up through the queue-aware send —
  // conversation follows the action instead of performing it.
  function serverFirstAction(button, api, workingLabel, followUp, undoMark) {
    button.disabled = true;
    var was = button.textContent;
    button.textContent = workingLabel;
    fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: button.getAttribute("data-slug") }),
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      if (typeof data.shelf_mtime === "number") shelfVersion = data.shelf_mtime;
      softRefresh().catch(function () { /* the poll catches up */ });
      sendOrQueue(followUp); // queued visibly when the guide is busy
    }).catch(function () {
      button.disabled = false; // network/500: quietly re-arm
      button.textContent = was;
      if (undoMark) undoMark();
    });
  }

  // "✓ Done with this talk" — server-first: POST /api/done records the
  // listen if absent, moves Queued → Studied on STUDY.md, and rebuilds —
  // instant, idempotent, no guide involved. The guide only gets the
  // what's-next conversation afterwards.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".done-for-now");
    if (!button || button.disabled) return;
    serverFirstAction(button, "/api/done", "✓ done — finding what's next…",
      "I'm done with " + button.getAttribute("data-title")
      + " for now — the shelf has already marked it done on the path. "
      + "What's next? If nothing unheard is left in the library, this "
      + "click is my explicit request to fetch the next talk from the "
      + "curriculum — let me know when it's ready.",
      markSidebarState(button.getAttribute("data-slug"), "nav-done", "✓"));
  });
  // "reopen — put it back on the path" — the exact inverse, same shape:
  // POST /api/reopen moves Studied → Queued instantly; the guide picks
  // the thread up in conversation.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".reopen-talk");
    if (!button || button.disabled) return;
    serverFirstAction(button, "/api/reopen", "reopening…",
      "I've reopened " + button.getAttribute("data-title")
      + " — pick it up with me when you're ready: what should we "
      + "look at again?",
      markSidebarState(button.getAttribute("data-slug"), "nav-next", "→"));
  });
  // "…or wrap it up together" — the heard card's quieter door into the
  // full wrap-up conversation, through the same send path.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".wrap-up-talk");
    if (!button) return;
    sendOrQueue("I've listened to " + button.getAttribute("data-title")
      + " to the end — let's wrap it up: ask me what landed, "
      + "then update the path.");
  });
  // "mark as heard" — the manual door when auto-completion didn't fire.
  // Same server path as the automatic report; the response carries the
  // rebuilt page's mtime (adopted BEFORE the poll sees it, so no reload),
  // and the soft refresh flips the sidebar mark and the card in place.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".mark-heard");
    if (!button || button.disabled) return;
    button.disabled = true;
    button.textContent = "marking…";
    fetch("/api/listened", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: button.getAttribute("data-slug") }),
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      if (typeof data.shelf_mtime === "number") shelfVersion = data.shelf_mtime;
      button.textContent = "heard ✓"; // instant, even in the playing room
      return softRefresh();
    }).catch(function () {
      button.disabled = false; // static shelf or a hiccup: quietly re-arm
      button.textContent = "mark as heard";
    });
  });
  // "mark unheard — come back to this" — the quiet inverse: an
  // append-only retraction server-side (latest entry wins), then the
  // card and sidebar flip back to not-heard in place. Done talks keep
  // their own reopen door; this button never appears on them.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".mark-unheard");
    if (!button || button.disabled) return;
    button.disabled = true;
    fetch("/api/unheard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: button.getAttribute("data-slug") }),
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      if (typeof data.shelf_mtime === "number") shelfVersion = data.shelf_mtime;
      return softRefresh();
    }).catch(function () {
      button.disabled = false; // static shelf or a hiccup: quietly re-arm
    });
  });
  // The now-playing capsule (its own closure) asks the chat to step
  // aside before it navigates to the playing talk's room.
  window.saDockChat = function () { setChatState("docked"); };
  document.getElementById("chat-minimize").addEventListener("click", function () {
    setChatState("docked"); // same as Escape: the page is exactly as left
  });
  setChatState("docked");

  // --- guide-offered navigation: a final-line [[go: ...]] cue -----------
  // The cue is ALWAYS stripped from display; only a final-line cue whose
  // target really exists on this page earns a "take me there" button.
  // --- action cues: the guide drives the same UI the user does ----------
  // Final-line only, always stripped from display, strictly validated:
  // [[go: talk/<slug>|curriculum|home]], [[seek: <slug> <seconds>]],
  // [[pause]], [[play]]. Seconds are capped by the talk's INDEX duration
  // when known. One action per reply; anything else is stripped silently.
  function parseActionCue(text) {
    var action = null;
    var match = text.match(/\\[\\[(go|seek|pause|play)(?::\\s*([^\\]]*?))?\\s*\\]\\]\\s*$/);
    if (match) {
      var kind = match[1];
      var arg = (match[2] || "").trim();
      if (kind === "pause" && !arg) action = { kind: "pause" };
      else if (kind === "play" && !arg) action = { kind: "play" };
      else if (kind === "go") {
        if (arg === "home") {
          action = { kind: "go", target: "#home", label: "the beginning" };
        } else if (arg === "curriculum"
            && document.getElementById("view-curriculum")) {
          action = { kind: "go", target: "#curriculum", label: "the curriculum" };
        } else {
          var talk = arg.match(/^talk\\/([a-z0-9][a-z0-9-]*)$/);
          if (talk && document.getElementById("talk-" + talk[1])) {
            action = { kind: "go", target: "#talk/" + talk[1], slug: talk[1] };
          }
        }
      } else if (kind === "seek") {
        var seek = arg.match(/^([a-z0-9][a-z0-9-]*)\\s+(\\d+(?:\\.\\d+)?)$/);
        if (seek) {
          var room = document.getElementById("talk-" + seek[1]);
          var seconds = parseFloat(seek[2]);
          var cap = room ? parseFloat(room.getAttribute("data-duration")) : NaN;
          if (room && (!cap || seconds <= cap)) {
            action = { kind: "seek", slug: seek[1], seconds: seconds };
          }
        }
      }
    }
    return {
      text: text.replace(/\\s*\\[\\[(?:go|seek|pause|play)[^\\]]*\\]\\]/g, "").trim(),
      action: action,
    };
  }

  function cueClock(seconds) {
    var total = Math.max(0, Math.floor(seconds || 0));
    var m = Math.floor(total / 60);
    var sec = total % 60;
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  // Locked mode: the same cue becomes an offer the user can take or leave.
  function offerAction(bubble, action) {
    var go = document.createElement("button");
    go.type = "button";
    go.className = "chat-go";
    var label = "the guide suggests it — go?";
    if (action.kind === "go") label = "the guide wants to take you somewhere — go?";
    if (action.kind === "seek") {
      label = "the guide wants to jump to " + cueClock(action.seconds) + " — go?";
    }
    if (action.kind === "pause") label = "the guide wants to pause — ok?";
    if (action.kind === "play") label = "the guide wants to press play — ok?";
    go.textContent = label;
    go.addEventListener("click", function () {
      var line = window.saExecuteCue ? window.saExecuteCue(action) : null;
      if (line) add("system", line);
    });
    bubble.appendChild(go);
  }

  // --- sticky selection: sa-brain / sa-route survive reloads ------------
  // The pick changes ONLY on the user's own click in settings; restores
  // that can't be honored fall back hermes→claude out loud, never
  // silently, and never overwrite the stored pick.
  function savedPick(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function storePick(key, value) {
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch (e) { /* storage blocked: the pick just doesn't persist */ }
  }

  function brainAvailable(name, brains) {
    if (name === "hermes") {
      var entry = brains.hermes;
      return !!(entry && typeof entry === "object" && entry.wired);
    }
    return brains[name] !== false;
  }

  // The one quiet line over the conversation: who answers, linking to
  // the settings room where that can change.
  function renderIdentity() {
    if (!healthInfo || !identityLink) return;
    var wired = brainAvailable("hermes", healthInfo.brains || {});
    if (brain === "hermes") {
      identityLink.textContent = "on Hermes · second-arrow";
    } else if (!wired) {
      identityLink.textContent = "on " + brain + " — hermes not wired";
    } else {
      identityLink.textContent = "on " + brain;
    }
    identityRow.hidden = false;
  }

  function currentView() {
    // The ambient context: the talk open on the shelf right now, or null.
    var match = location.hash.match(/^#talk\\/(.+)$/);
    return match ? match[1] : null;
  }

  function clearMessages() {
    while (list.firstChild) list.removeChild(list.firstChild);
    history.length = 0;
  }

  // The local-model picker (settings room, under the ollama row): visible
  // only while ollama is the picked brain and /api/models answered. The
  // select is re-queried per call — the soft refresh swaps the settings
  // room in whole, so no node reference may be held.
  function updateModelVisibility() {
    var picker = document.getElementById("chat-model");
    if (!picker) return;
    picker.hidden = brain !== "ollama" || picker.options.length === 0;
  }

  function fillModelPicker() {
    var picker = document.getElementById("chat-model");
    if (!picker) return;
    while (picker.firstChild) picker.removeChild(picker.firstChild);
    ((modelList && modelList.models) || []).forEach(function (item) {
      var option = document.createElement("option");
      option.value = item.name;
      option.textContent = item.name
        + (item.tools ? " · tools" : "")
        + " · " + item.size_gb + "GB";
      picker.appendChild(option);
    });
    if (model) picker.value = model;
    updateModelVisibility();
  }

  function loadModels() {
    fetch("/api/models").then(function (r) { return r.json(); }).then(function (data) {
      modelList = data;
      // Only adopt the server's current when it is really installed — a
      // default that is not must not ride along with requests.
      if (data.current && (data.models || []).some(function (item) {
        return item.name === data.current;
      })) model = data.current;
      fillModelPicker();
      renderMachinery(); // the card can now name the local model too
    }).catch(function () { /* ollama down or older server: picker stays hidden */ });
  }

  // --- the settings room: one choice, made of calm radio rows -----------
  // The guide's brain section lists the Hermes routes (picking one IS
  // picking hermes); the fallback section lists claude/ollama. Exactly
  // one row is checked across both groups. Rebuilt after every /health
  // read and every soft refresh — rows carry their own listeners.
  function pickRow(container, label, checked, disabled, onPick) {
    var row = document.createElement("label");
    row.className = "pick-row";
    var radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "guide-brain";
    radio.checked = checked;
    radio.disabled = !!disabled;
    radio.addEventListener("change", function () {
      if (radio.checked) onPick();
    });
    var text = document.createElement("span");
    text.textContent = label;
    row.appendChild(radio);
    row.appendChild(text);
    container.appendChild(row);
  }

  function pickBrain(name, route) {
    brain = name;
    storePick("sa-brain", name);
    if (name === "hermes") {
      hermesRoute = route || null;
      storePick("sa-route", hermesRoute);
    }
    var note = document.getElementById("fallback-note");
    if (note) {
      note.hidden = name === "hermes";
      if (name !== "hermes") {
        note.textContent =
          "the guide answers via " + name + " until you switch back";
      }
    }
    updateModelVisibility();
    renderIdentity();
  }

  function renderBrainPicker() {
    var routeBox = document.getElementById("route-rows");
    var fallbackBox = document.getElementById("fallback-rows");
    if (!routeBox || !fallbackBox || !healthInfo) return;
    while (routeBox.firstChild) routeBox.removeChild(routeBox.firstChild);
    while (fallbackBox.firstChild) fallbackBox.removeChild(fallbackBox.firstChild);
    var brains = healthInfo.brains || {};
    var wired = brainAvailable("hermes", brains);
    var wiredState = document.getElementById("hermes-wired-state");
    if (wiredState) {
      wiredState.textContent = wired
        ? "wired" + (hermes && hermes.model ? " · " + hermes.model : "")
        : "not wired";
    }
    var unwiredHelp = document.getElementById("hermes-unwired");
    if (unwiredHelp) unwiredHelp.hidden = wired;
    // "default" rides first: the profile's own model, no route alias.
    var routes = [{ alias: "", model: (hermes && hermes.model) || "" }]
      .concat((hermes && hermes.routes) || []);
    routes.forEach(function (route) {
      pickRow(routeBox,
        (route.alias || "default") + (route.model ? " · " + route.model : ""),
        brain === "hermes" && (hermesRoute || "") === route.alias,
        !wired,
        function () { pickBrain("hermes", route.alias); });
    });
    [
      { name: "claude", label: "claude · deep", off: brains.claude === false },
      { name: "ollama", label: "ollama · offline", off: brains.ollama === false }
    ].forEach(function (item) {
      pickRow(fallbackBox, item.label, brain === item.name, item.off,
        function () { pickBrain(item.name, null); });
    });
    var fallbackSection = document.getElementById("set-fallback");
    if (fallbackSection) fallbackSection.hidden = false;
    fillModelPicker();
  }

  // --- nightly prep: the ONE gateway job, three narrow controls ---------
  function renderPrep() {
    var section = document.getElementById("set-prep");
    var line = document.getElementById("prep-line");
    var controls = document.getElementById("prep-controls");
    if (!section || !line || !controls) return;
    section.hidden = false;
    fetch("/api/prep").then(function (r) { return r.json(); }).then(function (data) {
      if (!data.wired || !data.found) {
        line.textContent = data.wired
          ? "no nightly-prep job yet — install it: uv run tools/hermes_cron_setup.py"
          : "gateway not wired — the job sleeps until it is";
        controls.hidden = true;
        return;
      }
      var job = data.job || {};
      line.textContent = (job.schedule ? job.schedule + " · " : "")
        + (job.model ? job.model + " · " : "")
        + (job.enabled ? "on" : "paused");
      controls.hidden = false;
      document.getElementById("prep-pause").hidden = !job.enabled;
      document.getElementById("prep-resume").hidden = !!job.enabled;
    }).catch(function () {
      line.textContent = "the gateway did not answer";
      controls.hidden = true;
    });
  }

  // Delegated: the buttons live in the settings room, which the soft
  // refresh swaps in whole.
  document.addEventListener("click", function (event) {
    var button = event.target.closest(".prep-btn");
    if (!button || button.disabled) return;
    var action = button.id === "prep-run" ? "run"
      : (button.id === "prep-pause" ? "pause" : "resume");
    button.disabled = true;
    var feedback = document.getElementById("prep-feedback");
    fetch("/api/prep/" + action, { method: "POST" })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
          return data;
        });
      })
      .then(function () {
        if (feedback) {
          feedback.hidden = false;
          feedback.textContent = action === "run"
            ? "started — output lands under the profile's cron/output/"
            : (action === "pause"
              ? "paused — nothing runs until resumed"
              : "resumed — next run on schedule");
        }
        renderPrep(); // the fresh enabled/paused state
      })
      .catch(function (error) {
        if (feedback) {
          feedback.hidden = false;
          feedback.textContent = error.message;
        }
      })
      .finally(function () { button.disabled = false; });
  });

  // --- the room's machinery: a quiet read-only card in Settings ---------
  // Built from /health with createElement + textContent only. No secrets —
  // presence booleans and display names, honestly stated. Begin here keeps
  // one pointer line to it. Re-rendered after every soft-refresh swap.
  function machineryLine(listEl, label, value) {
    var item = document.createElement("li");
    var name = document.createElement("span");
    name.className = "machinery-name";
    name.textContent = label;
    var state = document.createElement("span");
    state.className = "machinery-state";
    state.textContent = value;
    item.appendChild(name);
    item.appendChild(state);
    listEl.appendChild(item);
  }

  function renderMachinery() {
    var listEl = document.getElementById("machinery-list");
    if (!listEl || !healthInfo) return;
    while (listEl.firstChild) listEl.removeChild(listEl.firstChild);
    var brains = healthInfo.brains || {};
    var h = brains.hermes;
    // Hermes leads: it is the guide's home harness.
    machineryLine(listEl, "hermes · second-arrow",
      (h && typeof h === "object" && h.wired)
        ? (h.model ? "wired · " + h.model : "wired") : "not wired");
    machineryLine(listEl, "claude · deep",
      brains.claude === false ? "not found" : "ready");
    machineryLine(listEl, "ollama · offline",
      brains.ollama === false ? "not running"
        : "ready" + (model ? " · " + model : ""));
    machineryLine(listEl, "aX presence",
      healthInfo.ax && healthInfo.ax.wired ? "wired" : "not set up");
    var prep = healthInfo.prep_cron;
    machineryLine(listEl, "nightly prep",
      prep && prep.installed_at
        ? (prep.schedule ? prep.schedule + " · " : "")
          + "installed " + String(prep.installed_at).slice(0, 10)
        : "not yet scheduled");
    var section = document.getElementById("set-machinery");
    if (section) section.hidden = false;
    var link = document.getElementById("machinery"); // begin-here's pointer
    if (link) link.hidden = false;
  }

  // Delegated: the settings swap replaces the select node itself.
  document.addEventListener("change", function (event) {
    var picker = event.target;
    if (!picker || picker.id !== "chat-model") return;
    model = picker.value;
    add("system", "— ollama model: " + model + " —");
  });

  // --- reflections from practice: consent-first hand-off ----------------
  // A learning tool may post {type:"second-arrow:reflection", name, prompt,
  // text} UP to the shelf. Identity is the mounted iframe's contentWindow
  // (the sandbox is a null origin, so origin can't identify it); the talk
  // slug comes from OUR data-slug, never from the message. The latest
  // reflection per talk waits in memory only, behind a quiet chip — the
  // click on that chip IS the consent that hands the words to the guide.
  var toolFrames = []; // {win, slug, name} — pushed as each frame mounts
  var reflections = {}; // slug -> {tool, text}, memory only
  var chip = document.getElementById("reflection-chip");
  var chipSend = document.getElementById("reflection-send");
  var chipDismiss = document.getElementById("reflection-dismiss");
  var chipSlug = null;

  function validReflection(data) {
    return !!data
      && typeof data === "object"
      && data.type === "second-arrow:reflection"
      && typeof data.name === "string" && data.name.length > 0
      && typeof data.prompt === "string" && data.prompt.length <= 300
      && typeof data.text === "string" && data.text.trim().length > 0
      && data.text.length <= 4000;
  }

  function validArtifactSeek(data, cap) {
    return !!data
      && typeof data === "object"
      && data.type === "second-arrow:seek"
      && typeof data.start === "number"
      && isFinite(data.start)
      && data.start >= 0
      && (data.label === undefined
          || (typeof data.label === "string" && data.label.length <= 80))
      && (!cap || data.start <= cap);
  }

  window.addEventListener("message", function (event) {
    var from = null;
    toolFrames.forEach(function (tool) {
      if (tool.win === event.source) from = tool;
    });
    if (!from) return; // only OUR mounted interactives speak here
    if (event.data && event.data.type === "second-arrow:seek") {
      // Anchored listening: a tool's "listen from 13:23" button. The
      // slug comes ONLY from OUR data-slug; execution rides the same
      // user-click path as a transcript line. The guide lock does not
      // apply — locks tie the GUIDE's hands, and an artifact button is
      // the user's own finger. No announcement: direct manipulation.
      var room = document.getElementById("talk-" + from.slug);
      var cap = room ? parseFloat(room.getAttribute("data-duration")) : NaN;
      if (!validArtifactSeek(event.data, cap)) return;
      if (window.saExecuteCue) {
        window.saExecuteCue({ kind: "seek", slug: from.slug,
          seconds: event.data.start });
      }
      return;
    }
    if (!validReflection(event.data)) return;
    // OUR mounted file name, not the message's claim, names the tool.
    reflections[from.slug] = { tool: from.name, text: event.data.text };
    chipSlug = from.slug;
    chipSend.textContent =
      "reflection from your practice — hand it to the guide?";
    chip.hidden = false; // quiet: no focus theft, never auto-sent
  });

  function dismissChip(forget) {
    if (forget && chipSlug) delete reflections[chipSlug];
    chipSlug = null;
    chip.hidden = true;
  }

  chipDismiss.addEventListener("click", function () { dismissChip(true); });

  chipSend.addEventListener("click", function () {
    var reflection = chipSlug && reflections[chipSlug];
    if (!reflection) return;
    var card = document.getElementById("talk-" + chipSlug);
    var heading = card && card.querySelector("h2");
    var title = heading ? heading.textContent : chipSlug;
    // Its own message — a draft in the input is never clobbered.
    sendOrQueue("From my practice in " + reflection.tool
      + ' on "' + title + '": ' + reflection.text);
    dismissChip(true);
  });

  // Served mode only: swap each artifact link for a sandboxed live view.
  // Wall 1 is the sandbox — "allow-scripts" ALONE (never the same-origin
  // grant), so the artifact runs as a null origin. Wall 2 is the
  // /artifacts/ route's no-network CSP. The static file:// shelf keeps
  // the plain links instead: a file:// iframe would have neither wall.
  // Scoped to a container so the soft refresh can mount exactly the
  // rooms it swapped in; an already-live item is never mounted twice.
  function mountArtifacts(root) {
    var scope = root || document;
    scope.querySelectorAll(".artifact-note").forEach(function (note) {
      note.hidden = true; // the live view replaces the explanation
    });
    scope.querySelectorAll(".artifact-item").forEach(function (item) {
      if (item.querySelector(".artifact-frame")) return; // already live
      var name = item.getAttribute("data-name");
      var frame = document.createElement("iframe");
      frame.setAttribute("sandbox", "allow-scripts");
      frame.setAttribute("loading", "lazy");
      frame.setAttribute("title", name);
      frame.setAttribute("src", "/artifacts/"
        + encodeURIComponent(item.getAttribute("data-slug"))
        + "/" + encodeURIComponent(name));
      frame.className = "artifact-frame";
      item.appendChild(frame);
      toolFrames.push({ // identity for reflections: this exact window
        win: frame.contentWindow,
        slug: item.getAttribute("data-slug"),
        name: name,
      });
    });
  }

  // Safe mini-markdown for COMPLETED guide bubbles: **bold**, *italic*,
  // `code` become real elements, built with createElement + textContent
  // only — the text is never parsed as HTML. Streaming stays plain text.
  function renderRich(el, text) {
    el.textContent = "";
    var pattern = /\\*\\*([^*\\n]+)\\*\\*|\\*([^*\\n]+)\\*|`([^`\\n]+)`/;
    var rest = text;
    var m;
    while ((m = rest.match(pattern))) {
      if (m.index > 0) {
        el.appendChild(document.createTextNode(rest.slice(0, m.index)));
      }
      var tag = m[1] !== undefined ? "strong" : (m[2] !== undefined ? "em" : "code");
      var node = document.createElement(tag);
      node.textContent = m[1] !== undefined ? m[1]
        : (m[2] !== undefined ? m[2] : m[3]);
      el.appendChild(node);
      rest = rest.slice(m.index + m[0].length);
    }
    if (rest) el.appendChild(document.createTextNode(rest));
  }

  // One continuous guide: on load, the current episode's recent turns
  // come back and the conversation simply continues — episodes are the
  // server's invisible memory compaction, never a visible boundary.
  function restoreHistory(sid) {
    var url = "/api/history"
      + (sid ? "?session=" + encodeURIComponent(sid) : "");
    return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
      clearMessages();
      if (data.session) session = data.session;
      (data.turns || []).forEach(function (turn) {
        if (turn.role !== "user" && turn.role !== "assistant") return;
        var div = add(turn.role === "user" ? "user" : "guide", turn.content);
        if (turn.role === "assistant") {
          // Stored turns keep the raw narrative; render them clean.
          renderRich(div, parseActionCue(cleanReply(turn.content)).text);
        }
        history.push({ role: turn.role, content: turn.content });
      });
    }).catch(function () { /* an older server has no /api/history */ });
  }

  fetch("/health").then(function (r) { return r.json(); }).then(function (h) {
    if (!h.ok) return;
    healthInfo = h;
    var brains = h.brains || {};
    hermes = (brains.hermes && typeof brains.hermes === "object")
      ? brains.hermes : null;
    // The server's request-time truth: hermes when wired, else claude.
    brain = h.default_brain || h.brain;
    // Sticky selection: restore the user's own pick. A pick whose brain
    // can't answer right now falls back hermes→claude OUT LOUD (one
    // quiet system line below) — sa-brain itself stays put, so the pick
    // returns by itself once its brain is back.
    var saved = savedPick("sa-brain");
    var fallbackNote = null;
    if (saved === "claude" || saved === "ollama" || saved === "hermes") {
      if (brainAvailable(saved, brains)) {
        brain = saved;
      } else {
        brain = brainAvailable("hermes", brains) ? "hermes" : "claude";
        fallbackNote = "— " + saved + " isn't reachable — using "
          + brain + " for now —";
      }
    }
    var savedRoute = savedPick("sa-route");
    if (savedRoute && hermes && (hermes.routes || []).some(function (route) {
      return route.alias === savedRoute;
    })) hermesRoute = savedRoute; // only a route the gateway still has
    renderIdentity();
    renderBrainPicker(); // the settings room's radio rows
    renderMachinery(); // the settings status card (+ begin-here pointer)
    renderPrep(); // the nightly-prep job, live from the gateway
    panel.hidden = false;
    var restored = restoreHistory(); // the conversation continues across reloads
    if (fallbackNote) {
      restored.then(function () { add("system", fallbackNote); });
    }
    loadModels(); // fill the local-model picker (served mode only)
    mountArtifacts(); // artifact links become sandboxed live views
  }).catch(function () { /* static file:// shelf — panel stays hidden */ });

  // --- the build narrative: progress lines out of the stream ------------
  // Both brains stream "— doing a thing… —" lines inline with the reply;
  // the page lifts complete ones out as centered system lines and keeps
  // the bubble text clean.
  function splitNarrative(raw) {
    var progress = [];
    var kept = [];
    var parts = raw.split("\\n");
    for (var i = 0; i < parts.length; i++) {
      if (/^— .+ —$/.test(parts[i].trim())) progress.push(parts[i].trim());
      else kept.push(parts[i]);
    }
    return {
      text: kept.join("\\n").replace(/\\n{3,}/g, "\\n\\n").trim(),
      progress: progress,
    };
  }

  function cleanReply(text) {
    return splitNarrative(text).text;
  }

  function addSystemBefore(refBubble, text) {
    var div = document.createElement("div");
    div.className = "chat-msg chat-system";
    div.textContent = text;
    var row = refBubble.closest(".chat-row") || refBubble;
    list.insertBefore(div, row);
    list.scrollTop = list.scrollHeight;
  }

  // A soft working dot on the sidebar entry the narrative mentions
  // (else on the Talks heading) — the room feels alive while the guide
  // builds. Page-side only.
  function clearPulse() {
    document.querySelectorAll(".working").forEach(function (el) {
      el.classList.remove("working");
    });
  }

  function pulseSidebar(narrative) {
    clearPulse();
    var hay = (narrative || "").toLowerCase();
    var target = document.getElementById("talks-heading");
    document.querySelectorAll("#talk-nav a").forEach(function (link) {
      var title = link.querySelector(".nav-title");
      var slug = (link.getAttribute("href") || "").slice(6);
      if ((title && title.textContent
            && hay.indexOf(title.textContent.toLowerCase()) !== -1)
          || (slug && hay.indexOf(slug) !== -1)) {
        target = link;
      }
    });
    if (target) target.classList.add("working");
  }

  // --- the shelf refreshes itself when new content lands ----------------
  // Safe moments reload outright (resume positions + history make that
  // cheap). Unsafe moments — mid-listen, mid-conversation, mid-draft —
  // get a soft refresh instead: the fresh page is fetched and swapped in
  // place, never touching the playing room or this tray. Only when even
  // that fails does the change wait (pendingReload + the chip) for the
  // next calm moment.
  var freshChip = document.getElementById("fresh-chip");
  var shelfVersion = null;
  var pendingReload = false; // new content waiting for a calm moment

  function reloadIsSafe(playing, state, draft) {
    return !playing && state === "docked" && !draft.trim();
  }

  function maybeApplyPendingReload() {
    if (!pendingReload) return;
    var playing = window.saIsPlaying ? window.saIsPlaying() : false;
    if (reloadIsSafe(playing, chatState, input.value)) location.reload();
  }

  // Best effort: folds stay as the reader left them across a swap.
  function carryDetails(oldView, newView) {
    var before = oldView.querySelectorAll("details");
    var after = newView.querySelectorAll("details");
    before.forEach(function (fold, i) {
      if (after[i]) after[i].open = fold.open;
    });
  }

  // Swap the fresh page in under the reader: the sidebar path and every
  // room EXCEPT the one holding the playing player (its embed must never
  // blink). DOM import/replace only — nothing is ever parsed as markup
  // in place. Returns false when the fetched page doesn't look like the
  // shelf.
  function swapShelf(doc) {
    var container = document.getElementById("views");
    var newViews = doc.getElementById("views");
    if (!container || !newViews) return false;
    var newNav = doc.getElementById("talk-nav");
    var oldNav = document.getElementById("talk-nav");
    if (newNav && oldNav) {
      oldNav.replaceWith(document.importNode(newNav, true));
    }
    var playingSlug = window.saPlayingSlug ? window.saPlayingSlug() : null;
    var keep = playingSlug ? "talk-" + playingSlug : null;
    var freshIds = {};
    var swapped = [];
    Array.prototype.slice.call(newViews.children).forEach(function (view) {
      if (!view.classList.contains("view") || !view.id) return;
      freshIds[view.id] = true;
      if (view.id === keep) return; // the playing room is untouchable
      var node = document.importNode(view, true);
      var old = document.getElementById(view.id);
      if (old) {
        carryDetails(old, node);
        old.replaceWith(node);
      } else {
        container.appendChild(node); // a brand-new room
      }
      swapped.push(node);
    });
    Array.prototype.slice.call(container.children).forEach(function (view) {
      if (!view.classList.contains("view")) return;
      if (view.id === keep || freshIds[view.id]) return;
      container.removeChild(view); // gone from the shelf
    });
    swapped.forEach(function (node) {
      if (window.saBindRoom) window.saBindRoom(node); // wiring back
      if (!panel.hidden) mountArtifacts(node); // served: live tool views
    });
    // A swapped-in settings/home room arrives as its static skeleton:
    // refill the radio rows, the machinery card, and the prep controls.
    renderBrainPicker();
    renderMachinery();
    renderPrep();
    if (window.saShowView) window.saShowView(); // active room, nav marks
    return true;
  }

  function softRefresh() {
    return fetch(location.pathname, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var x = window.scrollX;
        var y = window.scrollY;
        if (!swapShelf(doc)) throw new Error("nothing to swap");
        window.scrollTo(x, y); // best effort: stay where the reader was
      });
  }

  function checkVersion() {
    fetch("/api/version").then(function (r) { return r.json(); }).then(function (data) {
      if (typeof data.shelf_mtime !== "number") return;
      if (shelfVersion === null) { shelfVersion = data.shelf_mtime; return; }
      if (data.shelf_mtime === shelfVersion) {
        maybeApplyPendingReload(); // an earlier change may apply now
        return;
      }
      shelfVersion = data.shelf_mtime;
      var playing = window.saIsPlaying ? window.saIsPlaying() : false;
      if (reloadIsSafe(playing, chatState, input.value)) {
        location.reload(); // resume positions + history make this cheap
        return;
      }
      softRefresh().then(function () {
        pendingReload = false; // the page IS current — nothing waits
        freshChip.hidden = true;
      }).catch(function () {
        pendingReload = true; // apply at the next calm moment instead
        freshChip.hidden = false; // with the chip as the manual door
      });
    }).catch(function () { /* static shelf: nothing to poll */ });
  }

  freshChip.addEventListener("click", function () {
    pendingReload = false; // this reload IS the application
    location.reload();
  });
  setInterval(function () {
    if (!document.hidden) checkVersion(); // poll only while visible
  }, 8000);
  checkVersion(); // baseline mtime

  function sendMessage(text) {
    if (!text || busy) return null;
    add("user", text);
    history.push({ role: "user", content: text });
    var pending = add("guide", "thinking…");
    pending.classList.add("chat-thinking");
    var shownProgress = 0;
    var failed = false; // callers may await the outcome (e.g. Done-for-now)
    while (peekAction.firstChild) peekAction.removeChild(peekAction.firstChild);
    if (chatState === "docked") peekUpdate("thinking…"); // stay in the room
    busy = true;
    setWorking("the guide is thinking…"); // visible for the whole turn
    updateSendState();
    return fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: history, brain: brain,
        session: session, view: currentView(),
        model: brain === "ollama" ? model
          : (brain === "hermes" ? hermesRoute : null)
      })
    }).then(function (r) {
      var sid = r.headers.get("X-Session");
      if (sid) session = sid; // the session that recorded this turn
      var type = r.headers.get("content-type") || "";
      if (!r.ok || type.indexOf("application/json") !== -1) {
        // pre-stream failure: the server still answers with JSON {error}.
        // (A JSON {reply} from an older non-streaming server also works.)
        return r.json().then(function (data) {
          if (r.ok && data.reply) return data.reply;
          throw new Error(data.error || "HTTP " + r.status);
        });
      }
      // The reply streams as chunked plain text: append each decoded
      // chunk as it arrives. textContent only — replies stay inert text.
      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var reply = "";
      function pump() {
        return reader.read().then(function (step) {
          var chunk = decoder.decode(step.done ? new Uint8Array() : step.value,
                                     { stream: !step.done });
          if (chunk) {
            if (!reply) {
              pending.classList.remove("chat-thinking");
              pending.textContent = "";
            }
            reply += chunk;
            var flowing = splitNarrative(reply);
            while (shownProgress < flowing.progress.length) {
              addSystemBefore(pending, flowing.progress[shownProgress]);
              shownProgress += 1;
              pulseSidebar(reply);
              // The working line carries the latest tool progress.
              setWorking(flowing.progress[shownProgress - 1]);
            }
            pending.textContent = flowing.text;
            if (chatState === "docked") {
              peekUpdate(flowing.text
                || flowing.progress[flowing.progress.length - 1] || "…");
            }
            list.scrollTop = list.scrollHeight;
          }
          return step.done ? reply : pump();
        });
      }
      return pump();
    }).then(function (reply) {
      pending.classList.remove("chat-thinking");
      if (!reply) {
        pending.textContent = "The guide said nothing — try again.";
        peekUpdate(pending.textContent, true);
        return;
      }
      var cue = parseActionCue(cleanReply(reply));
      renderRich(pending, cue.text); // bubble completed: dress the markdown
      peekUpdate(cue.text, true); // the peek settles into its bubble
      if (cue.action) {
        if (window.saCueLocked && window.saCueLocked()) {
          offerAction(pending, cue.action); // locked: offer, never act
          if (chatState === "docked") {
            offerAction(peekAction, cue.action); // visible where the user is
          }
        } else if (window.saExecuteCue) {
          var line = window.saExecuteCue(cue.action);
          if (line) add("system", line);
        }
      }
      history.push({ role: "assistant", content: reply });
    }).catch(function (error) {
      failed = true;
      pending.classList.remove("chat-thinking");
      pending.textContent = "The guide is out of reach — " + error.message;
      peekUpdate(pending.textContent, true);
    }).finally(function () {
      busy = false;
      clearPulse();
      setWorking(null);
      updateSendState();
      checkVersion(); // fresh content may have just landed
      input.focus({ preventScroll: true });
      if (queuedMessage) {
        // The queue empties the moment the turn ends — never dropped.
        var next = queuedMessage;
        queuedMessage = null;
        renderQueuedNote();
        sendMessage(next);
      }
    }).then(function () {
      return !failed; // the outcome, for optimistic callers to settle on
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    updateSendState();
    autoGrow();
    sendOrQueue(text); // busy queues it visibly, never a silent drop
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
    if (event.key === "Escape") {
      if (chatState !== "docked") {
        setChatState("docked"); // back to the page, exactly as it was
        return;
      }
      input.blur(); // keys go back to the page: space scrolls, players work
    }
  });

  // typing is intent, never steal: a printable key pressed while nothing
  // else owns the keyboard lands in the guide's textarea. "/" focuses
  // without inserting itself. Anything focusable — inputs, selects, the
  // players, the sandboxed learning tools (their own windows entirely) —
  // keeps its keys; space stays with the page for scrolling.
  document.addEventListener("keydown", function (event) {
    if (panel.hidden || event.metaKey || event.ctrlKey || event.altKey) return;
    var target = event.target;
    if (target !== document.body && target !== document.documentElement) return;
    if (event.key === "Escape" && chatState !== "docked") {
      setChatState("docked");
      return;
    }
    if (event.key === "/") {
      event.preventDefault(); // focus without the slash
      input.focus({ preventScroll: true });
      return;
    }
    if (event.key.length === 1 && event.key !== " ") {
      // Never move the viewport: the text lands in the pinned input,
      // visible peripherally; the user keeps reading what they read.
      input.focus({ preventScroll: true });
    }
  });
})();
</script>"""


# Hash routing, the sidebar toggle, and the listening room: click-to-load
# YouTube players (thumbnail or button placeholder), resume positions
# (localStorage only — sa-pos-<slug>, never sent to any server), and the
# transcript player (click a segment to seek; local audio highlights the
# current segment). Views are hidden only under the runtime "js" class:
# with JS off, everything still renders stacked. Iframes are built with
# createElement + setAttribute — no third-party request until asked.
LAYOUT_SCRIPT = """<script>
(function () {
  var sidebar = document.getElementById("sidebar");
  var toggle = document.getElementById("sidebar-toggle");
  document.body.classList.add("js"); // hiding starts here, never in the HTML

  function show() {
    var hash = location.hash || "#home";
    var id = "view-home";
    if (hash.indexOf("#talk/") === 0) id = "talk-" + hash.slice(6);
    else if (hash === "#curriculum") id = "view-curriculum";
    else if (hash === "#settings") id = "view-settings";
    if (!document.getElementById(id)) id = "view-home"; // unknown hash: go home
    // Queried live, never cached: the soft refresh swaps rooms and the
    // sidebar path in and out under this router.
    document.querySelectorAll(".view").forEach(function (view) {
      view.classList.toggle("active", view.id === id);
    });
    document.querySelectorAll("#talk-nav a").forEach(function (link) {
      link.classList.toggle("active", link.getAttribute("href") === hash);
    });
    keepPlayingViewAlive(); // the playing talk's embed survives the switch
  }
  window.addEventListener("hashchange", show);
  show();

  toggle.addEventListener("click", function () {
    sidebar.classList.toggle("open");
  });

  // Desktop collapser: a slim chevron folds the sidebar away and a
  // floating one brings it back; the choice persists. The tray never
  // moves relative to the viewport bottom through any of it.
  function setSidebarCollapsed(collapsed) {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    try {
      if (collapsed) localStorage.setItem("sa-sidebar", "collapsed");
      else localStorage.removeItem("sa-sidebar");
    } catch (e) { /* storage blocked: the choice just doesn't persist */ }
  }
  document.getElementById("sidebar-collapse").addEventListener(
    "click", function () { setSidebarCollapsed(true); });
  document.getElementById("sidebar-reopen").addEventListener(
    "click", function () { setSidebarCollapsed(false); });
  try {
    if (localStorage.getItem("sa-sidebar") === "collapsed") {
      setSidebarCollapsed(true);
    }
  } catch (e) { /* fresh page each time is fine */ }
  // Delegated: the soft refresh replaces the nav list whole.
  sidebar.addEventListener("click", function (event) {
    if (event.target.closest("#talk-nav a")) {
      sidebar.classList.remove("open"); // narrow screens: picking closes it
      if (document.body.classList.contains("chat-conversation-mode")
          && window.saDockChat) {
        window.saDockChat(); // browsing wins: back to the room
      }
    }
  });

  // --- resume positions: localStorage only, never sent anywhere --------
  function posKey(slug) { return "sa-pos-" + slug; }

  function loadPos(slug) {
    try {
      var value = parseFloat(localStorage.getItem(posKey(slug)));
      return isNaN(value) ? 0 : value;
    } catch (e) { return 0; }
  }

  function savePos(slug, t, duration) {
    if (duration && duration - t < 15) {
      reportListened(slug); // within a breath of the end counts
    }
    try {
      if (duration && duration - t < 15) localStorage.removeItem(posKey(slug));
      else if (t > 1) localStorage.setItem(posKey(slug), String(Math.floor(t)));
    } catch (e) { /* storage blocked: resume is a nicety */ }
  }

  // --- the transcript player: click a segment, be there -----------------
  function highlightSegment(slug, t) {
    var box = document.querySelector('.seg-transcript[data-slug="' + slug + '"]');
    if (!box) return;
    var details = box.closest("details");
    if (details && !details.open) return; // gentle: only while it's open
    var active = null;
    box.querySelectorAll(".seg").forEach(function (seg) {
      if (parseFloat(seg.getAttribute("data-start")) <= t) active = seg;
    });
    box.querySelectorAll(".seg").forEach(function (seg) {
      seg.classList.toggle("active", seg === active);
    });
    if (active && box.getAttribute("data-active") !== active.getAttribute("data-start")) {
      box.setAttribute("data-active", active.getAttribute("data-start"));
      active.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  function seekAudio(audio, t) {
    audio.setAttribute("data-restored", "1"); // an explicit seek wins
    if (audio.readyState >= 1) {
      audio.currentTime = t;
    } else {
      audio.addEventListener("loadedmetadata", function once() {
        audio.removeEventListener("loadedmetadata", once);
        audio.currentTime = t;
      });
    }
    audio.play();
  }

  // ONE seek path — the transcript click and the guide's seek cue both
  // land here (no new machinery for the guide's hands).
  function seekTalk(slug, start) {
    var audio = document.querySelector(
      'audio.talk-audio[data-slug="' + slug + '"]');
    if (audio) { seekAudio(audio, start); return true; }
    var holder = document.querySelector(
      '.yt-embed[data-slug="' + slug + '"]');
    // No API dependency: seeking a YouTube talk just reloads the
    // embed at that second.
    if (holder) { mountFrame(holder, Math.floor(start)); return true; }
    return false;
  }

  // --- now playing: one voice, one visible handle ------------------------
  // Views hide, they never unmount — so a talk keeps playing across room
  // changes and chat states. The capsule is its handle: visible whenever
  // a talk is playing (or paused midway) and its own room is not on
  // screen; above the conversation overlay; never near the input row.
  var ytFrames = {}; // slug -> mounted iframe (for command postMessages)
  var nowPlaying = null; // {slug, kind, title, time, playing, ytInfo}
  var capsule = document.getElementById("now-playing");
  var npBody = document.getElementById("np-body");
  var npThumb = document.getElementById("np-thumb");
  var npGlyph = document.getElementById("np-glyph");
  var npTitle = document.getElementById("np-title");
  var npTime = document.getElementById("np-time");
  var npPlay = document.getElementById("np-play");
  var npStop = document.getElementById("np-stop");
  var npExpand = document.getElementById("np-expand");

  function npClock(seconds) {
    var total = Math.max(0, Math.floor(seconds || 0));
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var sec = total % 60;
    var mm = (h && m < 10 ? "0" : "") + m;
    return (h ? h + ":" : "") + mm + ":" + (sec < 10 ? "0" : "") + sec;
  }

  function ytCommand(slug, func, args) {
    var frame = ytFrames[slug];
    if (!frame) return;
    try {
      frame.contentWindow.postMessage(JSON.stringify(
        { event: "command", func: func, args: args || [] }),
        "https://www.youtube-nocookie.com");
    } catch (e) { /* mute channel: the capsule still navigates */ }
  }

  // --- completion: tell the shelf a talk finished ------------------------
  var reportedListened = {}; // one POST per talk per page load
  function reportListened(slug) {
    if (reportedListened[slug]) return;
    reportedListened[slug] = true;
    fetch("/api/listened", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: slug }),
    }).catch(function () { /* static shelf: the server remembers next time */ });
  }

  function pauseOthers(slug) {
    // One voice at a time: whoever starts, everyone else goes quiet.
    document.querySelectorAll("audio.talk-audio").forEach(function (audio) {
      if (audio.getAttribute("data-slug") !== slug && !audio.paused) {
        audio.pause(); // position is saved by the resume feature
      }
    });
    Object.keys(ytFrames).forEach(function (other) {
      if (other !== slug) ytCommand(other, "pauseVideo");
    });
  }

  function setNowPlaying(slug, kind) {
    var heading = document.querySelector("#talk-" + slug + " h2");
    nowPlaying = {
      slug: slug,
      kind: kind,
      title: heading ? heading.textContent : slug,
      time: 0,
      playing: true,
      ytInfo: false,
    };
    var art = document.querySelector("#talk-" + slug + " .yt-thumb img");
    npThumb.hidden = !art;
    npGlyph.hidden = !!art;
    if (art) npThumb.setAttribute("src", art.getAttribute("src"));
    updateCapsule();
    keepPlayingViewAlive();
    updateRoomLocks();
  }

  function capsuleVisible(playing, hash, conversationMode) {
    if (!playing) return false;
    // With the conversation covering the page, even the talk's own room
    // is out of sight — the handle must be there.
    if (conversationMode) return true;
    // Otherwise only its own visible room makes the handle redundant.
    return hash !== "#talk/" + playing.slug;
  }

  function updateCapsule() {
    capsule.hidden = !capsuleVisible(
      nowPlaying,
      location.hash,
      document.body.classList.contains("chat-conversation-mode"));
    if (capsule.hidden) return;
    npTitle.textContent = nowPlaying.title;
    npTime.textContent = npClock(nowPlaying.time);
    npPlay.textContent = nowPlaying.playing ? "❚❚" : "▶";
    // A YouTube channel that never delivered info can't be trusted with
    // a toggle — hide it rather than show a control that may not work.
    npPlay.hidden = nowPlaying.kind === "yt" && !nowPlaying.ytInfo;
  }

  function goToNowPlaying() {
    if (!nowPlaying) return;
    // Chat steps aside FIRST, so the room (and the still-playing video)
    // is visible the moment the hash lands.
    if (window.saDockChat) window.saDockChat();
    location.hash = "#talk/" + nowPlaying.slug;
    updateCapsule();
  }
  npBody.addEventListener("click", goToNowPlaying);
  npExpand.addEventListener("click", goToNowPlaying);

  // --- the lock: the guide's hands can be tied ---------------------------
  // Locked, action cues become offer-buttons instead of executing. The
  // padlock lives on the capsule and (for the playing talk only) in the
  // room header; the choice persists.
  var guideLock = false;
  try { guideLock = localStorage.getItem("sa-guide-lock") === "1"; } catch (e) {}
  window.saCueLocked = function () { return guideLock; };

  function applyLockUI() {
    document.querySelectorAll(".guide-lock").forEach(function (button) {
      button.textContent = guideLock ? "🔒" : "🔓";
      button.classList.toggle("locked", guideLock);
      button.setAttribute("title", guideLock
        ? "guide navigation locked — cues become offers"
        : "guide navigation unlocked — the guide may drive");
    });
  }

  function setGuideLock(locked) {
    guideLock = locked;
    try {
      if (locked) localStorage.setItem("sa-guide-lock", "1");
      else localStorage.removeItem("sa-guide-lock");
    } catch (e) { /* storage blocked: the choice just doesn't persist */ }
    applyLockUI();
    if (window.saAnnounce) {
      window.saAnnounce(locked
        ? "— guide navigation locked —"
        : "— guide navigation unlocked —");
    }
  }

  applyLockUI(); // reflect the persisted choice, silently

  function updateRoomLocks() {
    document.querySelectorAll(".room-lock").forEach(function (button) {
      button.hidden = !nowPlaying
        || button.getAttribute("data-slug") !== nowPlaying.slug;
    });
  }

  // --- the guide's hands: execute a validated cue -------------------------
  // Everything runs through the user's own click paths (seekTalk,
  // mountFrame, setPlayback, hash navigation) — no new machinery.
  window.saExecuteCue = function (action) {
    if (!action) return null;
    if (action.kind === "go") {
      if (window.saDockChat) window.saDockChat();
      location.hash = action.target;
      var label = action.label;
      if (!label) {
        var heading = document.querySelector("#talk-" + action.slug + " h2");
        label = heading ? heading.textContent : action.slug;
      }
      return "— the guide took you to " + label + " —";
    }
    if (action.kind === "seek") {
      var playingHere = nowPlaying && nowPlaying.slug === action.slug;
      if (!playingHere && location.hash !== "#talk/" + action.slug) {
        if (window.saDockChat) window.saDockChat();
        location.hash = "#talk/" + action.slug; // its room, then the moment
      }
      if (playingHere && nowPlaying.kind === "yt" && nowPlaying.ytInfo) {
        ytCommand(action.slug, "seekTo", [action.seconds, true]);
      } else {
        seekTalk(action.slug, action.seconds);
      }
      return "— the guide jumped to " + npClock(action.seconds) + " —";
    }
    if (action.kind === "pause" || action.kind === "play") {
      if (!setPlayback(action.kind === "play")) return "— nothing is playing —";
      return action.kind === "play"
        ? "— the guide pressed play —" : "— the guide paused —";
    }
    return null;
  };

  // ONE playback switch — the capsule button and the guide's pause/play
  // cues both use it.
  function setPlayback(playing) {
    if (!nowPlaying) return false;
    if (nowPlaying.kind === "audio") {
      var audio = document.querySelector(
        'audio.talk-audio[data-slug="' + nowPlaying.slug + '"]');
      if (!audio) return false;
      if (playing) audio.play(); else audio.pause();
      return true;
    }
    ytCommand(nowPlaying.slug, playing ? "playVideo" : "pauseVideo");
    nowPlaying.playing = playing; // infoDelivery corrects us
    updateCapsule();
    return true;
  }

  npPlay.addEventListener("click", function () {
    if (nowPlaying) setPlayback(!nowPlaying.playing);
  });

  npStop.addEventListener("click", function () {
    if (!nowPlaying) return;
    if (nowPlaying.kind === "audio") {
      var audio = document.querySelector(
        'audio.talk-audio[data-slug="' + nowPlaying.slug + '"]');
      if (audio) audio.pause();
    } else {
      // Pause, never reload or destroy the iframe — resume keeps the place.
      ytCommand(nowPlaying.slug, "pauseVideo");
    }
    nowPlaying = null;
    updateCapsule();
    keepPlayingViewAlive();
    updateRoomLocks();
  });

  window.addEventListener("hashchange", updateCapsule);
  // The chat panel (its own closure) calls this when conversation mode
  // opens or closes, so the capsule appears the moment the room is covered.
  window.saUpdateCapsule = updateCapsule;
  window.saIsPlaying = function () { return !!nowPlaying; };

  // Navigation must never interrupt playback. Hiding an iframe with
  // display:none lets YouTube stop the video, so the actively-playing
  // talk's view is parked offscreen instead — still rendered, no layout
  // footprint, pointer-inert. Only that one view, only while it plays.
  function keepPlayingViewAlive() {
    document.querySelectorAll(".view.audible").forEach(function (view) {
      view.classList.remove("audible");
    });
    if (!nowPlaying || nowPlaying.kind !== "yt") return;
    var view = document.getElementById("talk-" + nowPlaying.slug);
    if (view && !view.classList.contains("active")) {
      view.classList.add("audible");
    }
  }

  // --- local audio: restore, track, highlight ---------------------------
  function bindAudio(audio) {
    var slug = audio.getAttribute("data-slug");
    var lastSave = 0;
    audio.addEventListener("loadedmetadata", function () {
      if (audio.getAttribute("data-restored")) return;
      audio.setAttribute("data-restored", "1");
      var saved = loadPos(slug);
      if (saved > 0 && saved < audio.duration - 15) audio.currentTime = saved;
    });
    audio.addEventListener("timeupdate", function () {
      highlightSegment(slug, audio.currentTime);
      if (nowPlaying && nowPlaying.slug === slug) {
        nowPlaying.time = audio.currentTime;
        updateCapsule();
      }
      var now = Date.now();
      if (now - lastSave < 5000) return; // throttled
      lastSave = now;
      savePos(slug, audio.currentTime, audio.duration);
    });
    audio.addEventListener("play", function () {
      pauseOthers(slug);
      if (!nowPlaying || nowPlaying.slug !== slug) setNowPlaying(slug, "audio");
      nowPlaying.playing = true;
      nowPlaying.time = audio.currentTime;
      updateCapsule();
    });
    audio.addEventListener("pause", function () {
      if (nowPlaying && nowPlaying.slug === slug) {
        nowPlaying.playing = false; // paused midway: the handle stays
        updateCapsule();
      }
    });
    audio.addEventListener("ended", function () {
      reportListened(slug); // it played to the end
      if (nowPlaying && nowPlaying.slug === slug) {
        nowPlaying = null;
        updateCapsule();
        keepPlayingViewAlive();
      }
    });
  }

  // --- YouTube embeds: click-to-load, resume via &start=, jsapi track ---
  var ytMounted = {}; // slug -> true once its iframe exists
  var ytLastSave = {};

  function mountFrame(holder, startAt) {
    var slug = holder.getAttribute("data-slug");
    var src = holder.getAttribute("data-embed") + "?autoplay=1&enablejsapi=1";
    if (location.protocol === "http:" || location.protocol === "https:") {
      src += "&origin=" + encodeURIComponent(location.origin);
    }
    var at = startAt !== undefined ? startAt : Math.floor(loadPos(slug));
    if (at > 0) src += "&start=" + at; // resumes even if the API stays mute
    var frame = document.createElement("iframe");
    frame.setAttribute("src", src);
    frame.setAttribute("title", "YouTube player");
    frame.setAttribute("allow", "accelerometer; autoplay; clipboard-write; "
      + "encrypted-media; gyroscope; picture-in-picture; web-share");
    frame.setAttribute("allowfullscreen", "");
    frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    frame.addEventListener("load", function () {
      // The standard listening handshake: the player then streams
      // infoDelivery events (currentTime) back — no SDK script needed.
      try {
        frame.contentWindow.postMessage(JSON.stringify(
          { event: "listening", id: slug, channel: "widget" }),
          "https://www.youtube-nocookie.com");
      } catch (e) { /* degrade: the &start= above already resumed us */ }
    });
    ytMounted[slug] = true;
    ytFrames[slug] = frame;
    pauseOthers(slug); // one voice: the new talk takes over
    setNowPlaying(slug, "yt"); // autoplay: playing until told otherwise
    var box = document.createElement("div");
    box.className = "yt-frame";
    box.appendChild(frame);
    var old = holder.querySelector(".yt-frame") || holder.querySelector(".yt-play");
    if (old) holder.replaceChild(box, old);
  }

  window.addEventListener("message", function (event) {
    if (event.origin !== "https://www.youtube-nocookie.com"
        && event.origin !== "https://www.youtube.com") return;
    var data;
    try { data = JSON.parse(event.data); } catch (e) { return; }
    if (!data || data.event !== "infoDelivery" || !data.info) return;
    var slug = data.id;
    if (!ytMounted[slug] || typeof data.info.currentTime !== "number") return;
    if (data.info.playerState === 0
        || (data.info.duration
            && data.info.currentTime >= data.info.duration * 0.98)) {
      reportListened(slug); // ended, or within 2% of it
    }
    if (nowPlaying && nowPlaying.slug === slug) {
      nowPlaying.ytInfo = true; // the command channel is alive
      nowPlaying.time = data.info.currentTime;
      if (typeof data.info.playerState === "number") {
        nowPlaying.playing = data.info.playerState === 1;
      }
      updateCapsule();
    }
    highlightSegment(slug, data.info.currentTime);
    var now = Date.now();
    if (now - (ytLastSave[slug] || 0) < 5000) return; // throttled
    ytLastSave[slug] = now;
    savePos(slug, data.info.currentTime, data.info.duration);
  });

  // --- one wiring point per room -----------------------------------------
  // Every per-element binding lives here, scoped to a container, so the
  // chat side's soft refresh can rebind exactly the rooms it swapped in
  // (window.saBindRoom). Page load wires the whole document once.
  function bindRoom(root) {
    root.querySelectorAll(".seg-transcript").forEach(function (box) {
      box.addEventListener("click", function (event) {
        var seg = event.target.closest(".seg");
        if (!seg) return;
        seekTalk(box.getAttribute("data-slug"),
          parseFloat(seg.getAttribute("data-start")) || 0);
      });
    });
    // "Listen for" chips: the guide's curated moments seek exactly like
    // a transcript-line click — the same ONE seek path.
    root.querySelectorAll(".moments").forEach(function (box) {
      box.addEventListener("click", function (event) {
        var chip = event.target.closest(".moment-chip");
        if (!chip) return;
        seekTalk(box.getAttribute("data-slug"),
          parseFloat(chip.getAttribute("data-start")) || 0);
      });
    });
    root.querySelectorAll(".listened-replay").forEach(function (button) {
      button.addEventListener("click", function () {
        var slug = button.getAttribute("data-slug");
        var audio = document.querySelector(
          'audio.talk-audio[data-slug="' + slug + '"]');
        if (audio) { audio.play(); return; }
        var holder = document.querySelector(
          '.yt-embed[data-slug="' + slug + '"]');
        if (holder) mountFrame(holder, 0);
      });
    });
    root.querySelectorAll(".guide-lock").forEach(function (button) {
      button.addEventListener("click", function () { setGuideLock(!guideLock); });
    });
    root.querySelectorAll("audio.talk-audio").forEach(bindAudio);
    root.querySelectorAll(".yt-embed").forEach(function (holder) {
      var button = holder.querySelector(".yt-play");
      if (!button) return;
      button.addEventListener("click", function () { mountFrame(holder); });
    });
  }
  bindRoom(document);

  // The chat side's soft refresh hands each swapped-in room through here.
  window.saBindRoom = function (root) {
    bindRoom(root);
    applyLockUI(); // fresh lock buttons reflect the persisted choice
    updateRoomLocks();
  };
  window.saShowView = show;
  window.saPlayingSlug = function () {
    return nowPlaying ? nowPlaying.slug : null;
  };
})();
</script>"""


def has_primer_section(notes_text: str) -> bool:
    """Does a '## Primer' heading live inside the notes?

    Nightly prep writes primers there (any heading level, case folded)
    — that counts as having one, even with no primer.mp3/primer.md.
    """
    return bool(re.search(r"(?mi)^#{1,6} primer\b", notes_text or ""))


def notes_are_empty(text: str) -> bool:
    """No notes, or notes that are all headings and blank lines —
    'effectively empty': nothing anyone actually wrote down yet."""
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not re.fullmatch(r"#{1,6}( .*)?", line):
            return False
    return True


def render_generator(css: str, title: str, label: str, desc: str) -> str:
    """One empty section's uniform ✦ invitation.

    Every main card section either has content or shows this exact
    pattern: the generate button (a canned ask through the queue-aware
    chat send — delegated JS, so swapped-in rooms keep working) plus one
    quiet line saying what it creates.
    """
    return (
        '<p class="gen-empty">'
        f'<button type="button" class="{css}" data-title="{escape(title)}">'
        f"✦ {escape(label)}</button>\n"
        f'<span class="gen-desc">{escape(desc)}</span></p>'
    )


def render_moments(slug: str, title: str, moments: list[dict]) -> str:
    """The Transcript block's front layer: anchored listening first.

    With moments, each becomes a chip — "listen from 13:23 — <why>" —
    that seeks the talk player exactly like a transcript-line click
    (bindRoom wires .moments through the ONE seek path), followed by a
    small "✦ more like this" asking for a few more, no duplicates.
    Without moments, the ✦ mark-the-moments generator sits in the front
    layer instead. Either way the timestamps are grounded in
    transcript.json — callers only render this layer when it exists.
    """
    if moments:
        chips = "\n".join(
            f'<button type="button" class="moment-chip" data-start="{m["start"]:g}">'
            f'<span class="moment-time">listen from {format_time(m["start"])}</span>'
            f" — {escape(m['label'])}</button>"
            for m in moments
        )
        return (
            f'<div class="moments" data-slug="{escape(slug)}">\n{chips}\n</div>\n'
            '<p class="gen-more">'
            f'<button type="button" class="more-moments" data-title="{escape(title)}">'
            "✦ more like this</button></p>"
        )
    return render_generator(
        "mark-moments",
        title,
        "ask the guide to mark the moments",
        "3–6 anchored jump-to moments, grounded in the transcript",
    )


def render_stub_card(stub: dict) -> str:
    """A room-in-waiting for a queued talk not yet in the library.

    The sidebar's greyed dead-ends become real rooms: title, teacher,
    why it's on the path (the curriculum's own line), the source link,
    and ONE primary action. With a fetchable URL that's "✦ fetch this
    talk" (an explicit single-item download, said plainly); a reading
    or unknown source gets "ask the guide about this" instead — never a
    fetch without a recording URL. Both go through the queue-aware chat
    send; once the real talk lands, the next shelf swap replaces this
    room with the real one.
    """
    parts = [
        f'<section class="card view talk-stub" id="talk-{escape(stub["slug"])}">',
        f"<h2>{escape(stub['title'])}</h2>",
    ]
    meta = " &middot; ".join(
        bit for bit in (escape(stub.get("teacher", "")), "not fetched yet") if bit
    )
    parts.append(f'<p class="meta">{meta}</p>')
    parts.append(
        '<p class="card-status"><span class="status-mark status-next">'
        "→ on the path — not in the library yet</span></p>"
    )
    if stub.get("why"):
        parts.append(
            f'<p class="reach"><em>on the path because: {escape(stub["why"])}</em></p>'
        )
    if stub.get("url"):
        parts.append(
            f'<a class="source-link" href="{escape(stub["url"])}" target="_blank" '
            'rel="noopener">source &#8599;</a>'
        )
    if stub.get("fetchable"):
        parts.append(
            '<p class="stub-action"><button type="button" class="fetch-stub" '
            f'data-title="{escape(stub["title"])}" '
            f'data-teacher="{escape(stub.get("teacher", ""))}" '
            f'data-url="{escape(stub["url"])}">✦ fetch this talk</button></p>'
        )
        parts.append(
            '<p class="state-note">downloads are explicit — this fetches one '
            "talk; transcription can take a few minutes.</p>"
        )
    else:
        parts.append(
            '<p class="stub-action"><button type="button" class="ask-stub" '
            f'data-title="{escape(stub["title"])}">'
            "ask the guide about this</button></p>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def render_card(
    talk: dict,
    files: dict,
    reach: str | None,
    listened: dict | None = None,
    state: str | None = None,
) -> str:
    slug = talk["slug"]
    title = talk.get("title", slug)
    cap = duration_to_seconds(talk.get("duration", ""))
    cap_attr = f' data-duration="{cap}"' if cap else ""
    parts = [
        f'<section class="card view" id="talk-{escape(slug)}"{cap_attr}>',
        f"<h2>{escape(title)}</h2>",
        # The room-side guide-navigation lock: shown only while THIS talk
        # is the one playing (the capsule carries its twin).
        f'<button type="button" class="guide-lock room-lock" '
        f'data-slug="{escape(slug)}" hidden></button>',
        f'<p class="meta">{escape(talk.get("teacher", ""))}'
        f" &middot; {escape(talk.get('themes', ''))}</p>",
    ]
    # The card names its own place on the path, right at the top — the
    # same three-state vocabulary as the sidebar — and the one completion
    # action sits beside it, so status and action read as one unit.
    heard = bool(listened and listened.get("last"))
    status_bits = []
    if state == "studied":
        date = f' · {escape(listened["last"][:10])}' if heard else ""
        status_bits.append(
            f'<span class="status-mark status-done">✓ done{date}</span>'
        )
        # A closed talk still has a door — quiet, dotted, one line. The
        # click is server-first (POST /api/reopen: Studied → Queued,
        # instantly), then the guide follows up in conversation.
        status_bits.append(
            f'<button type="button" class="reopen-talk" '
            f'data-slug="{escape(slug)}" data-title="{escape(title)}">'
            "reopen — put it back on the path</button>"
        )
    else:
        if heard:
            # Named next to the Done button, so the button's purpose is
            # obvious: heard, but not yet closed out on the path.
            status_bits.append(
                '<span class="status-mark status-heard">'
                "heard — not closed out yet</span>"
            )
        elif state == "queued":
            status_bits.append(
                '<span class="status-mark status-next">→ current</span>'
            )
        status_bits.append(
            '<button type="button" class="done-for-now" '
            f'data-slug="{escape(slug)}" data-title="{escape(title)}">'
            "✓ Done with this talk</button>"
        )
        if heard:
            status_bits.append(
                '<button type="button" class="wrap-up-talk" '
                f'data-title="{escape(title)}">'
                "…or wrap it up together — what landed?</button>"
            )
        else:
            # The manual door, for listens the player couldn't see. On
            # the static shelf the click fails quietly and re-arms.
            status_bits.append(
                f'<button type="button" class="mark-heard" data-slug="{escape(slug)}" '
                'title="finished this talk somewhere the player couldn\'t see? '
                'record it">mark as heard</button>'
            )
    parts.append('<p class="card-status">' + " ".join(status_bits) + "</p>")
    if reach:
        parts.append(f'<p class="reach"><em>{escape(reach)}</em></p>')
    if files["primer_mp3"]:
        parts.append('<p class="player-label">Primer — 1 min, spoken by the guide</p>')
        parts.append(
            f'<audio controls preload="none" src="{escape(slug)}/primer.mp3"></audio>'
        )
    if files["audio"]:
        parts.append('<p class="player-label">The talk</p>')
        parts.append(
            f'<audio controls preload="none" class="talk-audio" '
            f'data-slug="{escape(slug)}" '
            f'src="{escape(slug)}/{escape(files["audio"])}"></audio>'
        )
    elif talk.get("source"):
        source = talk["source"]
        embed = youtube_embed_url(source)
        if embed:
            # Click-to-load: the iframe exists only after the click, so the
            # page stays light and makes no third-party request until
            # asked. With a local thumbnail the placeholder is the picture
            # itself (downloaded at ingest — YouTube is never pinged just
            # to show it); otherwise a plain calm button.
            if files["thumbnail"]:
                duration = talk.get("duration", "")
                duration_tag = (
                    f'<span class="yt-duration">{escape(duration)}</span>\n'
                    if duration
                    else ""
                )
                button = (
                    '<button type="button" class="yt-play yt-thumb">\n'
                    f'<img src="{escape(slug)}/thumbnail.jpg" alt="" loading="lazy">\n'
                    '<span class="yt-glyph">▶</span>\n'
                    f"{duration_tag}</button>"
                )
            else:
                button = '<button type="button" class="yt-play">Play here ▸</button>'
            # No separate "open on YouTube" anchor: the embedded
            # player's own logo link already covers that need.
            parts.append(
                f'<div class="yt-embed" data-embed="{escape(embed)}" '
                f'data-slug="{escape(slug)}">\n{button}\n</div>'
            )
        else:
            parts.append(
                f'<a class="source-link" href="{escape(source)}" target="_blank" '
                'rel="noopener">Listen at the source &rarr;</a>'
            )
    if heard:
        # Finished at least once: say so quietly. Replay simply plays —
        # the resume position was cleared at the end, so it starts fresh.
        # A not-yet-done talk can also step back to unheard ("come back
        # to this"); done is a path state and keeps its own reopen door.
        unheard = (
            f' · <button type="button" class="mark-unheard" '
            f'data-slug="{escape(slug)}">mark unheard — come back to this</button>'
            if state != "studied"
            else ""
        )
        parts.append(
            f'<p class="listened-line">listened ✓ {escape(listened["last"][:10])}'
            f' · <button type="button" class="listened-replay" '
            f'data-slug="{escape(slug)}">replay</button>{unheard}</p>'
        )
    return "\n".join(parts)


_NAV_MARKS = {
    "studied": '<span class="nav-state nav-done">✓</span> ',
    "queued": '<span class="nav-state nav-next">→</span> ',
}

_NAV_LEGEND = '<p class="nav-legend">✓ done · → current</p>'


def render_nav(
    talks: list[dict],
    states: dict[str, str] | None = None,
    stubs: list[dict] | tuple = (),
) -> str:
    """The sidebar's Talks list — which IS the path.

    Three states only, so a glance answers "am I done with this one?":
    ✓ done, → current, or nothing (in the library, untouched). Parked
    talks read as done here — their nuance stays in STUDY.md and notes.
    Queued talks not yet fetched appear last as rooms-in-waiting: real
    links into their stub rooms (render_stub_card), muted but no longer
    dead ends. One tiny legend line keeps the marks self-explanatory.
    """
    states = states or {}
    if not talks and not stubs:
        return '<p class="side-muted">The library is empty so far.</p>'
    items = []
    for talk in talks:
        state = states.get(talk["slug"])
        mark = _NAV_MARKS.get(state, "")
        items.append(
            f'<li><a href="#talk/{escape(talk["slug"])}">'
            f'{mark}<span class="nav-title">{escape(talk.get("title", talk["slug"]))}</span>'
            f'<span class="nav-teacher">{escape(talk.get("teacher", ""))}</span></a></li>'
        )
    for stub in stubs:
        hint = (
            "not fetched yet — open to fetch it"
            if stub.get("fetchable")
            else "not fetched yet — ask the guide"
        )
        items.append(
            f'<li class="nav-unfetched"><a href="#talk/{escape(stub["slug"])}">'
            f'{_NAV_MARKS["queued"]}<span class="nav-title">{escape(stub["name"])}</span>'
            f'<span class="nav-teacher">{hint}</span></a></li>'
        )
    return '<ul id="talk-nav">\n' + "\n".join(items) + "\n</ul>\n" + _NAV_LEGEND


_URL_IN_HTML = re.compile(r"https?://[^\s<]+")


def _link_curriculum_urls(html: str, by_source: dict[str, str]) -> str:
    """Turn bare curriculum URLs into calm links.

    A URL whose talk is already in the library becomes an in-page
    "on your shelf →" link; anything else keeps an external (noopener)
    link plus the standing invitation to ask the guide.
    """

    def swap(match: re.Match) -> str:
        raw = match.group(0)
        trimmed = raw.rstrip(".,;:)")
        trailing = raw[len(trimmed):]
        url = trimmed.replace("&amp;", "&")
        slug = by_source.get(youtube_embed_url(url) or url)
        if slug:
            return (
                f'<a class="cur-onshelf" href="#talk/{escape(slug)}">on your shelf &rarr;</a>'
                + trailing
            )
        return (
            f'<a href="{trimmed}" target="_blank" rel="noopener">source ↗</a> '
            '<span class="cur-hint">ask the guide to fetch it</span>' + trailing
        )

    return _URL_IN_HTML.sub(swap, html)


def render_curriculum(curriculum: Path, talks: list[dict]) -> str:
    """The curriculum room: committed clusters rendered first-party.

    curriculum/*.md is trusted, committed content — md_to_html (escaped)
    with the calm styling, no sandbox needed. Returns "" when there is
    nothing to show, so the room simply doesn't exist yet.
    """
    files = [
        path
        for path in (sorted(curriculum.glob("*.md")) if curriculum.is_dir() else [])
        if path.name.lower() != "readme.md"
    ]
    if not files:
        return ""
    by_source: dict[str, str] = {}
    for talk in talks:
        source = talk.get("source")
        if source:
            by_source[youtube_embed_url(source) or source] = talk["slug"]
    clusters = "\n".join(
        f'<section class="cluster">\n'
        f"{_link_curriculum_urls(md_to_html(path.read_text()), by_source)}\n</section>"
        for path in files
    )
    return (
        '<section class="card view" id="view-curriculum">\n'
        "<h2>Curriculum</h2>\n"
        '<p class="meta">The road ahead, cluster by cluster. Anything not yet '
        "on the shelf, the guide can fetch.</p>\n"
        f"{clusters}\n</section>"
    )


# The settings room: a fixed skeleton the chat script fills from /health,
# /api/models and /api/prep (createElement + textContent only — the rows
# are rebuilt after every soft-refresh swap, so nothing here is stateful).
# The static file:// shelf shows the plain-text parts and none of the
# controls. Everything Hermes-side is stated as configuration to run BY
# HAND — this page never writes ~/.hermes.
SETTINGS_VIEW = """<section class="card view" id="view-settings">
<h2>Settings</h2>
<p class="meta">The guide's machinery — read honestly, changed here where
the page has hands, and in Hermes itself where it doesn't.</p>
<section class="set-group" id="set-brain">
<h3>The guide's brain</h3>
<p class="set-headline">The guide runs on <strong>Hermes</strong> —
hermes-agent (Nous Research) · profile <code>second-arrow</code> ·
14 reviewed tools. <span id="hermes-wired-state" class="set-state"></span></p>
<div id="route-rows" class="pick-rows"></div>
<p id="hermes-unwired" class="set-fine" hidden>not wired — run
<code>uv run tools/wire_hermes_profile.py</code>, then
<code>hermes -p second-arrow gateway restart</code>, then verify with
<code>uv run tools/hermes_probe.py</code>.</p>
<p class="set-fine">The profile's default model lives in
<code>~/.hermes/profiles/second-arrow/config.yaml</code> — change it with
<code>hermes -p second-arrow config set model.default …</code>
or the Hermes app → Settings → Model, then
<code>hermes -p second-arrow gateway restart</code>.
This page never edits Hermes config.</p>
</section>
<section class="set-group" id="set-fallback" hidden>
<h3>Fallback brains</h3>
<div id="fallback-rows" class="pick-rows"></div>
<select id="chat-model" hidden></select>
<p id="fallback-note" class="set-fine" hidden></p>
</section>
<section class="set-group" id="set-machinery" hidden>
<h3>The room's machinery</h3>
<ul id="machinery-list"></ul>
</section>
<section class="set-group" id="set-prep" hidden>
<h3>Nightly prep</h3>
<p class="set-fine">A quiet job inside the Hermes gateway: primers, notes,
and moments for queued talks, nothing fetched that isn't already on the
path.</p>
<p id="prep-line" class="set-state"></p>
<p id="prep-controls" hidden>
<button type="button" id="prep-run" class="prep-btn">run now</button>
<button type="button" id="prep-pause" class="prep-btn">pause</button>
<button type="button" id="prep-resume" class="prep-btn">resume</button>
</p>
<p id="prep-feedback" class="set-fine" hidden></p>
</section>
</section>"""


def render_shelf(library: Path, reach: dict[str, str] | None = None) -> str:
    reach = reach or {}
    study_path = library.parent / "STUDY.md"
    study = study_path.read_text() if study_path.exists() else ""
    path = parse_study(study)
    path_strip = render_path_strip(path)  # the home view's small summary
    talks = parse_index((library / "INDEX.md").read_text())
    states, unfetched = talk_states(path, talks)
    # Rooms-in-waiting: each queued-but-unfetched path item gets a stub
    # room carrying what the curriculum knows about it.
    entries = curriculum_entries(library.parent / "curriculum")
    stubs = [curriculum_stub(name, entries) for name in unfetched]
    listening = load_listening(library)
    curriculum_view = render_curriculum(library.parent / "curriculum", talks)
    curriculum_link = (
        '\n<a class="begin-link" href="#curriculum">curriculum</a>'
        if curriculum_view
        else ""
    )
    cards = []
    for talk in talks:
        talk_dir = library / talk["slug"]
        files = probe(talk_dir) if talk_dir.is_dir() else probe(library / "_missing_")
        card = [render_card(talk, files, reach.get(talk.get("source", "")),
                            listened=listening.get(talk["slug"]),
                            state=states.get(talk["slug"]))]
        slug = escape(talk["slug"])
        title = talk.get("title", talk["slug"])
        notes_text = (
            (talk_dir / "notes.md").read_text() if files["notes_md"] else ""
        )
        # The completeness standard: Primer / Notes / Transcript·listen
        # for / Interactive each has content or shows its ✦ generator in
        # a details block that still RENDERS — sections never disappear.
        if files["primer_md"]:
            primer = md_to_html((talk_dir / "primer.md").read_text())
            card.append(f"<details><summary>Primer text</summary>\n{primer}\n</details>")
        elif not (files["primer_mp3"] or has_primer_section(notes_text)):
            card.append(
                "<details open><summary>Primer</summary>\n"
                + render_generator(
                    "make-primer",
                    title,
                    "ask the guide to write & speak a primer",
                    "a 60–90 second spoken introduction — who the teacher "
                    "is, what to listen for",
                )
                + "\n</details>"
            )
        if not notes_are_empty(notes_text):
            card.append(
                f"<details><summary>Notes</summary>\n{md_to_html(notes_text)}\n</details>"
            )
        else:
            card.append(
                "<details open><summary>Notes</summary>\n"
                + render_generator(
                    "make-notes",
                    title,
                    "ask the guide to start notes for this talk",
                    "a living notes file — takeaways, quotes, the moments "
                    "worth returning to",
                )
                + "\n</details>"
            )
        segments = []
        if files["transcript_json"]:
            try:
                segments = normalize_segments(
                    json.loads((talk_dir / "transcript.json").read_text())
                )
            except (OSError, json.JSONDecodeError):
                segments = []  # a torn file falls back to the plain rendering
        # The guide's curated "listen for" moments (notes.md ## Moments),
        # validated against the transcript's own range — a moment past
        # the end is silently invalid (same rule as the seek cues).
        moment_cap = max((seg["end"] for seg in segments), default=0) or (
            duration_to_seconds(talk.get("duration", "")) or 0
        )
        moments_front = (
            render_moments(
                talk["slug"], title, parse_moments(notes_text, cap=moment_cap)
            )
            if files["transcript_json"]
            else ""  # no grounding possible: no moments layer at all
        )
        if segments:
            # The transcript block opens onto the moments (chips or the
            # ✦, one home for anchored listening); the segmented
            # click-to-seek transcript waits behind a quiet sub-expander,
            # with the raw file still a click away.
            rows = "\n".join(
                f'<p class="seg" data-start="{seg["start"]:g}">'
                f'<span class="seg-time">{format_time(seg["start"])}</span> '
                f"{escape(seg['text'])}</p>"
                for seg in segments
            )
            card.append(
                "<details open><summary>Transcript · listen for</summary>\n"
                f"{moments_front}\n"
                '<details class="full-transcript">'
                "<summary>full transcript ▸</summary>\n"
                f'<p class="raw-link"><a href="{slug}/transcript.md">open raw file &rarr;</a></p>\n'
                f'<div class="scroll-box seg-transcript" data-slug="{slug}">\n'
                f"{rows}\n</div>\n</details>\n</details>"
            )
        elif moments_front:
            # transcript.json exists but yielded no segments (a torn
            # file): the moments layer still gets its one home.
            card.append(
                "<details open><summary>Listen for</summary>\n"
                + moments_front
                + "\n</details>"
            )
        if not segments and files["transcript_md"]:
            # Rendered inline (escaped, formatted) — the raw .md link alone
            # opened as one wall of unformatted text. Transcripts run long,
            # so the rendered copy lives in a scrollable box, with the raw
            # file still a click away.
            transcript = md_to_html((talk_dir / "transcript.md").read_text())
            card.append(
                "<details><summary>Transcript</summary>\n"
                f'<p class="raw-link"><a href="{slug}/transcript.md">open raw file &rarr;</a></p>\n'
                f'<div class="scroll-box">\n{transcript}\n</div>\n</details>'
            )
        if files["artifacts"]:
            # Guide-written interactive pages. The static HTML carries only
            # plain new-tab links; the sandboxed iframes (allow-scripts,
            # never allow-same-origin, behind the /artifacts/ CSP wall) are
            # mounted by JS on the served shelf — a file:// iframe would
            # have no CSP wall, so it is never emitted here.
            items = "\n".join(
                f'<li class="artifact-item" data-slug="{slug}" data-name="{escape(name)}">\n'
                f'<span class="artifact-name">{escape(name)}</span>\n'
                f'<a class="artifact-open" href="{slug}/artifacts/{escape(name)}"'
                ' target="_blank" rel="noopener">open full page ↗</a>\n</li>'
                for name in files["artifacts"]
            )
            interactive_body = (
                '<p class="artifact-note">Interactive pages the guide made for'
                " this talk. The sandboxed view appears on the served shelf;"
                " these links open the raw page.</p>\n"
                f'<ul class="artifact-list">\n{items}\n</ul>'
            )
        else:
            # No tools yet: one calm generator in the uniform ✦ pattern.
            # Clicking sends the ask through the normal chat path — the
            # peek shows the build.
            interactive_body = render_generator(
                "make-interactive",
                title,
                "create interactive tools from this talk",
                "small practice pages with anchored listen-from links",
            )
        card.append(
            "<details open><summary>Interactive</summary>\n"
            + interactive_body
            + "\n</details>"
        )
        card.append("</section>")
        cards.append("\n".join(card))
    talk_views = "\n\n".join(cards + [render_stub_card(stub) for stub in stubs])
    empty_note = "" if cards else "\n<p>The library is empty so far.</p>"
    # One plain sentence next to the path summary, so "done" never needs
    # guessing at. Only when there is a path to explain — an empty study
    # space stays untouched.
    state_note = (
        '\n<p class="state-note">✓ done — say so with a talk\'s '
        "“Done for now” button, or by wrapping it up with the guide.</p>"
        if (path_strip or listening)
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Second Arrow — Study Shelf</title>
<style>{STYLE}</style>
</head>
<body>
<button type="button" id="sidebar-toggle" aria-label="Toggle sidebar">☰</button>
<button type="button" id="sidebar-reopen" title="show the sidebar" aria-label="show the sidebar">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.2 12h15.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9.8 6.8 4.2 12l5.6 5.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M14.6 12l3.1-2.9M14.6 12l3.1 2.9M17.4 12l3.1-2.9M17.4 12l3.1 2.9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
</button>
<div id="layout">
<nav id="sidebar">
<button type="button" id="sidebar-collapse" title="hide the sidebar" aria-label="hide the sidebar">
<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.2 12h15.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M9.8 6.8 4.2 12l5.6 5.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M14.6 12l3.1-2.9M14.6 12l3.1 2.9M17.4 12l3.1-2.9M17.4 12l3.1 2.9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
</button>
<h1>Second Arrow</h1>
<p class="epigraph">Pain happens. The second arrow is optional.</p>
<a class="begin-link" href="#home">begin here</a>{curriculum_link}
<h2 id="talks-heading">Talks</h2>
{render_nav(talks, states, stubs)}
<footer>
Private — generated from your library.
Rebuild: <code>uv run tools/build_shelf.py</code><br>
<a class="side-settings" href="#settings">settings</a>
</footer>
</nav>
<main>
<div id="now-playing" hidden>
<button type="button" id="np-body" title="go to this talk">
<img id="np-thumb" alt="" hidden>
<span id="np-glyph" hidden>▶</span>
<span id="np-title"></span>
<span id="np-time"></span>
</button>
<button type="button" id="np-lock" class="guide-lock"></button>
<button type="button" id="np-play" title="play / pause"></button>
<button type="button" id="np-stop" title="stop — your place is kept">■</button>
<button type="button" id="np-expand" title="go to this talk">⤢</button>
</div>
<div id="views">
<section class="card view" id="view-home">
<h2>Begin here</h2>
<p class="epigraph">Pain happens. The second arrow is optional.</p>
<div class="how-lines">
<p>Pick a talk from the sidebar — the guide comes with you.</p>
<p>Press play. Leave whenever; your place is kept.</p>
<p>The transcript follows the voice — click any line to be there.</p>
<p>Interactive tools live on each talk's card, made for you by the guide.</p>
<p>And just tell the guide where you are — it remembers so you don't have to.</p>
</div>
{path_strip}{state_note}{empty_note}
<div id="machinery" hidden>
<p class="machinery-link"><a href="#settings">the room's machinery → settings</a></p>
</div>
</section>

{curriculum_view}

{SETTINGS_VIEW}

{talk_views}
</div>

{CHAT_PANEL}
</main>
</div>
{LAYOUT_SCRIPT}
</body>
</html>
"""


def collect_reach(curriculum: Path) -> dict[str, str]:
    reach: dict[str, str] = {}
    if curriculum.is_dir():
        for path in sorted(curriculum.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            reach.update(reach_lines(path.read_text()))
    return reach


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the study shelf page.")
    parser.add_argument("--library", default="library", help="library directory")
    parser.add_argument("-o", "--output", default=None, help="output HTML path")
    args = parser.parse_args()

    library = Path(args.library)
    if not (library / "INDEX.md").exists():
        raise SystemExit(f"No {library / 'INDEX.md'} found — ingest a talk first.")

    reach = collect_reach(library.parent / "curriculum")
    output = Path(args.output) if args.output else library / "shelf.html"
    output.write_text(render_shelf(library, reach))
    print(f"Wrote {output}")
    print(f"Hint: open {output}")


if __name__ == "__main__":
    main()
