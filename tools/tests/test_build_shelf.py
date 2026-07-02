import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "build_shelf.py"
SPEC = importlib.util.spec_from_file_location("build_shelf", MODULE_PATH)
build_shelf = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(build_shelf)

INDEX_SNIPPET = """# Library Index

One entry per ingested talk.

## patience
- **Title:** Patience
- **Teacher:** Thanissaro Bhikkhu
- **Source:** https://example.org/patience.html
- **Themes:** patience, anger
- **Path:** library/patience/

## anger-eating-demons
- **Title:** Anger Eating Demons
- **Teacher:** Ajahn Brahm
- **Source:** https://www.youtube.com/watch?v=me7Wm5LOpx0
- **Themes:** anger, kindness, stories
- **Path:** library/anger-eating-demons/
"""

CURRICULUM_SNIPPET = """# Cluster 1: Anger & the Second Arrow

## The source teaching

- **The Arrow (SN 36:6) — trans. Thanissaro Bhikkhu** — https://example.org/sn36-6.html
  The original two-arrows text. Short. Read it once early, return often.

## Talks

- **Patience — Thanissaro Bhikkhu (2026-06-12)** — https://example.org/patience.html
  Already in the library. Patience as not wearing the burden all the time.
  Reach for it when practice feels like grim endurance.

- **Anger Eating Demons — Ajahn Brahm (2011, 56 min)** — https://www.youtube.com/watch?v=me7Wm5LOpx0
  The classic story-rich Brahm talk: the demon that grows on anger and shrinks
  on kindness. Reach for it when you want the teaching carried by a story
  instead of an argument.
"""


def test_parse_index_two_entries():
    talks = build_shelf.parse_index(INDEX_SNIPPET)
    assert len(talks) == 2
    first, second = talks
    assert first["slug"] == "patience"
    assert first["title"] == "Patience"
    assert first["teacher"] == "Thanissaro Bhikkhu"
    assert first["source"] == "https://example.org/patience.html"
    assert first["themes"] == "patience, anger"
    assert second["slug"] == "anger-eating-demons"
    assert second["title"] == "Anger Eating Demons"
    assert second["source"] == "https://www.youtube.com/watch?v=me7Wm5LOpx0"


def test_reach_lines_extracts_sentence_keyed_by_url():
    reach = build_shelf.reach_lines(CURRICULUM_SNIPPET)
    assert (
        reach["https://example.org/patience.html"]
        == "Reach for it when practice feels like grim endurance."
    )
    # A sentence that wraps across lines is joined back together.
    assert reach["https://www.youtube.com/watch?v=me7Wm5LOpx0"] == (
        "Reach for it when you want the teaching carried by a story "
        "instead of an argument."
    )
    # The sutta entry has no reach line and stays out of the map.
    assert "https://example.org/sn36-6.html" not in reach


def test_md_to_html_heading_list_bold():
    html = build_shelf.md_to_html(
        "# Primer: Patience\n\nListen for **three things**.\n\n- one\n- two\n"
    )
    assert "<h3>Primer: Patience</h3>" in html
    assert "<strong>three things</strong>" in html
    assert "<ul>" in html and "<li>one</li>" in html and "<li>two</li>" in html
    assert "</ul>" in html


def test_md_to_html_escapes_script():
    html = build_shelf.md_to_html("hello <script>alert('x')</script> & goodbye")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp; goodbye" in html


def _make_library(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    (library / "INDEX.md").write_text(
        """# Library Index

## quiet-mind
- **Title:** Quiet Mind & <Friends>
- **Teacher:** Ajahn Test
- **Source:** https://example.org/quiet-mind.html
- **Themes:** calm, anger
- **Path:** library/quiet-mind/

## far-talk
- **Title:** Far Talk
- **Teacher:** Ajahn Test
- **Source:** https://example.org/far-talk.html
- **Themes:** patience
- **Path:** library/far-talk/

## demon-story
- **Title:** Demon Story
- **Teacher:** Ajahn Brahm
- **Source:** https://www.youtube.com/watch?v=me7Wm5LOpx0
- **Duration:** 56:04
- **Themes:** anger, stories
- **Path:** library/demon-story/

## bare-yt
- **Title:** Bare YT
- **Teacher:** Ajahn Test
- **Source:** https://youtu.be/abcdefUVWXY
- **Themes:** anger
- **Path:** library/bare-yt/
"""
    )
    quiet = library / "quiet-mind"
    quiet.mkdir()
    (quiet / "primer.mp3").write_bytes(b"\x00")
    (quiet / "audio.mp3").write_bytes(b"\x00")
    (quiet / "notes.md").write_text("# Notes\n\nWhat landed: **kindness** wins.\n")
    (quiet / "artifacts").mkdir()
    (quiet / "artifacts" / "breath-timer.html").write_text(
        "<!DOCTYPE html><html><body><h1>Breathe</h1></body></html>"
    )
    # A whisper-shaped transcript.json (extra keys ride along).
    (quiet / "transcript.json").write_text(
        json.dumps(
            {
                "text": "ignored",
                "segments": [
                    {"id": 0, "seek": 0, "start": 0.0, "end": 4.5,
                     "text": " Quiet begins & <opens>. ", "tokens": [1]},
                    {"id": 1, "start": 4.5, "end": 9.0, "text": "It settles."},
                ],
            }
        )
    )
    far = library / "far-talk"
    far.mkdir()
    (far / "transcript.md").write_text("# Far Talk\n\nWords.\n")
    (library / ".listening.jsonl").write_text(
        '{"slug": "quiet-mind", "at": "2026-06-30T10:00:00+00:00"}\n'
        "{torn line\n"
        '{"slug": "quiet-mind", "at": "2026-07-02T06:00:00+00:00"}\n'
    )
    demon = library / "demon-story"
    demon.mkdir()
    (demon / "thumbnail.jpg").write_bytes(b"\xff\xd8\xff")
    # A captions-shaped transcript.json (bare start/end/text).
    (demon / "transcript.json").write_text(
        json.dumps({"segments": [{"start": 12.0, "end": 15.5, "text": "the demon arrives"}]})
    )
    return library


def test_render_shelf_end_to_end(tmp_path):
    library = _make_library(tmp_path)
    html = build_shelf.render_shelf(
        library, {"https://example.org/quiet-mind.html": "Reach for it when testing."}
    )
    # Card title is HTML-escaped.
    assert "Quiet Mind &amp; &lt;Friends&gt;" in html
    assert "Quiet Mind & <Friends>" not in html
    # Primer audio with a relative src, labeled for the guide's voice.
    assert 'src="quiet-mind/primer.mp3"' in html
    assert "Primer — 1 min, spoken by the guide" in html
    # Notes made it in, rendered and escaped.
    assert "<strong>kindness</strong> wins." in html
    # The reach line shows for the matched talk.
    assert "Reach for it when testing." in html


def test_render_shelf_talk_without_audio_gets_source_link(tmp_path):
    library = _make_library(tmp_path)
    html = build_shelf.render_shelf(library, {})
    # far-talk has no primer.mp3 and no audio.* — no audio tag points at it.
    assert 'src="far-talk/' not in html
    assert 'href="https://example.org/far-talk.html"' in html
    assert "Listen at the source" in html
    # Its transcript is linked relatively.
    assert 'href="far-talk/transcript.md"' in html


def test_render_shelf_includes_chat_panel_hidden_by_default(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The panel exists but starts hidden; it only appears when the served
    # shelf's /health check succeeds — the static file:// shelf is unchanged.
    assert 'id="guide-chat"' in html
    assert "hidden" in html
    assert "/health" in html
    assert "/api/chat" in html
    assert "the guide" in html.lower()


def test_chat_js_renders_replies_as_text_never_html(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Model output must be rendered inert: textContent + pre-wrap only.
    assert "textContent" in html
    assert "innerHTML" not in html


def test_chat_panel_has_brain_toggle_pills(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    assert 'data-brain="claude"' in html
    assert 'data-brain="ollama"' in html
    assert "claude · deep" in html
    assert "ollama · offline" in html


def test_chat_js_has_safe_rich_renderer_and_history_restore(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Completed bubbles are dressed by the DOM-only mini-markdown renderer;
    # earlier turns come back from the server. Still never innerHTML.
    assert "renderRich" in html
    assert "createTextNode" in html
    assert "/api/history" in html
    assert "innerHTML" not in html


def test_render_shelf_transcript_renders_inline_and_scrollable(tmp_path):
    library = _make_library(tmp_path)
    html = build_shelf.render_shelf(library, {})
    # The transcript body is rendered into the details (formatted, escaped)
    # inside a scrollable box — not just linked out to the raw file.
    assert "scroll-box" in html
    assert "<h3>Far Talk</h3>" in html
    assert "<p>Words.</p>" in html
    # The raw file stays one click away.
    assert 'href="far-talk/transcript.md"' in html
    assert "open raw file" in html


# --- parse_study + the path strip -----------------------------------------

STUDY_SNIPPET = """# Study Memory

## Where we are
- Root cluster: anger, aversion, patience.

## Studied
- **Patience** (Thanissaro Bhikkhu, 2026-06-12): not grim endurance;
  the carpenter's adze-handle image for invisible progress.

## Queued
- **Anger Eating Demons (Ajahn Brahm)** — primer ready: see
  library/anger-eating-demons/.
- Dealing with people that irritate us (Ajahn Brahm, 4 min): light taster.

## Open questions
- Eightfold Path without feeling dumb for forgetting.
"""


def test_parse_study_pulls_studied_and_queued_names():
    path = build_shelf.parse_study(STUDY_SNIPPET)
    assert path["studied"] == ["Patience"]
    # A bold span names the item; a plain one falls back to pre-colon text.
    assert path["queued"] == [
        "Anger Eating Demons (Ajahn Brahm)",
        "Dealing with people that irritate us (Ajahn Brahm, 4 min)",
    ]


def test_parse_study_ignores_other_sections_and_wrapped_lines():
    path = build_shelf.parse_study(STUDY_SNIPPET)
    flat = path["studied"] + path["queued"]
    assert not any("Root cluster" in name for name in flat)
    assert not any("Eightfold" in name for name in flat)
    assert not any("adze-handle" in name for name in flat)  # continuation line


def test_parse_study_tolerates_missing_sections_and_empty_text():
    empty = {"studied": [], "queued": [], "parked": []}
    assert build_shelf.parse_study("") == empty
    assert build_shelf.parse_study("# Just a title\n\nprose\n") == empty
    assert build_shelf.parse_study("## Queued\n- **Next Talk** — soon.\n") == {
        "studied": [],
        "queued": ["Next Talk"],
        "parked": [],
    }


def test_parse_study_sets_parked_queued_items_aside():
    text = """## Studied
- **Patience**: landed; we parked the sutta question for later.

## Queued
- **Anger Issues (Thanissaro Bhikkhu)** — next up; not in the library yet.
- **Anger Eating Demons (Ajahn Brahm)** — parked, no obligation: most of
  it heard, it can call back whenever.
- **Sparked Joy** — the word inside another word does not count.
"""
    path = build_shelf.parse_study(text)
    # "parked" in a queued item's note moves it aside — a queued state...
    assert path["parked"] == ["Anger Eating Demons (Ajahn Brahm)"]
    assert path["queued"] == [
        "Anger Issues (Thanissaro Bhikkhu)",
        "Sparked Joy",
    ]
    # ...but a studied talk mentioning the word stays studied.
    assert path["studied"] == ["Patience"]


def test_render_shelf_shows_path_strip_when_study_md_exists(tmp_path):
    library = _make_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(STUDY_SNIPPET)
    html = build_shelf.render_shelf(library, {})
    assert "The path" in html
    assert "✓ Patience" in html
    assert "→ Anger Eating Demons (Ajahn Brahm)" in html
    assert "→ Dealing with people that irritate us (Ajahn Brahm, 4 min)" in html


def test_render_shelf_omits_path_strip_without_study_md(tmp_path):
    library = _make_library(tmp_path)  # no STUDY.md next to library/
    html = build_shelf.render_shelf(library, {})
    assert "The path" not in html
    assert 'class="path-strip"' not in html
    # An empty STUDY.md is treated the same (static shareability).
    (tmp_path / "STUDY.md").write_text("# Study Memory\n")
    html = build_shelf.render_shelf(library, {})
    assert 'class="path-strip"' not in html


def test_render_shelf_path_strip_escapes_names(tmp_path):
    library = _make_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(
        "## Studied\n- **Quiet <Talk> & Friends**: done.\n"
    )
    html = build_shelf.render_shelf(library, {})
    assert "✓ Quiet &lt;Talk&gt; &amp; Friends" in html
    assert "<Talk>" not in html


# --- the sidebar IS the path (merged talks list) ----------------------------


def test_normalize_title_tolerates_suffixes():
    nt = build_shelf.normalize_title
    # STUDY.md's parenthetical suffixes and INDEX's "| Teacher" tails both
    # collapse away, so the two spellings of one talk meet in the middle.
    assert nt("Anger Eating Demons (Ajahn Brahm)") == nt("Anger Eating Demons")
    assert nt("Dealing with people that irritate us | Ajahn Brahm") == nt(
        "Dealing with people that irritate us (Ajahn Brahm, 4 min)"
    )
    assert nt("Patience") == "patience"
    assert nt("Quiet Mind & <Friends>") == "quiet mind friends"
    assert nt("") == ""


def test_talk_states_maps_slugs_and_surfaces_unfetched():
    talks = [
        {"slug": "quiet-mind", "title": "Quiet Mind & <Friends>"},
        {"slug": "far-talk", "title": "Far Talk"},
        {"slug": "demon-story", "title": "Demon Story"},
    ]
    path = {
        "studied": ["Quiet Mind & <Friends> (Ajahn Test)"],
        "queued": [
            "Far Talk (Ajahn Test, 4 min)",
            "Anger Issues (Thanissaro Bhikkhu, 2019)",
        ],
        "parked": ["Demon Story (Ajahn Brahm)"],
    }
    states, unfetched = build_shelf.talk_states(path, talks)
    assert states == {
        "quiet-mind": "studied",
        "far-talk": "queued",
        "demon-story": "parked",
    }
    # A queued talk with no library match is the visible path ahead.
    assert unfetched == ["Anger Issues (Thanissaro Bhikkhu, 2019)"]
    # No STUDY.md: everything unmarked, nothing phantom.
    empty = {"studied": [], "queued": [], "parked": []}
    assert build_shelf.talk_states(empty, talks) == ({}, [])


SIDEBAR_STUDY = """# Study Memory

## Studied
- **Quiet Mind & <Friends>** (Ajahn Test): landed.

## Queued
- **Far Talk (Ajahn Test)** — next up.
- **Anger Issues (Thanissaro Bhikkhu, 2019)** — not in the library yet.
- **Demon Story (Ajahn Brahm)** — parked, no obligation.
"""


def test_sidebar_talks_list_is_the_path(tmp_path):
    library = _make_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(SIDEBAR_STUDY)
    html = build_shelf.render_shelf(library, {})
    sidebar = re.search(r'<nav id="sidebar">.*?</nav>', html, re.S).group(0)
    # State marks ride inline on the talk entries.
    quiet = re.search(r'<li><a href="#talk/quiet-mind">.*?</a></li>', sidebar, re.S).group(0)
    assert '<span class="nav-state nav-done">✓</span>' in quiet
    far = re.search(r'<li><a href="#talk/far-talk">.*?</a></li>', sidebar, re.S).group(0)
    assert '<span class="nav-state nav-next">→</span>' in far
    demon = re.search(r'<li><a href="#talk/demon-story">.*?</a></li>', sidebar, re.S).group(0)
    assert '<span class="nav-tag">parked</span>' in demon
    # A queued talk not yet in the library appears muted and unclickable.
    # No curriculum in this fixture, so no URL is known anywhere for it.
    unfetched = re.search(r'<li class="nav-unfetched">.*?</li>', sidebar, re.S).group(0)
    assert "Anger Issues (Thanissaro Bhikkhu, 2019)" in unfetched
    assert "needs a URL — tell the guide" in unfetched
    assert "<a " not in unfetched
    # The separate sidebar path strip is gone — the list IS the path...
    assert 'class="path-strip"' not in sidebar
    assert "The path" not in sidebar
    # ...while the home view keeps its small summary strip.
    assert html.count('class="path-strip"') == 1


def test_sidebar_without_study_md_is_unmarked(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    sidebar = re.search(r'<nav id="sidebar">.*?</nav>', html, re.S).group(0)
    assert "nav-state" not in sidebar
    assert "nav-unfetched" not in sidebar
    assert 'href="#talk/quiet-mind"' in sidebar  # talks still listed


def test_sidebar_escapes_unfetched_names(tmp_path):
    library = _make_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(
        "## Queued\n- **Sneaky <Talk> & Co** — not here yet.\n"
    )
    html = build_shelf.render_shelf(library, {})
    assert "Sneaky &lt;Talk&gt; &amp; Co" in html
    assert "<Talk>" not in html


# --- youtube_embed_url ------------------------------------------------------


def test_youtube_embed_url_watch_form():
    assert build_shelf.youtube_embed_url(
        "https://www.youtube.com/watch?v=me7Wm5LOpx0"
    ) == "https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"
    # Without the www, and over plain http, still recognized.
    assert build_shelf.youtube_embed_url(
        "http://youtube.com/watch?v=Haj6wtNSP2k"
    ) == "https://www.youtube-nocookie.com/embed/Haj6wtNSP2k"


def test_youtube_embed_url_youtu_be_form():
    assert build_shelf.youtube_embed_url(
        "https://youtu.be/me7Wm5LOpx0"
    ) == "https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"


def test_youtube_embed_url_survives_extra_params():
    # The video id is picked out; timestamps and share cruft are dropped.
    assert build_shelf.youtube_embed_url(
        "https://www.youtube.com/watch?v=me7Wm5LOpx0&t=120s"
    ) == "https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"
    assert build_shelf.youtube_embed_url(
        "https://www.youtube.com/watch?t=120s&v=me7Wm5LOpx0"
    ) == "https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"
    assert build_shelf.youtube_embed_url(
        "https://youtu.be/me7Wm5LOpx0?si=AbCd_123"
    ) == "https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"


def test_youtube_embed_url_non_youtube_is_none():
    assert build_shelf.youtube_embed_url("https://example.org/patience.html") is None
    assert build_shelf.youtube_embed_url("https://vimeo.com/12345") is None
    # YouTube pages that are not a single video get no embed either.
    assert build_shelf.youtube_embed_url("https://www.youtube.com/@AjahnBrahm") is None
    assert build_shelf.youtube_embed_url("") is None


# --- iteration 4: embedded player + two-pane layout -------------------------


def test_render_shelf_youtube_talk_gets_click_to_load_embed(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The demon-story talk (YouTube source, no local audio) gets a calm
    # click-to-load button instead of a navigate-away link.
    assert "Play here" in html
    assert 'data-embed="https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"' in html
    # No separate "open on YouTube" anchor: the embedded player's own
    # logo link covers that — ours was redundant chrome.
    assert "open on YouTube" not in html
    assert "yt-link" not in html
    # No iframe in the static page: nothing loads until the user asks.
    assert "<iframe" not in html


def test_render_shelf_non_youtube_source_never_navigates_away(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # far-talk keeps its source link, but it opens in a new tab now.
    link = re.search(
        r'<a class="source-link"[^>]*href="https://example.org/far-talk.html"[^>]*>',
        html,
    )
    assert link, "far-talk source link missing"
    assert 'target="_blank"' in link.group(0)
    assert 'rel="noopener"' in link.group(0)


def test_render_shelf_sidebar_lists_each_talk(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    sidebar = re.search(r'<nav id="sidebar">.*?</nav>', html, re.S)
    assert sidebar, "sidebar nav missing"
    for title, slug in [
        ("Quiet Mind &amp; &lt;Friends&gt;", "quiet-mind"),
        ("Far Talk", "far-talk"),
        ("Demon Story", "demon-story"),
    ]:
        assert title in sidebar.group(0)
        assert f'href="#talk/{slug}"' in sidebar.group(0)
    # The sidebar also carries the epigraph and the "begin here" link to
    # the intro room, above the talks.
    assert "The second arrow is optional." in sidebar.group(0)
    assert re.search(r'<a class="begin-link" href="#home">begin here</a>', sidebar.group(0))
    # Sessions are invisible infrastructure now: no sidebar section.
    assert "sessions-section" not in sidebar.group(0)
    assert "session-list" not in sidebar.group(0)


def test_render_shelf_hash_views_present(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # One full-pane view per talk, plus the home/welcome view, routed by a
    # tiny hashchange handler (CSS :target can't also highlight the nav).
    assert 'id="talk-quiet-mind"' in html
    assert 'id="talk-far-talk"' in html
    assert 'id="talk-demon-story"' in html
    assert 'id="view-home"' in html
    assert "hashchange" in html
    assert "Pick a talk from the sidebar" in html


def test_render_shelf_degrades_gracefully_without_js(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Views are hidden by a "js" class added at runtime — never by inline
    # style — so with JS off everything renders stacked and readable.
    assert 'classList.add("js")' in html
    assert ".js .view" in html
    assert 'style="' not in html  # no inline styles at all, hiding or otherwise
    # Every display:none rule for views is gated behind the runtime class.
    for match in re.finditer(r"([^{};]*)\{[^{}]*display:\s*none", html):
        selector = match.group(1)
        assert ".js" in selector or ".view" not in selector, selector


def test_chat_panel_is_one_continuous_guide(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Sessions are invisible infrastructure: the panel neither lists them
    # nor offers a "new conversation" — one guide, one stream.
    assert "/api/sessions" not in html
    assert "sessions-section" not in html
    assert "chat-new" not in html
    assert "new conversation" not in html
    # The conversation continues across refreshes: the current episode's
    # turns restore on load, and each turn's episode rides X-Session.
    assert "/api/history" in html
    assert "X-Session" in html
    # Every chat POST still carries the ambient view (the open talk).
    assert "currentView" in html


def test_home_view_is_the_intro_room(tmp_path):
    library = _make_library(tmp_path)
    html = build_shelf.render_shelf(library, {})
    home = re.search(r'<section class="card view" id="view-home">.*?</section>', html, re.S)
    assert home, "home view missing"
    assert "Begin here" in home.group(0)
    assert "The second arrow is optional." in home.group(0)
    # The short "how this room works" lines, in the project's calm voice.
    for line in (
        "the guide comes with you",
        "your place is kept",
        "transcript follows the voice",
        "Interactive",
        "it remembers so you don't have to",
    ):
        assert line in home.group(0), line
    # The path summary strip stays on the home view.
    (tmp_path / "STUDY.md").write_text("## Studied\n- **Quiet Mind & <Friends>**: done.\n")
    html = build_shelf.render_shelf(library, {})
    home = re.search(r'<section class="card view" id="view-home">.*?</section>', html, re.S)
    assert 'class="path-strip"' in home.group(0)


def test_render_shelf_lists_artifacts_behind_the_sandbox_contract(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The talk card lists artifacts/*.html under the human label
    # "Interactive" (the folder and routes keep the artifact name).
    assert "<summary>Interactive</summary>" in html
    assert "<summary>Learning tools</summary>" not in html
    item = re.search(r'<li class="artifact-item"[^>]*>', html)
    assert item and 'data-slug="quiet-mind"' in item.group(0)
    assert 'data-name="breath-timer.html"' in item.group(0)
    # The static shelf shows a plain link (new tab, never navigates away)
    # plus a note that the sandboxed view needs the served shelf.
    link = re.search(
        r'<a class="artifact-open"[^>]*href="quiet-mind/artifacts/breath-timer.html"[^>]*>',
        html,
    )
    assert link and 'target="_blank"' in link.group(0)
    assert 'rel="noopener"' in link.group(0)
    assert "served shelf" in html  # the note
    # No iframe in the static HTML: the sandboxed view is mounted by JS
    # in served mode only, with allow-scripts and NEVER allow-same-origin.
    assert "<iframe" not in html
    assert '"sandbox", "allow-scripts"' in html
    assert "allow-same-origin" not in html
    assert "/artifacts/" in html  # the CSP-walled route the frames point at


def test_interactive_section_is_always_present_and_open(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Default-open on every talk card: interactivity is a first-class
    # part of a talk, not a drawer to discover.
    assert html.count("<details open><summary>Interactive</summary>") == 4
    # quiet-mind has artifacts: the list. The rest: one calm generator.
    buttons = re.findall(r'<button type="button" class="make-interactive" data-title="([^"]+)">', html)
    assert sorted(buttons) == ["Bare YT", "Demon Story", "Far Talk"]
    assert "✦ create interactive tools from this talk" in html


def test_chat_panel_has_the_ollama_model_picker(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # A calm select next to the pills; empty in the HTML (populated by JS
    # from /api/models in served mode) and hidden until the ollama pill
    # is active and the model list actually loaded.
    select = re.search(r'<select id="chat-model"[^>]*>\s*</select>', html)
    assert select and "hidden" in select.group(0)
    assert "/api/models" in html
    # Picking a model announces itself with a quiet system line.
    assert "ollama model:" in html


def test_shelf_js_still_never_uses_innerhtml_for_iframe(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The player iframe is built with createElement + setAttribute.
    assert "createElement" in html
    assert "setAttribute" in html
    assert "innerHTML" not in html


def test_inline_scripts_parse_with_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "no inline scripts found"
    for i, script in enumerate(scripts):
        js = tmp_path / f"inline-{i}.js"
        js.write_text(script)
        result = subprocess.run(
            ["node", "--check", str(js)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


# --- the listening room: thumbnails, resume positions, transcript player -----


def test_normalize_segments_accepts_whisper_and_captions_shapes():
    whisper = {
        "text": "all of it",
        "segments": [
            {"id": 0, "seek": 0, "start": 0.0, "end": 11.24, "text": " Patience is… ",
             "tokens": [1, 2], "temperature": 0.0},
        ],
    }
    captions = {"segments": [{"start": 2, "end": 4.5, "text": "about anger"}]}
    assert build_shelf.normalize_segments(whisper) == [
        {"start": 0.0, "end": 11.24, "text": "Patience is…"}
    ]
    assert build_shelf.normalize_segments(captions) == [
        {"start": 2.0, "end": 4.5, "text": "about anger"}
    ]
    # Junk-tolerant: missing text/start, wrong types, non-dicts all drop out.
    junk = {"segments": [
        {"start": 1}, {"text": "no start"}, {"start": "x", "text": "y"},
        "nope", {"start": 3, "end": None, "text": "end optional"},
    ]}
    assert build_shelf.normalize_segments(junk) == [
        {"start": 3.0, "end": 3.0, "text": "end optional"}
    ]
    assert build_shelf.normalize_segments(None) == []
    assert build_shelf.normalize_segments([1, 2]) == []


def test_format_time_mm_ss_and_hours():
    fmt = build_shelf.format_time
    assert fmt(0) == "0:00"
    assert fmt(65.4) == "1:05"
    assert fmt(3725) == "1:02:05"


def test_youtube_thumbnail_becomes_the_placeholder(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # demon-story has thumbnail.jpg: the placeholder is the local image
    # with a play glyph and the talk duration (from INDEX) overlaid...
    thumb = re.search(r'<button type="button" class="yt-play yt-thumb">.*?</button>', html, re.S)
    assert thumb, "thumbnail play button missing"
    assert '<img src="demon-story/thumbnail.jpg"' in thumb.group(0)
    assert 'class="yt-glyph"' in thumb.group(0)
    assert '<span class="yt-duration">56:04</span>' in thumb.group(0)
    assert "Play here" not in thumb.group(0)
    # ...while bare-yt (no thumbnail) keeps the plain button.
    bare = html[html.index('data-slug="bare-yt"'):]
    assert "Play here ▸" in bare[:600]
    # Both carry data-slug for resume positions; noopener links stay.
    assert re.search(r'<div class="yt-embed"[^>]*data-slug="demon-story"', html)
    assert 'rel="noopener"' in html


def test_transcript_player_renders_segments_with_data_start(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # quiet-mind (whisper transcript.json + audio.mp3): segment paragraphs.
    box = re.search(
        r'<div class="scroll-box seg-transcript" data-slug="quiet-mind">.*?</div>',
        html, re.S,
    )
    assert box, "segmented transcript missing"
    seg = re.search(r'<p class="seg" data-start="0">.*?</p>', box.group(0), re.S)
    assert seg
    assert '<span class="seg-time">0:00</span>' in seg.group(0)
    # Segment text is escaped.
    assert "Quiet begins &amp; &lt;opens&gt;." in box.group(0)
    assert "<opens>" not in box.group(0)
    assert 'data-start="4.5"' in box.group(0)
    # The raw file stays a click away; the YouTube talk gets segments too.
    assert 'href="quiet-mind/transcript.md"' in html
    assert re.search(r'seg-transcript" data-slug="demon-story"', html)
    assert 'data-start="12"' in html
    # far-talk has only transcript.md: the plain rendering remains.
    assert "<h3>Far Talk</h3>" in html


def test_talk_audio_is_tagged_for_resume(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    audio = re.search(r"<audio[^>]*src=\"quiet-mind/audio.mp3\"[^>]*>", html)
    assert audio
    assert 'class="talk-audio"' in audio.group(0)
    assert 'data-slug="quiet-mind"' in audio.group(0)
    # The primer player is NOT position-tracked.
    primer = re.search(r"<audio[^>]*src=\"quiet-mind/primer.mp3\"[^>]*>", html)
    assert primer and "talk-audio" not in primer.group(0)


def test_listening_room_js_markers(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Positions live in localStorage under sa-pos-<slug>, never sent out.
    assert "sa-pos-" in html
    assert "localStorage" in html
    # YouTube resume: jsapi handshake + infoDelivery tracking + &start=.
    assert "enablejsapi=1" in html
    assert '"listening"' in html or "'listening'" in html
    assert "infoDelivery" in html
    assert "&start=" in html
    # Still no innerHTML anywhere (covered elsewhere too, cheap here).
    assert "innerHTML" not in html


# --- iteration 10 addenda: curriculum room, richer md, anchored input --------


def test_md_to_html_renders_blockquotes():
    html = build_shelf.md_to_html(
        "Before.\n\n> Don't just look at the two bad bricks.\n> Look at the wall.\n\nAfter.\n"
    )
    assert "<blockquote>" in html and "</blockquote>" in html
    quote = re.search(r"<blockquote>.*?</blockquote>", html, re.S).group(0)
    assert "two bad bricks" in quote and "Look at the wall." in quote
    assert "&gt; Don" not in html  # the marker is consumed, not shown
    # Escaping still applies inside quotes.
    assert "<script>" not in build_shelf.md_to_html("> <script>x</script>\n")


def test_md_to_html_renders_numbered_lists():
    html = build_shelf.md_to_html("Steps:\n\n1. breathe in\n2. breathe out\n\nDone.\n")
    assert "<ol>" in html and "</ol>" in html
    assert "<li>breathe in</li>" in html
    assert "<li>breathe out</li>" in html
    # Dashed lists still work beside them.
    both = build_shelf.md_to_html("- a\n- b\n\n1. one\n")
    assert "<ul>" in both and "<ol>" in both


CURRICULUM_CLUSTER = """# Cluster 1: Anger & the Second Arrow

## Talks

- **Quiet Mind & <Friends> — Ajahn Test** — https://example.org/quiet-mind.html
  Already on the shelf. Reach for it when testing.

- **Somewhere Else — Ajahn Away** — https://example.org/elsewhere.html
  Not fetched yet; a fine next step.
"""


def test_curriculum_room_renders_with_shelf_crosslinks(tmp_path):
    library = _make_library(tmp_path)
    curriculum = tmp_path / "curriculum"
    curriculum.mkdir()
    (curriculum / "01-anger.md").write_text(CURRICULUM_CLUSTER)
    (curriculum / "README.md").write_text("# not rendered\n")
    html = build_shelf.render_shelf(library, {})
    # The room exists: a view plus a sidebar link below "begin here".
    assert 'id="view-curriculum"' in html
    sidebar = re.search(r'<nav id="sidebar">.*?</nav>', html, re.S).group(0)
    assert re.search(r'href="#curriculum"', sidebar)
    view = re.search(
        r'<section class="card view" id="view-curriculum">.*?</section>', html, re.S
    ).group(0)
    # A cluster section, escaped like everything human-facing.
    assert "Cluster 1: Anger &amp; the Second Arrow" in view
    assert "Quiet Mind &amp; &lt;Friends&gt;" in view
    # The in-library entry cross-links to its talk view...
    assert re.search(r'<a class="cur-onshelf" href="#talk/quiet-mind">on your shelf', view)
    # ...the unfetched one keeps its external link (noopener) + a hint.
    ext = re.search(r'<a [^>]*href="https://example.org/elsewhere.html"[^>]*>', view)
    assert ext and 'rel="noopener"' in ext.group(0) and 'target="_blank"' in ext.group(0)
    assert "ask the guide to fetch it" in view
    # README stays machine-layer.
    assert "not rendered" not in view


def test_curriculum_room_absent_without_files(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    assert 'id="view-curriculum"' not in html
    assert 'href="#curriculum"' not in html


def test_chat_tray_is_one_immutable_fixture(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # ONE tray node, fixed to the viewport bottom of the main pane, the
    # same in every state and room — conversation stretches the SAME
    # layer upward; the bar itself never moves.
    assert html.count('id="guide-chat"') == 1
    assert "#guide-chat { position: fixed; left: 260px; right: 0; bottom: 0;" in html
    assert "#guide-chat.chat-conversation { top: 0;" in html
    # Content scrolls beneath with room to spare — never occluded.
    assert re.search(r"main \{[^}]*11rem", html)
    # Click-through outside the bar: the layer itself takes no events.
    assert "pointer-events: none" in html and "pointer-events: auto" in html


def test_chat_focus_typing_is_intent_never_steal(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Idle typing lands in the guide's textarea; "/" focuses without
    # inserting itself; Escape hands the keys back to the page.
    assert "typing is intent" in html
    assert 'document.addEventListener("keydown"' in html
    assert "input.blur()" in html
    # No autofocus without intent: exactly three focus calls — slash,
    # type-to-focus (both explicit keystrokes), and the after-send
    # refocus (that IS user intent). Nothing focuses on load, and no
    # focus ever moves the viewport (the reply streams into the message
    # list's own scroll container; the page stays where the user left it).
    assert "autofocus" not in html
    assert html.count("input.focus({ preventScroll: true })") == 3
    assert "input.focus()" not in html


# --- iteration 11a: reflections flow from practice to guide ------------------


def test_reflection_chip_markup_is_quiet_and_consent_first(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # A hidden chip near the input; nothing persists, nothing auto-sends.
    chip = re.search(r'<div id="reflection-chip" hidden>.*?</div>', html, re.S)
    assert chip, "reflection chip missing"
    assert 'id="reflection-send"' in chip.group(0)
    assert 'id="reflection-dismiss"' in chip.group(0)
    # The chip label and composed message are set via textContent only.
    assert "hand it to the guide" in html
    assert '"From my practice in "' in html
    assert "innerHTML" not in html


def test_reflection_listener_trusts_only_our_frames_and_slug(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Identity is the mounted iframe's contentWindow (sandbox = null
    # origin), and the slug comes from OUR data-slug — the message's own
    # claims are never used for routing.
    assert "toolFrames" in html
    assert "event.source" in html
    assert "event.data.slug" not in html
    assert "second-arrow:reflection" in html


def test_reflection_validator_matrix_runs_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    fn = re.search(r"function validReflection\(data\) \{[\s\S]*?\n  \}", html)
    assert fn, "validReflection missing"
    harness = fn.group(0) + """
var cases = [
  [{type:"second-arrow:reflection", name:"t.html", prompt:"p", text:"hello"}, true],
  [{type:"reflection", name:"t.html", prompt:"p", text:"hello"}, false],
  [{name:"t.html", prompt:"p", text:"hello"}, false],
  [{type:"second-arrow:reflection", prompt:"p", text:"hello"}, false],
  [{type:"second-arrow:reflection", name:7, prompt:"p", text:"hello"}, false],
  [{type:"second-arrow:reflection", name:"t.html", text:"hello"}, false],
  [{type:"second-arrow:reflection", name:"t.html", prompt:"p"}, false],
  [{type:"second-arrow:reflection", name:"t.html", prompt:"p", text:"   "}, false],
  [{type:"second-arrow:reflection", name:"t.html", prompt:"p", text:"x".repeat(4001)}, false],
  [{type:"second-arrow:reflection", name:"t.html", prompt:"p".repeat(301), text:"hi"}, false],
  [{type:"second-arrow:reflection", name:"t.html", prompt:"p", text:"x".repeat(4000)}, true],
  [{type:"second-arrow:reflection", name:"t.html", prompt:"", text:"hi"}, true],
  [null, false],
  ["string", false],
  [42, false],
];
for (var i = 0; i < cases.length; i++) {
  if (!!validReflection(cases[i][0]) !== cases[i][1]) {
    console.error("case " + i + " wrong");
    process.exit(1);
  }
}
console.log("matrix ok");
"""
    js = tmp_path / "validator.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "matrix ok" in result.stdout


def test_reflection_send_reuses_the_chat_send_path(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # One send path: the chip composes a message and calls the same
    # sendMessage the form uses — a draft in the input is never clobbered.
    assert "function sendMessage(text)" in html
    assert html.count("sendMessage(") >= 3  # definition + form + chip


# --- iteration 11b: docked/open/full guide; guide-offered navigation ---------


def test_chat_panel_is_binary_docked_or_conversation(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Docked is the calm default, set in the static markup itself: either
    # you are talking or you are looking at the page — nothing in between.
    assert re.search(r'<section class="chat-docked" id="guide-chat" hidden>', html)
    assert "chat-toggle" not in html  # the unintuitive bar toggle is gone
    assert "chat-expand" not in html  # no middle state, no second control
    assert "chat-full" not in html  # (chat-open is now the opener BUTTON id)
    assert 'panel.classList.remove("chat-docked", "chat-conversation");' in html
    # One state function; opening is deliberate (bubble icon or peek) —
    # sending from docked stays in the room (the peek carries the reply).
    assert "function setChatState(next)" in html
    assert 'setChatState("conversation"); // open without sending' in html
    assert 'setChatState("conversation"); // the full exchange, deliberately' in html
    # Escape (and the toggle) drop straight back to the page.
    assert 'setChatState("docked");' in html
    # Docked hides the stream; conversation fills the pane generously,
    # overlaying (views hidden, never unmounted — audio keeps playing).
    assert ".chat-docked #chat-messages" in html
    assert "#guide-chat.chat-conversation" in html


def test_reflection_chip_is_gone_when_empty(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The chip starts hidden AND its flex display must not defeat the
    # hidden attribute (the empty-dashed-pill bug seen live).
    assert re.search(r"#reflection-chip\[hidden\] \{ display: none", html)
    # It only ever shows with non-empty reflection text in hand.
    assert "reflections[from.slug]" in html


def test_action_cue_parser_matrix_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    fn = re.search(r"function parseActionCue\(text\) \{[\s\S]*?\n  \}", html)
    assert fn, "parseActionCue missing"
    harness = """
var elements = {
  "talk-patience": { getAttribute: function () { return "232"; } },
  "talk-demon-story": { getAttribute: function () { return null; } },
  "view-curriculum": { getAttribute: function () { return null; } },
};
var document = { getElementById: function (id) { return elements[id] || null; } };
""" + fn.group(0) + r"""
function check(i, got, wantText, wantAction) {
  var gotAction = JSON.stringify(got.action);
  if (got.text !== wantText || gotAction !== JSON.stringify(wantAction)) {
    console.error("case " + i, got.text, gotAction);
    process.exit(1);
  }
}
check(0, parseActionCue("Going.\n[[go: talk/patience]]"), "Going.",
  { kind: "go", target: "#talk/patience", slug: "patience" });
check(1, parseActionCue("Road ahead.\n[[go: curriculum]]"), "Road ahead.",
  { kind: "go", target: "#curriculum", label: "the curriculum" });
check(2, parseActionCue("Start.\n[[go: home]]"), "Start.",
  { kind: "go", target: "#home", label: "the beginning" });
check(3, parseActionCue("The eggs story.\n[[seek: patience 130]]"), "The eggs story.",
  { kind: "seek", slug: "patience", seconds: 130 });
check(4, parseActionCue("Past the end.\n[[seek: patience 500]]"), "Past the end.", null);
check(5, parseActionCue("No duration known.\n[[seek: demon-story 3000]]"), "No duration known.",
  { kind: "seek", slug: "demon-story", seconds: 3000 });
check(6, parseActionCue("Unknown talk.\n[[seek: nope 10]]"), "Unknown talk.", null);
check(7, parseActionCue("Rest.\n[[pause]]"), "Rest.", { kind: "pause" });
check(8, parseActionCue("On.\n[[play]]"), "On.", { kind: "play" });
check(9, parseActionCue("A [[seek: patience 10]] mid-text.\nMore."), "A mid-text.\nMore.", null);
check(10, parseActionCue("Bad.\n[[go: javascript:alert(1)]]"), "Bad.", null);
check(11, parseActionCue("Plain reply."), "Plain reply.", null);
check(12, parseActionCue("Junk args.\n[[pause: now]]"), "Junk args.", null);
check(13, parseActionCue("Neg.\n[[seek: patience -5]]"), "Neg.", null);
console.log("cue matrix ok");
"""
    js = tmp_path / "cues.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "cue matrix ok" in result.stdout


def test_locked_cues_become_offers_not_actions(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Unlocked: the cue executes through the shared executor and announces.
    assert "window.saExecuteCue" in html
    assert '"— the guide took you to "' in html
    assert '"— the guide jumped to "' in html
    # Locked: the same cue renders the old offer button instead — and
    # when docked, the offer ALSO lands in the peek, where the user is
    # (the message stream is hidden there).
    assert "window.saCueLocked" in html
    assert "offerAction(pending, cue.action)" in html
    assert "offerAction(peekAction, cue.action)" in html
    assert 'id="peek-action"' in html
    assert '" — go?"' in html
    assert "innerHTML" not in html


def test_chat_bubbles_carry_avatars_and_run_labels(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Inline-SVG avatars live in static templates (cloned per message —
    # never built from message content): a bodhi leaf for the guide (an
    # enso read as a loading spinner at bubble size — no rings, ever),
    # a small person for the user.
    guide = re.search(r'<template id="avatar-guide">\s*<svg.*?</template>', html, re.S)
    assert guide and guide.group(0).count("<path") == 2  # outline + vein
    assert "<circle" not in guide.group(0)  # nothing ring-shaped
    assert re.search(r'<template id="avatar-user">\s*<svg', html)
    assert "cloneNode(true)" in html
    # The real thinking indicator stays text in the bubble, never a ring.
    assert '"thinking…"' in html and "chat-thinking" in html
    # Speaker labels appear once per run of same-speaker messages.
    assert '"the guide"' in html and '"you"' in html
    assert "chat-run-start" in html
    assert "chat-label" in html
    # System lines stay centered and unbubbled (no row/avatar).
    assert "chat-system" in html


# --- iteration 11c: now playing — one voice, visible handle -------------------


def test_now_playing_capsule_markup(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    capsule = re.search(r'<div id="now-playing" hidden>.*?</div>', html, re.S)
    assert capsule, "capsule missing"
    # Three explicit controls + the navigating body; tooltips on all.
    for control in ("np-body", "np-play", "np-stop", "np-expand"):
        assert f'id="{control}"' in capsule.group(0)
    assert capsule.group(0).count('title="') >= 3
    # The chip lesson, applied: hidden must beat the flex display.
    assert re.search(r"#now-playing\[hidden\] \{ display: none", html)
    # Fixed top-right, above the conversation overlay (z 5 over z 4),
    # far from the input row at the bottom.
    assert re.search(r"#now-playing \{ position: fixed; top:", html)
    assert "z-index: 5" in html


def test_one_voice_at_a_time(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Starting any talk pauses every other: local audio directly, YouTube
    # through the jsapi command channel we already listen on.
    assert "function pauseOthers(slug)" in html
    assert '"pauseVideo"' in html
    assert '"playVideo"' in html
    # Stop pauses and clears the handle — never reloads/destroys the
    # iframe (position is already saved by the resume feature).
    assert "nowPlaying = null" in html


def test_capsule_visibility_predicate_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    fn = re.search(r"function capsuleVisible\([\s\S]*?\n  \}", html)
    assert fn, "capsuleVisible missing"
    harness = fn.group(0) + r"""
var playing = { slug: "patience" };
function check(i, got, want) {
  if (got !== want) { console.error("case " + i); process.exit(1); }
}
check(0, capsuleVisible(null, "#home", false), false);        // nothing playing
check(1, capsuleVisible(playing, "#home", false), true);      // other room
check(2, capsuleVisible(playing, "#talk/patience", false), false); // own room
check(3, capsuleVisible(playing, "#talk/patience", true), true);   // own room COVERED by chat
check(4, capsuleVisible(playing, "#talk/other", true), true);  // chat + other room
check(5, capsuleVisible(playing, "#curriculum", false), true);
console.log("predicate ok");
"""
    js = tmp_path / "capsule.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "predicate ok" in result.stdout
    # Opening/closing the conversation re-evaluates the capsule at once.
    assert "window.saUpdateCapsule = updateCapsule" in html
    assert "if (window.saUpdateCapsule) window.saUpdateCapsule();" in html
    # YouTube with a mute command channel: hide play/pause, keep the
    # capsule navigating (degrade, never a broken-looking control).
    assert "ytInfo" in html


def test_playing_embed_survives_room_changes(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Navigation must never interrupt playback: the actively-playing
    # talk's view is parked offscreen (still rendered) instead of
    # display:none — only that one, with no layout side effects.
    assert "function keepPlayingViewAlive()" in html
    assert re.search(r"\.js \.view\.audible \{ display: block; position: fixed;\s*left: -10000px", html)
    assert "pointer-events: none" in html
    # The one-voice rule fires only when a NEW talk starts (mount/play) —
    # never from the hash router.
    show = re.search(r"function show\(\) \{[\s\S]*?\n  \}", html).group(0)
    assert "pauseOthers" not in show
    assert "keepPlayingViewAlive();" in show


def test_conversation_overlay_has_a_visible_way_down(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # A clearly-labeled minimize pill, pinned top-right of the overlay
    # (it does not scroll with the list), same action as Escape.
    assert 'id="chat-minimize"' in html
    assert "▾ back to the room" in html
    assert re.search(r"#chat-minimize \{ display: none", html)  # docked: hidden
    assert ".chat-conversation #chat-minimize" in html  # conversation: pinned
    # The now-playing capsule steps down in conversation mode so both the
    # way down and the way to the talk stay visible, never overlapping.
    assert ".chat-conversation-mode #now-playing" in html


def test_chat_bar_is_a_modern_capsule(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Send is an accent-filled circular button with an inline-SVG arrow,
    # labeled for a11y, and disabled until there is something to send.
    send = re.search(r'<button type="submit" id="chat-send"[^>]*>', html)
    assert send, "send button missing"
    assert 'title="Send"' in send.group(0)
    assert 'aria-label="Send"' in send.group(0)
    assert "disabled" in send.group(0)
    assert re.search(r'id="chat-send"[^>]*>\s*<svg', html)
    assert "function updateSendState()" in html  # empty input keeps it dim
    # Opening without sending: a quiet chat-bubble icon-button on the bar.
    opener = re.search(r'<button type="button" id="chat-open"[^>]*>', html)
    assert opener and 'title="open the conversation"' in opener.group(0)
    assert re.search(r'id="chat-open"[^>]*>\s*<svg', html)
    # The input: soft rounding, gentle accent focus ring, muted italic
    # placeholder, auto-grow to a few lines.
    assert "border-radius: 14px" in html
    assert "#chat-form textarea:focus" in html
    assert "::placeholder" in html
    assert "function autoGrow()" in html
    # Sending busy-ness is tracked apart from the empty-input dimming, so
    # the reflection chip can still hand text over with an empty input.
    assert "var busy = false;" in html


def test_sidebar_collapser_persists_and_spares_mobile(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # A chevron on the sidebar edge; a floating one to reopen; the choice
    # persists in localStorage; the tray follows the new left edge.
    assert 'id="sidebar-collapse"' in html
    assert 'id="sidebar-reopen"' in html
    assert '"sa-sidebar"' in html
    assert "body.sidebar-collapsed #sidebar" in html
    assert "body.sidebar-collapsed #guide-chat { left: 0; }" in html
    # Desktop-only: the collapse rules live behind min-width, and the
    # mobile drawer (☰) keeps its own behavior untouched.
    assert "@media (min-width: 721px)" in html
    assert re.search(r"@media \(max-width: 720px\) \{[^@]*#sidebar-collapse \{ display: none;", html, re.S)


# --- listened: the shelf remembers what finished ------------------------------


def test_listening_summary_loader_tolerates_garbage(tmp_path):
    library = _make_library(tmp_path)
    summary = build_shelf.load_listening(library)
    assert summary == {"quiet-mind": {"count": 2, "last": "2026-07-02T06:00:00+00:00"}}
    (library / ".listening.jsonl").unlink()
    assert build_shelf.load_listening(library) == {}


def test_card_shows_listened_state_when_completed(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # quiet-mind has finished at least once: a quiet line with the date
    # and a replay affordance (replay starts fresh — position was cleared).
    line = re.search(r'<p class="listened-line"[^>]*>.*?</p>', html, re.S)
    assert line, "listened line missing"
    assert "listened ✓ 2026-07-02" in line.group(0)
    assert 'class="listened-replay" data-slug="quiet-mind"' in line.group(0)
    # Talks never finished carry no such line.
    far_card = re.search(r'<section class="card view" id="talk-far-talk">.*?</section>', html, re.S)
    assert "listened-line" not in far_card.group(0)


def test_completion_detection_js_markers(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # One POST per talk per page-load; the server dedupes besides.
    assert '"/api/listened"' in html
    assert "function reportListened(slug)" in html
    assert "reportedListened" in html
    # Local audio reports on ended and via the near-end clear; YouTube via
    # playerState 0 or ≥98% of duration (before the save throttle).
    assert "playerState === 0" in html
    assert "0.98" in html
    # Static shelf: the POST just fails quietly.
    assert "the server remembers next time" in html


# --- capsule expand: chat steps aside ------------------------------------------


def test_capsule_expand_docks_the_chat_first(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The chat panel hands LAYOUT a dock hook...
    assert "window.saDockChat = function" in html
    # ...and going to the playing talk uses it BEFORE navigating, so the
    # room is visible (and still playing) the moment the hash lands.
    go = re.search(r"function goToNowPlaying\(\) \{[\s\S]*?\n  \}", html).group(0)
    assert "saDockChat" in go
    assert go.index("saDockChat") < go.index("location.hash")


# --- co-navigation: peek, action execution, the lock ---------------------------


def test_duration_to_seconds():
    d = build_shelf.duration_to_seconds
    assert d("3:52") == 232
    assert d("56:04") == 3364
    assert d("1:03:52") == 3832
    assert d("") is None
    assert d(None) is None
    assert d("not a time") is None


def test_talk_sections_carry_duration_caps(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # demon-story has a Duration in the INDEX -> a data cap for seek cues.
    assert re.search(r'id="talk-demon-story" data-duration="3364"', html)
    # far-talk has none: no attribute, cues accept any offset there.
    assert re.search(r'id="talk-far-talk">', html)


def test_docked_send_streams_into_the_peek(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Sending from docked NO LONGER opens the overlay...
    assert 'if (chatState === "docked") setChatState("conversation");' not in html
    # ...the reply streams into a compact peek above the bar instead.
    assert 'id="chat-peek"' in html
    assert "function peekUpdate(text, done)" in html
    assert 'id="peek-text"' in html
    # The peek is a real element with the guide's mark, cloned at init.
    assert 'id="peek-mark"' in html


def test_peek_settles_into_a_dismissible_bubble(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    peek = re.search(r'<div id="chat-peek" hidden>.*?\n</div>', html, re.S)
    assert peek, "peek missing"
    # The settled bubble: clamped text, a "…more" that opens the overlay,
    # and a small dismiss. No auto-fade — it stays until acted on.
    assert 'id="peek-body"' in peek.group(0)
    assert 'id="peek-more"' in peek.group(0)
    assert 'id="peek-dismiss"' in peek.group(0)
    assert "…more" in html
    assert "peek-settled" in html
    assert "-webkit-line-clamp" in html
    assert "peek-rise" in html  # calm entrance: gentle rise + fade-in
    assert re.search(r"#chat-peek\[hidden\] \{ display: none", html)  # the chip lesson


def test_guide_lock_toggles_and_persists(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # A padlock on the capsule AND in each room header (shown only for
    # the playing talk); one shared class, one handler, localStorage.
    assert 'id="np-lock"' in html
    assert re.search(r'class="guide-lock room-lock" data-slug="quiet-mind" hidden', html)
    assert '"sa-guide-lock"' in html
    assert '"— guide navigation locked —"' in html
    assert '"— guide navigation unlocked —"' in html
    # The executor asks the lock before acting.
    assert "window.saCueLocked && window.saCueLocked()" in html


def test_cue_execution_reuses_user_click_paths(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Seek goes through the same seekTalk the transcript click uses; the
    # segment click handler itself is refactored onto it.
    assert "function seekTalk(slug, start)" in html
    assert html.count("seekTalk(") >= 3  # definition + seg click + cue path
    # Alive YouTube channels seek in place; otherwise the reload path.
    assert '"seekTo"' in html
    # Pause/play cues drive the same playback switch the capsule uses.
    assert "function setPlayback(playing)" in html


# --- watch it work: narrative rendering + self-refreshing shelf ---------------


def test_stream_narrative_splitter_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    fn = re.search(r"function splitNarrative\(raw\) \{[\s\S]*?\n  \}", html)
    assert fn, "splitNarrative missing"
    harness = fn.group(0) + r"""
function check(i, got, wantText, wantProgress) {
  if (got.text !== wantText || JSON.stringify(got.progress) !== JSON.stringify(wantProgress)) {
    console.error("case " + i, JSON.stringify(got));
    process.exit(1);
  }
}
check(0, splitNarrative("On it.\n— fetching the talk… —\nDone: it landed."),
  "On it.\nDone: it landed.", ["— fetching the talk… —"]);
check(1, splitNarrative("— rebuilding the shelf… —\n— rebuilding the shelf… —\nOk."),
  "Ok.", ["— rebuilding the shelf… —", "— rebuilding the shelf… —"]);
check(2, splitNarrative("plain reply, no narrative"),
  "plain reply, no narrative", []);
check(3, splitNarrative("mid — dash — text stays"), "mid — dash — text stays", []);
console.log("narrative ok");
"""
    js = tmp_path / "narrative.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "narrative ok" in result.stdout


def test_progress_lines_render_as_system_lines_and_pulse(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # New complete progress lines become centered system lines mid-stream
    # (peek and overlay alike), and the sidebar shows a soft working dot
    # on the entry the narrative mentions (else on the Talks heading).
    assert "shownProgress" in html
    assert "function pulseSidebar(" in html
    assert "function clearPulse()" in html
    assert 'id="talks-heading"' in html
    assert re.search(r"\.working::after \{[^}]*pulse", html, re.S)
    # The history strip removes narrative from restored/settled bubbles.
    assert "function cleanReply(" in html


def test_reload_safety_predicate_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    fn = re.search(r"function reloadIsSafe\(playing, state, draft\) \{[\s\S]*?\n  \}", html)
    assert fn, "reloadIsSafe missing"
    harness = fn.group(0) + r"""
function check(i, got, want) {
  if (got !== want) { console.error("case " + i); process.exit(1); }
}
check(0, reloadIsSafe(false, "docked", ""), true);
check(1, reloadIsSafe(true, "docked", ""), false);   // never mid-listen
check(2, reloadIsSafe(false, "conversation", ""), false); // never over chat
check(3, reloadIsSafe(false, "docked", "half a thought"), false); // never mid-draft
check(4, reloadIsSafe(false, "docked", "   "), true); // whitespace is no draft
console.log("safety ok");
"""
    js = tmp_path / "reload.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "safety ok" in result.stdout


def test_auto_fresh_polling_and_chip(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    assert '"/api/version"' in html
    assert "shelf_mtime" in html
    # ~8s poll while visible, plus a check after each completed turn.
    assert "8000" in html and "document.hidden" in html
    assert "checkVersion(); // fresh content may have just landed" in html
    # Unsafe moments get the gentle chip instead of a reload.
    chip = re.search(r'<button type="button" id="fresh-chip" hidden>', html)
    assert chip, "fresh chip missing"
    assert "the shelf has new content — refresh" in html
    assert re.search(r"#fresh-chip\[hidden\] \{ display: none", html)
    assert "location.reload()" in html
    assert "window.saIsPlaying" in html


def test_unfetched_hint_depends_on_curriculum_urls(tmp_path):
    library = _make_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(
        "## Queued\n- **Anger Issues (Thanissaro Bhikkhu, 2019)** — next.\n"
        "- **Mystery Talk** — no source known.\n"
    )
    curriculum = tmp_path / "curriculum"
    curriculum.mkdir()
    (curriculum / "01.md").write_text(
        "# Cluster\n\n- **Anger Issues — Thanissaro Bhikkhu (2019-05-31)** — "
        "https://www.dhammatalks.org/a.html\n  Reach for it when testing.\n"
    )
    html = build_shelf.render_shelf(library, {})
    sidebar = re.search(r'<nav id="sidebar">.*?</nav>', html, re.S).group(0)
    # The curriculum knows Anger Issues' URL: the guide can fetch it.
    anger = re.search(r'<li class="nav-unfetched">[\s\S]*?Anger Issues[\s\S]*?</li>', sidebar)
    assert anger and "not fetched yet — ask the guide" in anger.group(0)
    # Nothing anywhere knows Mystery Talk's URL: say what is missing.
    mystery = re.search(r'<li class="nav-unfetched">[\s\S]*?Mystery Talk[\s\S]*?</li>', sidebar)
    assert mystery and "needs a URL — tell the guide" in mystery.group(0)


def test_generate_button_sends_the_composed_ask(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Clicking composes and SENDS through the one send path.
    assert '"Please create interactive tools for "' in html or "'Please create interactive tools for '" in html
    assert "listening-first" in html
    assert ".make-interactive" in html
    # Titles are escaped in the data attribute.
    assert 'data-title="Quiet Mind &amp; &lt;Friends&gt;"' not in html  # has artifacts: no button
    assert 'data-title="Far Talk"' in html


# --- artifact -> seek: anchored listening from interactives --------------------


def test_artifact_seek_validator_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    fn = re.search(r"function validArtifactSeek\(data, cap\) \{[\s\S]*?\n  \}", html)
    assert fn, "validArtifactSeek missing"
    harness = fn.group(0) + r"""
function check(i, got, want) {
  if (!!got !== want) { console.error("case " + i); process.exit(1); }
}
check(0, validArtifactSeek({type: "second-arrow:seek", start: 803}, 3832), true);
check(1, validArtifactSeek({type: "second-arrow:seek", start: 0, label: "the eggs story"}, 3832), true);
check(2, validArtifactSeek({type: "second-arrow:seek", start: 4000}, 3832), false); // past the end
check(3, validArtifactSeek({type: "second-arrow:seek", start: 4000}, 0), true);     // no cap known
check(4, validArtifactSeek({type: "second-arrow:seek", start: -1}, 0), false);
check(5, validArtifactSeek({type: "second-arrow:seek", start: NaN}, 0), false);
check(6, validArtifactSeek({type: "second-arrow:seek", start: "803"}, 0), false);
check(7, validArtifactSeek({type: "second-arrow:seek", start: 10, label: "x".repeat(81)}, 0), false);
check(8, validArtifactSeek({type: "second-arrow:reflection", start: 10}, 0), false);
check(9, validArtifactSeek(null, 0), false);
console.log("seek matrix ok");
"""
    js = tmp_path / "artseek.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "seek matrix ok" in result.stdout


def test_artifact_seek_uses_frame_identity_and_click_semantics(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Same identity rule as reflections: the source must be OUR mounted
    # frame; the slug comes only from OUR data-slug.
    assert '"second-arrow:seek"' in html
    # Execution rides the user-click path (saExecuteCue -> seekTalk),
    # bypassing the guide lock: locks tie the GUIDE's hands, and an
    # artifact button is the user's own finger.
    assert "the user's own finger" in html
    assert re.search(r'saExecuteCue\(\{ kind: "seek", slug: from\.slug', html)



# --- iteration 13: the page stays alive — soft refresh + deferred reload -----


def test_turn_end_checks_version_immediately(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The finally of a streamed turn (success or error alike) polls right
    # away — never waiting out the 8s tick after the guide builds things.
    finally_block = re.search(r"\.finally\(function \(\) \{[\s\S]*?\n    \}\);", html)
    assert finally_block, "sendMessage finally missing"
    assert "checkVersion()" in finally_block.group(0)


def test_pending_reload_auto_applies_under_node(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    safe = re.search(
        r"function reloadIsSafe\(playing, state, draft\) \{[\s\S]*?\n  \}", html
    )
    fn = re.search(r"function maybeApplyPendingReload\(\) \{[\s\S]*?\n  \}", html)
    assert safe and fn, "pending-reload machinery missing"
    harness = (
        'var reloads = 0;\n'
        'var playing = false;\n'
        'var window = { saIsPlaying: function () { return playing; } };\n'
        'var location = { reload: function () { reloads += 1; } };\n'
        'var input = { value: "" };\n'
        'var chatState = "docked";\n'
        'var pendingReload = false;\n'
        + safe.group(0) + "\n" + fn.group(0) + "\n"
        + """
function check(i, want) {
  maybeApplyPendingReload();
  if (reloads !== want) { console.error("case " + i, reloads); process.exit(1); }
}
check(0, 0);                                   // nothing pending: never fires
pendingReload = true; playing = true; check(1, 0);       // never mid-listen
playing = false; chatState = "conversation"; check(2, 0); // never over chat
chatState = "docked"; input.value = "half a thought"; check(3, 0); // never mid-draft
input.value = ""; check(4, 1);                 // calm at last: it applies
console.log("pending ok");
"""
    )
    js = tmp_path / "pending.js"
    js.write_text(harness)
    result = subprocess.run(["node", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "pending ok" in result.stdout


def test_version_change_defers_and_reevaluates_at_calm_moments(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Detected-but-unsafe changes set the flag (soft swap failing first)
    # and show the chip; the chip click clears the flag (it reloads anyway).
    assert "pendingReload = true" in html
    assert "pendingReload = false" in html
    # Re-evaluated on every poll tick (the unchanged-version branch), on
    # chat docking, and after every completed turn (via checkVersion).
    check = re.search(r"function checkVersion\(\) \{[\s\S]*?\n  \}", html)
    assert check and "maybeApplyPendingReload()" in check.group(0)
    dock = re.search(r"function setChatState\(next\) \{[\s\S]*?\n  \}", html)
    assert dock and "maybeApplyPendingReload()" in dock.group(0)
    chip = re.search(r'freshChip\.addEventListener\("click", function \(\) \{[\s\S]*?\}\);', html)
    assert chip and "pendingReload = false" in chip.group(0)


def test_soft_refresh_swaps_in_place_but_never_the_playing_room(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The real "alive" feel: an unsafe moment gets the fresh page fetched,
    # parsed, and swapped in place — sidebar path + every room EXCEPT the
    # one holding the playing player. DOMParser + importNode only.
    assert "function softRefresh()" in html
    assert "DOMParser" in html
    assert "document.importNode" in html
    assert "innerHTML" not in html
    swap = re.search(r"function swapShelf\(doc\) \{[\s\S]*?\n  \}", html)
    assert swap, "swapShelf missing"
    assert "saPlayingSlug" in swap.group(0)  # the playing room is skipped
    assert "talk-nav" in swap.group(0)  # the sidebar path swaps too
    # Swapped rooms get their wiring back and (served) their live artifact
    # views; the router then re-applies the active room.
    assert "window.saBindRoom" in html
    assert "window.saShowView" in html
    assert "window.saPlayingSlug" in html
    # Folds stay as the reader left them, best effort.
    assert "function carryDetails(" in html


def test_room_bindings_are_container_scoped_for_rebinding(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # All per-element room wiring is one function callable on a swapped-in
    # subtree; page load wires the whole document through the same door.
    assert "function bindRoom(root)" in html
    assert "bindRoom(document)" in html
    # mountArtifacts targets one room and never double-mounts a frame.
    assert re.search(r"function mountArtifacts\(root\)", html)
    assert 'item.querySelector(".artifact-frame")' in html
    # The generate button and sidebar links are delegated, so swapped-in
    # copies work without any rebinding at all.
    assert 'event.target.closest(".make-interactive")' in html
    assert 'event.target.closest("#talk-nav a")' in html
