import importlib.util
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
- **Themes:** anger, stories
- **Path:** library/demon-story/
"""
    )
    quiet = library / "quiet-mind"
    quiet.mkdir()
    (quiet / "primer.mp3").write_bytes(b"\x00")
    (quiet / "notes.md").write_text("# Notes\n\nWhat landed: **kindness** wins.\n")
    (quiet / "artifacts").mkdir()
    (quiet / "artifacts" / "breath-timer.html").write_text(
        "<!DOCTYPE html><html><body><h1>Breathe</h1></body></html>"
    )
    far = library / "far-talk"
    far.mkdir()
    (far / "transcript.md").write_text("# Far Talk\n\nWords.\n")
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
    # click-to-load button instead of a navigate-away link ...
    assert "Play here" in html
    assert 'data-embed="https://www.youtube-nocookie.com/embed/me7Wm5LOpx0"' in html
    # ... and a small escape hatch that opens in a NEW tab.
    assert "open on YouTube" in html
    demon = html[html.index("Demon Story"):]
    anchor = re.search(r'<a class="yt-link"[^>]*>', demon)
    assert anchor and 'target="_blank"' in anchor.group(0)
    assert 'rel="noopener"' in anchor.group(0)
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
    # The sidebar also carries the epigraph and the sessions placeholder.
    assert "The second arrow is optional." in sidebar.group(0)
    # The Sessions section is a real list now, filled from /api/sessions;
    # like the chat panel it stays hidden on the static file:// shelf.
    assert 'id="sessions-section"' in sidebar.group(0)
    assert 'id="session-list"' in sidebar.group(0)


def test_render_shelf_hash_views_present(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # One full-pane view per talk, plus the home/welcome view, routed by a
    # tiny hashchange handler (CSS :target can't also highlight the nav).
    assert 'id="talk-quiet-mind"' in html
    assert 'id="talk-far-talk"' in html
    assert 'id="talk-demon-story"' in html
    assert 'id="view-home"' in html
    assert "hashchange" in html
    assert "pick a talk from the sidebar" in html


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


def test_chat_panel_speaks_sessions_and_ambient_view(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The sidebar's Sessions list is fed from the server.
    assert "/api/sessions" in html
    section = re.search(r'<div id="sessions-section"[^>]*>', html)
    assert section and "hidden" in section.group(0)
    # A conversation can be started fresh, and the session that recorded
    # each turn comes back to the panel in the X-Session header.
    assert 'id="chat-new"' in html
    assert "new conversation" in html
    assert "X-Session" in html
    # Every chat POST carries the ambient view (the open talk's slug).
    assert "currentView" in html
    # After each completed turn the sessions list is refetched, so titles
    # and summaries the guide just updated appear immediately.
    assert "fresh summaries" in html


def test_render_shelf_lists_artifacts_behind_the_sandbox_contract(tmp_path):
    html = build_shelf.render_shelf(_make_library(tmp_path), {})
    # The talk card grows an Artifacts section listing artifacts/*.html.
    assert "<summary>Artifacts</summary>" in html
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
    assert html.count("<summary>Artifacts</summary>") == 1


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
