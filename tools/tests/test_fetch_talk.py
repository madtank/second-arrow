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
