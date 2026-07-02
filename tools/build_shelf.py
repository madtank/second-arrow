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


def format_time(seconds) -> str:
    """65 -> "1:05", 3725 -> "1:02:05" — segment stamps and durations."""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


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
    """(slug -> "studied"|"queued"|"parked", queued names not yet fetched).

    Matches parse_study names against library titles via normalize_title.
    Library talks absent from STUDY.md simply get no state; queued names
    with no library match come back as `unfetched`, so the path ahead
    stays visible in the sidebar.
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
                states.setdefault(slug, state)
            elif state == "queued":
                unfetched.append(name)
    return states, unfetched


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
  .nav-tag { margin-left: 0.5rem; color: #a99e8e; font-size: 0.72rem;
             border: 1px solid #e8e0d3; border-radius: 999px;
             padding: 0.05rem 0.5rem; vertical-align: middle; }
  .nav-unfetched { padding: 0.45rem 0.6rem; color: #a99e8e;
                   font-size: 0.95rem; line-height: 1.35; cursor: default; }
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
         padding: 2rem 1.5rem 4rem; }
  .js .view { display: none; }
  .js .view.active { display: block; }
  @media (max-width: 720px) {
    #sidebar-toggle { display: block; }
    #sidebar { position: fixed; z-index: 2; left: -290px;
               transition: left 0.2s ease; box-shadow: none; }
    #sidebar.open { left: 0; box-shadow: 0 0 24px rgba(60, 56, 51, 0.25); }
    main { padding-top: 3.5rem; }
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
  #guide-chat { position: sticky; bottom: 0; z-index: 2; margin-bottom: 0;
                box-shadow: 0 -8px 20px rgba(60, 56, 51, 0.07); }
  #chat-messages { max-height: 38vh; min-height: 5rem; overflow-y: auto;
                   padding: 0.25rem 0; border-top: 1px solid #f0e9dd; }
  .chat-msg { white-space: pre-wrap; margin: 0.6rem 0; padding: 0.5rem 0.8rem;
              border-radius: 8px; font-size: 0.95rem; }
  .chat-user { background: #efe7d9; margin-left: 2.5rem; }
  .chat-guide { background: #f6f1e7; margin-right: 2.5rem; }
  .chat-thinking { color: #a99e8e; font-style: italic; }
  .chat-system { background: none; text-align: center; color: #a99e8e;
                 font-size: 0.8rem; font-style: italic; padding: 0; }
  #chat-brain { display: flex; gap: 0.4rem; }
  .brain-pill { font: inherit; font-size: 0.8rem; color: #5a4d3a;
                background: none; border: 1px solid #e8e0d3;
                border-radius: 999px; padding: 0.15rem 0.7rem; cursor: pointer; }
  .brain-pill.brain-active { background: #efe7d9; border-color: #d8cbb4; }
  .brain-pill:disabled { opacity: 0.4; cursor: default; }
  #chat-model { font: inherit; font-size: 0.8rem; color: #5a4d3a;
                background: #fffdf9; border: 1px solid #e8e0d3;
                border-radius: 8px; padding: 0.15rem 0.4rem;
                max-width: 13rem; }
  #chat-form { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
  #chat-form textarea { flex: 1; font: inherit; color: inherit; resize: vertical;
                        background: #fffdf9; border: 1px solid #e8e0d3;
                        border-radius: 8px; padding: 0.5rem 0.75rem; }
  #chat-form button { font: inherit; color: #5a4d3a; background: #efe7d9;
                      border: none; border-radius: 8px; padding: 0 1.25rem;
                      cursor: pointer; }
  #chat-form button:disabled { opacity: 0.5; cursor: default; }
"""


# The panel starts hidden and only appears when /health answers — so the
# static file:// shelf keeps working unchanged. Guide replies stream in as
# chunked plain text (fetch + ReadableStream); errors before the stream
# starts arrive as JSON. The pill toggle picks which brain each message is
# sent to (per-request "brain" field), driven by /health's availability
# map. Replies are rendered with textContent (never innerHTML): model
# output stays inert text.
CHAT_PANEL = """<section class="card" id="guide-chat" hidden>
<h2>the guide</h2>
<p class="meta" id="chat-brain">
<button type="button" class="brain-pill" data-brain="claude">claude · deep</button>
<button type="button" class="brain-pill" data-brain="ollama">ollama · offline</button>
<select id="chat-model" hidden></select>
</p>
<div id="chat-messages"></div>
<form id="chat-form">
<textarea id="chat-input" rows="2" placeholder="Where are you right now?"></textarea>
<button type="submit" id="chat-send">Send</button>
</form>
</section>

<script>
(function () {
  var panel = document.getElementById("guide-chat");
  var list = document.getElementById("chat-messages");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var send = document.getElementById("chat-send");
  var pills = document.querySelectorAll("#chat-brain .brain-pill[data-brain]");
  var modelSelect = document.getElementById("chat-model");
  var history = [];
  var brain = null; // which brain the next message goes to (/health default)
  var session = null; // which conversation the next message continues
  var model = null; // which installed local model the ollama brain uses

  function add(role, text) {
    var div = document.createElement("div");
    div.className = "chat-msg chat-" + role;
    div.textContent = text; // textContent only — model output stays inert text
    list.appendChild(div);
    list.scrollTop = list.scrollHeight;
    return div;
  }

  function markActive() {
    pills.forEach(function (pill) {
      pill.classList.toggle(
        "brain-active", pill.getAttribute("data-brain") === brain);
    });
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

  // The local-model picker: visible only while the ollama pill is active
  // and /api/models actually answered (claude mode and the static shelf
  // never show it). Options are built with createElement + textContent.
  function updateModelVisibility() {
    modelSelect.hidden = brain !== "ollama" || modelSelect.options.length === 0;
  }

  function loadModels() {
    fetch("/api/models").then(function (r) { return r.json(); }).then(function (data) {
      (data.models || []).forEach(function (item) {
        var option = document.createElement("option");
        option.value = item.name;
        option.textContent = item.name
          + (item.tools ? " · tools" : "")
          + " · " + item.size_gb + "GB";
        modelSelect.appendChild(option);
      });
      if (data.current) {
        modelSelect.value = data.current;
        // Only adopt it when it is really one of the options — a default
        // that is not installed must not ride along with requests.
        if (modelSelect.value === data.current) model = data.current;
      }
      updateModelVisibility();
    }).catch(function () { /* ollama down or older server: picker stays hidden */ });
  }

  modelSelect.addEventListener("change", function () {
    model = modelSelect.value;
    add("system", "— ollama model: " + model + " —");
  });

  // Served mode only: swap each artifact link for a sandboxed live view.
  // Wall 1 is the sandbox — "allow-scripts" ALONE (never the same-origin
  // grant), so the artifact runs as a null origin. Wall 2 is the
  // /artifacts/ route's no-network CSP. The static file:// shelf keeps
  // the plain links instead: a file:// iframe would have neither wall.
  function mountArtifacts() {
    document.querySelectorAll(".artifact-note").forEach(function (note) {
      note.hidden = true; // the live view replaces the explanation
    });
    document.querySelectorAll(".artifact-item").forEach(function (item) {
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
    fetch(url).then(function (r) { return r.json(); }).then(function (data) {
      clearMessages();
      if (data.session) session = data.session;
      (data.turns || []).forEach(function (turn) {
        if (turn.role !== "user" && turn.role !== "assistant") return;
        var div = add(turn.role === "user" ? "user" : "guide", turn.content);
        if (turn.role === "assistant") renderRich(div, turn.content);
        history.push({ role: turn.role, content: turn.content });
      });
    }).catch(function () { /* an older server has no /api/history */ });
  }

  fetch("/health").then(function (r) { return r.json(); }).then(function (h) {
    if (!h.ok) return;
    brain = h.brain;
    var brains = h.brains || {};
    pills.forEach(function (pill) {
      var name = pill.getAttribute("data-brain");
      if (brains[name] === false) { // an older server omits the map
        pill.disabled = true;
        pill.title = name === "ollama"
          ? "start ollama serve" : "claude CLI not found";
      }
      pill.addEventListener("click", function () {
        if (pill.disabled || name === brain) return;
        brain = name;
        markActive();
        updateModelVisibility(); // the picker follows the ollama pill
        add("system", "— switched to " + name
          + (name === "ollama" ? " (offline)" : " (deep)") + " —");
      });
    });
    markActive();
    panel.hidden = false;
    restoreHistory(); // the conversation continues across reloads
    loadModels(); // fill the local-model picker (served mode only)
    mountArtifacts(); // artifact links become sandboxed live views
  }).catch(function () { /* static file:// shelf — panel stays hidden */ });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text || send.disabled) return;
    input.value = "";
    add("user", text);
    history.push({ role: "user", content: text });
    var pending = add("guide", "thinking…");
    pending.classList.add("chat-thinking");
    send.disabled = true;
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: history, brain: brain,
        session: session, view: currentView(),
        model: brain === "ollama" ? model : null
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
            pending.textContent += chunk;
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
        return;
      }
      renderRich(pending, reply); // bubble completed: dress the markdown
      history.push({ role: "assistant", content: reply });
    }).catch(function (error) {
      pending.classList.remove("chat-thinking");
      pending.textContent = "The guide is out of reach — " + error.message;
    }).finally(function () {
      send.disabled = false;
      input.focus({ preventScroll: true });
    });
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
    if (event.key === "Escape") {
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
  var views = document.querySelectorAll(".view");
  var links = document.querySelectorAll("#talk-nav a");
  document.body.classList.add("js"); // hiding starts here, never in the HTML

  function show() {
    var hash = location.hash || "#home";
    var id = "view-home";
    if (hash.indexOf("#talk/") === 0) id = "talk-" + hash.slice(6);
    else if (hash === "#curriculum") id = "view-curriculum";
    if (!document.getElementById(id)) id = "view-home"; // unknown hash: go home
    views.forEach(function (view) {
      view.classList.toggle("active", view.id === id);
    });
    links.forEach(function (link) {
      link.classList.toggle("active", link.getAttribute("href") === hash);
    });
  }
  window.addEventListener("hashchange", show);
  show();

  toggle.addEventListener("click", function () {
    sidebar.classList.toggle("open");
  });
  links.forEach(function (link) {
    link.addEventListener("click", function () {
      sidebar.classList.remove("open"); // narrow screens: picking closes it
    });
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

  document.querySelectorAll(".seg-transcript").forEach(function (box) {
    box.addEventListener("click", function (event) {
      var seg = event.target.closest(".seg");
      if (!seg) return;
      var slug = box.getAttribute("data-slug");
      var start = parseFloat(seg.getAttribute("data-start")) || 0;
      var audio = document.querySelector(
        'audio.talk-audio[data-slug="' + slug + '"]');
      if (audio) { seekAudio(audio, start); return; }
      var holder = document.querySelector(
        '.yt-embed[data-slug="' + slug + '"]');
      // No API dependency: seeking a YouTube talk just reloads the
      // embed at that second.
      if (holder) mountFrame(holder, Math.floor(start));
    });
  });

  // --- local audio: restore, track, highlight ---------------------------
  document.querySelectorAll("audio.talk-audio").forEach(function (audio) {
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
      var now = Date.now();
      if (now - lastSave < 5000) return; // throttled
      lastSave = now;
      savePos(slug, audio.currentTime, audio.duration);
    });
  });

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
    var box = document.createElement("div");
    box.className = "yt-frame";
    box.appendChild(frame);
    var old = holder.querySelector(".yt-frame") || holder.querySelector(".yt-play");
    if (old) holder.replaceChild(box, old);
  }

  document.querySelectorAll(".yt-embed").forEach(function (holder) {
    var button = holder.querySelector(".yt-play");
    if (!button) return;
    button.addEventListener("click", function () { mountFrame(holder); });
  });

  window.addEventListener("message", function (event) {
    if (event.origin !== "https://www.youtube-nocookie.com"
        && event.origin !== "https://www.youtube.com") return;
    var data;
    try { data = JSON.parse(event.data); } catch (e) { return; }
    if (!data || data.event !== "infoDelivery" || !data.info) return;
    var slug = data.id;
    if (!ytMounted[slug] || typeof data.info.currentTime !== "number") return;
    highlightSegment(slug, data.info.currentTime);
    var now = Date.now();
    if (now - (ytLastSave[slug] || 0) < 5000) return; // throttled
    ytLastSave[slug] = now;
    savePos(slug, data.info.currentTime, data.info.duration);
  });
})();
</script>"""


def render_card(talk: dict, files: dict, reach: str | None) -> str:
    slug = talk["slug"]
    parts = [
        f'<section class="card view" id="talk-{escape(slug)}">',
        f"<h2>{escape(talk.get('title', slug))}</h2>",
        f'<p class="meta">{escape(talk.get("teacher", ""))}'
        f" &middot; {escape(talk.get('themes', ''))}</p>",
    ]
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
    return "\n".join(parts)


_NAV_MARKS = {
    "studied": '<span class="nav-state nav-done">✓</span> ',
    "queued": '<span class="nav-state nav-next">→</span> ',
}


def render_nav(
    talks: list[dict],
    states: dict[str, str] | None = None,
    unfetched: list[str] | tuple = (),
) -> str:
    """The sidebar's Talks list — which IS the path.

    Each entry carries its state inline: ✓ studied, → queued, a muted
    "parked" tag, or nothing (in the library, not on the path). Queued
    talks not yet fetched appear last, muted and unclickable, so the
    path ahead stays visible.
    """
    states = states or {}
    if not talks and not unfetched:
        return '<p class="side-muted">The library is empty so far.</p>'
    items = []
    for talk in talks:
        state = states.get(talk["slug"])
        mark = _NAV_MARKS.get(state, "")
        tag = '<span class="nav-tag">parked</span>' if state == "parked" else ""
        items.append(
            f'<li><a href="#talk/{escape(talk["slug"])}">'
            f'{mark}<span class="nav-title">{escape(talk.get("title", talk["slug"]))}</span>{tag}'
            f'<span class="nav-teacher">{escape(talk.get("teacher", ""))}</span></a></li>'
        )
    items += [
        '<li class="nav-unfetched">'
        f'{_NAV_MARKS["queued"]}<span class="nav-title">{escape(name)}</span>'
        '<span class="nav-teacher">not fetched yet — ask the guide</span></li>'
        for name in unfetched
    ]
    return '<ul id="talk-nav">\n' + "\n".join(items) + "\n</ul>"


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


def render_shelf(library: Path, reach: dict[str, str] | None = None) -> str:
    reach = reach or {}
    study_path = library.parent / "STUDY.md"
    study = study_path.read_text() if study_path.exists() else ""
    path = parse_study(study)
    path_strip = render_path_strip(path)  # the home view's small summary
    talks = parse_index((library / "INDEX.md").read_text())
    states, unfetched = talk_states(path, talks)
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
        card = [render_card(talk, files, reach.get(talk.get("source", "")))]
        slug = escape(talk["slug"])
        if files["primer_md"]:
            primer = md_to_html((talk_dir / "primer.md").read_text())
            card.append(f"<details><summary>Primer text</summary>\n{primer}\n</details>")
        if files["notes_md"]:
            notes = md_to_html((talk_dir / "notes.md").read_text())
            card.append(f"<details><summary>Notes</summary>\n{notes}\n</details>")
        segments = []
        if files["transcript_json"]:
            try:
                segments = normalize_segments(
                    json.loads((talk_dir / "transcript.json").read_text())
                )
            except (OSError, json.JSONDecodeError):
                segments = []  # a torn file falls back to the plain rendering
        if segments:
            # The transcript as a player: each timed segment is clickable —
            # local-audio talks seek and play, YouTube talks reload the
            # embed at that moment. The raw file stays a click away.
            rows = "\n".join(
                f'<p class="seg" data-start="{seg["start"]:g}">'
                f'<span class="seg-time">{format_time(seg["start"])}</span> '
                f"{escape(seg['text'])}</p>"
                for seg in segments
            )
            card.append(
                "<details><summary>Transcript</summary>\n"
                f'<p class="raw-link"><a href="{slug}/transcript.md">open raw file &rarr;</a></p>\n'
                f'<div class="scroll-box seg-transcript" data-slug="{slug}">\n'
                f"{rows}\n</div>\n</details>"
            )
        elif files["transcript_md"]:
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
            card.append(
                "<details><summary>Learning tools</summary>\n"
                '<p class="artifact-note">Interactive pages the guide made for'
                " this talk. The sandboxed view appears on the served shelf;"
                " these links open the raw page.</p>\n"
                f'<ul class="artifact-list">\n{items}\n</ul>\n</details>'
            )
        card.append("</section>")
        cards.append("\n".join(card))
    talk_views = "\n\n".join(cards)
    empty_note = "" if cards else "\n<p>The library is empty so far.</p>"
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
<div id="layout">
<nav id="sidebar">
<h1>Second Arrow</h1>
<p class="epigraph">Pain happens. The second arrow is optional.</p>
<a class="begin-link" href="#home">begin here</a>{curriculum_link}
<h2>Talks</h2>
{render_nav(talks, states, unfetched)}
<footer>
Private — generated from your library.
Rebuild: <code>uv run tools/build_shelf.py</code>
</footer>
</nav>
<main>
<div id="views">
<section class="card view" id="view-home">
<h2>Begin here</h2>
<p class="epigraph">Pain happens. The second arrow is optional.</p>
<div class="how-lines">
<p>Pick a talk from the sidebar — the guide comes with you.</p>
<p>Press play. Leave whenever; your place is kept.</p>
<p>The transcript follows the voice — click any line to be there.</p>
<p>Learning tools live on each talk's card, made for you by the guide.</p>
<p>And just tell the guide where you are — it remembers so you don't have to.</p>
</div>
{path_strip}{empty_note}
</section>

{curriculum_view}

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
