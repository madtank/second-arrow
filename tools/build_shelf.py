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
a Sessions placeholder) and a main pane showing one view at a time —
#home or #talk/<slug> — routed by a tiny hashchange handler. With JS off
the views simply render stacked (hiding happens only under a runtime "js"
class). YouTube-sourced talks get a click-to-load embedded player: nothing
third-party loads until the user presses "Play here". The guide chat panel
sits below the active view and stays put across views.

Run with:
    uv run tools/build_shelf.py
Then:
    open library/shelf.html
"""

import argparse
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
    """Markdown-lite: #–### headings, - lists, **bold**, paragraphs. Escapes HTML."""
    out: list[str] = []
    in_list = False
    for raw in text.splitlines():
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(raw.strip()))
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        heading = re.match(r"(#{1,3}) (.+)", line)
        if heading and in_list:
            out.append("</ul>")
            in_list = False
        if heading:
            level = len(heading.group(1)) + 2  # keep card headings below the page h1/h2
            out.append(f"<h{level}>{heading.group(2)}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line[2:]}</li>")
        else:
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def parse_study(text: str) -> dict:
    """Pull the path out of STUDY.md: {"studied": [names], "queued": [names]}.

    Tolerant by design (STUDY.md is hand- and guide-edited): missing
    sections or plain prose give empty lists. Only top-level `- ` items
    inside `## Studied` / `## Queued` count; an item's name is its leading
    **bold** span, else the text before the first " — " or ": "
    separator. Wrapped continuation lines are ignored.
    """
    path: dict = {"studied": [], "queued": []}
    section = None
    for line in text.splitlines():
        heading = re.match(r"#{2,} (.+)", line)
        if heading:
            name = heading.group(1).strip().lower()
            section = name if name in path else None
            continue
        if section is None or not line.startswith("- "):
            continue
        item = line[2:].strip()
        bold = re.match(r"\*\*(.+?)\*\*", item)
        name = bold.group(1) if bold else re.split(r" — |: ", item)[0]
        name = name.strip().rstrip(".")
        if name:
            path[section].append(name)
    return path


def render_path_strip(path: dict) -> str:
    """A small calm strip: studied talks with a check, queued with an arrow.

    Rendered in the sidebar and again in the #home view. Returns "" when
    there is nothing to show, so a missing or empty STUDY.md leaves the
    page untouched (it must stay statically shareable).
    """
    marks = (("studied", "✓", "path-done"), ("queued", "→", "path-next"))
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
  .side-muted { color: #a99e8e; font-size: 0.85rem; font-style: italic; }
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
  .player-label { margin: 1rem 0 0.3rem; font-size: 0.9rem; color: #6d5f4b; }
  audio { width: 100%; }
  .source-link { display: inline-block; margin-top: 1rem; padding: 0.5rem 1rem;
                 background: #efe7d9; border-radius: 8px; color: #5a4d3a;
                 text-decoration: none; }
  .yt-embed { margin-top: 1rem; }
  .yt-play { font: inherit; color: #5a4d3a; background: #efe7d9; border: none;
             border-radius: 8px; padding: 0.5rem 1rem; cursor: pointer; }
  .yt-link { margin-left: 0.75rem; font-size: 0.85rem; color: #a99e8e; }
  .yt-frame { aspect-ratio: 16 / 9; }
  .yt-frame iframe { width: 100%; height: 100%; border: 0;
                     border-radius: 8px; }
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
  #chat-messages { height: 320px; overflow-y: auto; padding: 0.25rem 0;
                   border-top: 1px solid #f0e9dd; }
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
  var pills = document.querySelectorAll("#chat-brain .brain-pill");
  var history = [];
  var brain = null; // which brain the next message goes to (/health default)

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

  function restoreHistory() {
    fetch("/api/history").then(function (r) { return r.json(); }).then(function (data) {
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
        add("system", "— switched to " + name
          + (name === "ollama" ? " (offline)" : " (deep)") + " —");
      });
    });
    markActive();
    panel.hidden = false;
    restoreHistory(); // earlier turns come back after a reload or restart
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
      body: JSON.stringify({ messages: history, brain: brain })
    }).then(function (r) {
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
      input.focus();
    });
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
})();
</script>"""


# Hash routing, the sidebar toggle, and the click-to-load YouTube player.
# Views are hidden only under the runtime "js" class (added below): with
# JS off, or file:// oddities, every view simply renders stacked. The
# player iframe is built with createElement + setAttribute — the page
# makes no third-party request until the user presses "Play here".
LAYOUT_SCRIPT = """<script>
(function () {
  var sidebar = document.getElementById("sidebar");
  var toggle = document.getElementById("sidebar-toggle");
  var views = document.querySelectorAll(".view");
  var links = document.querySelectorAll("#talk-nav a");
  document.body.classList.add("js"); // hiding starts here, never in the HTML

  function show() {
    var hash = location.hash || "#home";
    var id = hash.indexOf("#talk/") === 0 ? "talk-" + hash.slice(6) : "view-home";
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

  document.querySelectorAll(".yt-embed").forEach(function (holder) {
    var button = holder.querySelector(".yt-play");
    if (!button) return;
    button.addEventListener("click", function () {
      var frame = document.createElement("iframe");
      frame.setAttribute("src", holder.getAttribute("data-embed") + "?autoplay=1");
      frame.setAttribute("title", "YouTube player");
      frame.setAttribute("allow", "accelerometer; autoplay; clipboard-write; "
        + "encrypted-media; gyroscope; picture-in-picture; web-share");
      frame.setAttribute("allowfullscreen", "");
      frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      var box = document.createElement("div");
      box.className = "yt-frame";
      box.appendChild(frame);
      holder.replaceChild(box, button);
    });
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
            f'<audio controls preload="none" src="{escape(slug)}/{escape(files["audio"])}"></audio>'
        )
    elif talk.get("source"):
        source = talk["source"]
        embed = youtube_embed_url(source)
        if embed:
            # Click-to-load: the iframe exists only after "Play here", so
            # the page stays light and makes no third-party request until
            # asked. A small new-tab escape hatch sits alongside.
            parts.append(
                f'<div class="yt-embed" data-embed="{escape(embed)}">\n'
                '<button type="button" class="yt-play">Play here ▸</button>\n'
                f'<a class="yt-link" href="{escape(source)}" target="_blank" '
                'rel="noopener">open on YouTube ↗</a>\n</div>'
            )
        else:
            parts.append(
                f'<a class="source-link" href="{escape(source)}" target="_blank" '
                'rel="noopener">Listen at the source &rarr;</a>'
            )
    return "\n".join(parts)


def render_nav(talks: list[dict]) -> str:
    """The sidebar's Talks list: one hash link per talk (title + teacher)."""
    if not talks:
        return '<p class="side-muted">The library is empty so far.</p>'
    items = [
        f'<li><a href="#talk/{escape(talk["slug"])}">'
        f'<span class="nav-title">{escape(talk.get("title", talk["slug"]))}</span>'
        f'<span class="nav-teacher">{escape(talk.get("teacher", ""))}</span></a></li>'
        for talk in talks
    ]
    return '<ul id="talk-nav">\n' + "\n".join(items) + "\n</ul>"


def render_shelf(library: Path, reach: dict[str, str] | None = None) -> str:
    reach = reach or {}
    study_path = library.parent / "STUDY.md"
    study = study_path.read_text() if study_path.exists() else ""
    path_strip = render_path_strip(parse_study(study))
    talks = parse_index((library / "INDEX.md").read_text())
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
        if files["transcript_md"]:
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
{path_strip}
<h2>Talks</h2>
{render_nav(talks)}
<h2>Sessions</h2>
<p class="side-muted">conversation history arrives in the next iteration</p>
<footer>
Private — generated from your library.
Rebuild: <code>uv run tools/build_shelf.py</code>
</footer>
</nav>
<main>
<div id="views">
<section class="card view" id="view-home">
<h2>Study shelf</h2>
<p class="epigraph">Pain happens. The second arrow is optional.</p>
{path_strip}
<p>When you're ready, pick a talk from the sidebar, or talk to the guide
below.</p>{empty_note}
</section>

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
