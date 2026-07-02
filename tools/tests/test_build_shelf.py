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
    unfetched = re.search(r'<li class="nav-unfetched">.*?</li>', sidebar, re.S).group(0)
    assert "Anger Issues (Thanissaro Bhikkhu, 2019)" in unfetched
    assert "not fetched yet" in unfetched
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
        "Learning tools",
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
    # "Learning tools" (the folder and routes keep the artifact name).
    assert "<summary>Learning tools</summary>" in html
    assert "<summary>Artifacts</summary>" not in html
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


def test_render_shelf_talk_without_artifacts_has_no_section(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # Only quiet-mind has artifacts; the section appears exactly once.
    assert html.count("<summary>Learning tools</summary>") == 1


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


def test_chat_input_is_anchored_to_the_viewport_bottom(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The guide panel sticks to the bottom of the main pane: the input
    # row can never be pushed off-screen; the message list scrolls above.
    assert "#guide-chat { position: sticky; bottom: 0;" in html
    assert re.search(r"#chat-messages \{[^}]*max-height", html)


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

