import importlib.util
from pathlib import Path

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
"""
    )
    quiet = library / "quiet-mind"
    quiet.mkdir()
    (quiet / "primer.mp3").write_bytes(b"\x00")
    (quiet / "notes.md").write_text("# Notes\n\nWhat landed: **kindness** wins.\n")
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
    assert build_shelf.parse_study("") == {"studied": [], "queued": []}
    assert build_shelf.parse_study("# Just a title\n\nprose\n") == {
        "studied": [],
        "queued": [],
    }
    assert build_shelf.parse_study("## Queued\n- **Next Talk** — soon.\n") == {
        "studied": [],
        "queued": ["Next Talk"],
    }


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
    assert 'class="card path-strip"' not in html
    # An empty STUDY.md is treated the same (static shareability).
    (tmp_path / "STUDY.md").write_text("# Study Memory\n")
    html = build_shelf.render_shelf(library, {})
    assert 'class="card path-strip"' not in html


def test_render_shelf_path_strip_escapes_names(tmp_path):
    library = _make_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(
        "## Studied\n- **Quiet <Talk> & Friends**: done.\n"
    )
    html = build_shelf.render_shelf(library, {})
    assert "✓ Quiet &lt;Talk&gt; &amp; Friends" in html
    assert "<Talk>" not in html
