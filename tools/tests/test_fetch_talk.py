import importlib.util
import json
import urllib.parse
from pathlib import Path

import pytest

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


def test_classify_url_reading_hosts_are_readings():
    # Sutta pages are text sources, never audio hunts.
    assert (
        fetch_talk.classify_url("https://www.dhammatalks.org/suttas/SN/SN36_6.html")
        == "reading"
    )
    assert (
        fetch_talk.classify_url("https://suttacentral.net/sn36.6/en/sujato")
        == "reading"
    )
    # Talk pages on the same site stay pages (audio-link hunts).
    assert (
        fetch_talk.classify_url("https://www.dhammatalks.org/audio/morning/2019/190531-anger-issues.html")
        == "page"
    )


def test_find_audio_link_in_dhammatalks_page():
    html = '<a href="/mp3/morning/2026/260612-patience.mp3">Download</a>'
    base = "https://www.dhammatalks.org/audio/morning/2026/260612-patience.html"
    assert (
        fetch_talk.find_audio_link(html, base)
        == "https://www.dhammatalks.org/mp3/morning/2026/260612-patience.mp3"
    )


def test_find_audio_link_returns_none_when_absent():
    assert fetch_talk.find_audio_link("<p>no audio here</p>", "https://x.test/") is None


def test_find_audio_link_unescapes_and_encodes_the_real_dhammatalks_shape():
    # Real-world regression (Patience & Goodwill, 2026-04-10): hrefs are
    # HTML-escaped and carry &, parens, and sometimes spaces — requesting
    # them raw 404s. The link must be HTML-unescaped, then made fetchable
    # (no bare spaces, no lingering &amp;).
    html = (
        '<a href="/Archive/shorttalks/y2026/'
        '260410(short)_Patience_&amp;_Goodwill.mp3">Listen</a>'
    )
    base = "https://www.dhammatalks.org/audio/morning/2026/260410-patience-goodwill.html"
    link = fetch_talk.find_audio_link(html, base)
    assert link is not None
    assert "&amp;" not in link
    assert "_Patience_&_Goodwill.mp3" in urllib.parse.unquote(link)
    assert " " not in link
    # A space in the path gets percent-encoded so urllib can fetch it.
    spaced = '<a href="/audio/some talk.mp3">x</a>'
    link = fetch_talk.find_audio_link(spaced, "https://x.test/")
    assert link == "https://x.test/audio/some%20talk.mp3"
    # Already-encoded links are not double-encoded.
    encoded = '<a href="/audio/some%20talk.mp3">x</a>'
    assert (
        fetch_talk.find_audio_link(encoded, "https://x.test/")
        == "https://x.test/audio/some%20talk.mp3"
    )


def test_guess_title_from_filename_strips_date_prefix_and_extension():
    assert fetch_talk.guess_title_from_filename("260612(short)_Patience.mp3") == "Patience"
    assert fetch_talk.guess_title_from_filename("some-talk.mp3") == "Some Talk"


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


def test_index_entry_carries_the_full_field_standard():
    entry = fetch_talk.index_entry(
        slug="on-anger",
        title="On Anger",
        teacher="Ajahn Brahm",
        source_url="https://youtu.be/abc",
        themes="anger, forgiveness",
        date="2023-01-27",
        duration="57:32",
        origin="youtube captions",
        ingested="2026-07-02",
    )
    assert entry.startswith("## on-anger\n")
    # Every entry gets the same fields, in a stable order.
    for line in (
        "- **Title:** On Anger",
        "- **Teacher:** Ajahn Brahm",
        "- **Source:** https://youtu.be/abc",
        "- **Date:** 2023-01-27",
        "- **Duration:** 57:32",
        "- **Origin:** youtube captions",
        "- **Ingested:** 2026-07-02",
        "- **Themes:** anger, forgiveness",
        "- **Path:** library/on-anger/",
    ):
        assert line in entry
    # Unknown values stay as blank fields, not missing lines.
    bare = fetch_talk.index_entry(
        slug="x", title="X", teacher="T", source_url="u", themes="t",
    )
    assert "- **Date:**" in bare and "- **Duration:**" in bare
    assert "- **Origin:**" in bare and "- **Ingested:**" in bare


# --- talk identity: the source URL is the canonical id -----------------------


def test_youtube_video_id_matrix():
    vid = fetch_talk.youtube_video_id
    assert vid("https://www.youtube.com/watch?v=d4JAjEj2d_c") == "d4JAjEj2d_c"
    assert vid("https://youtu.be/d4JAjEj2d_c") == "d4JAjEj2d_c"
    assert vid("https://www.youtube.com/watch?v=d4JAjEj2d_c&t=120s") == "d4JAjEj2d_c"
    assert vid("https://www.youtube.com/watch?t=1&v=d4JAjEj2d_c") == "d4JAjEj2d_c"
    assert vid("https://youtu.be/d4JAjEj2d_c?si=xyz") == "d4JAjEj2d_c"
    assert vid("https://example.org/talk.mp3") is None
    assert vid("") is None


def test_same_source_treats_youtube_spellings_as_one_talk():
    same = fetch_talk.same_source
    assert same(
        "https://www.youtube.com/watch?v=d4JAjEj2d_c",
        "https://youtu.be/d4JAjEj2d_c?si=share",
    )
    assert not same(
        "https://www.youtube.com/watch?v=d4JAjEj2d_c",
        "https://www.youtube.com/watch?v=me7Wm5LOpx0",
    )
    # Non-YouTube URLs compare exactly.
    assert same("https://example.org/t.mp3", "https://example.org/t.mp3")
    assert not same("https://example.org/t.mp3", "https://example.org/t2.mp3")


INDEX_TEXT = """# Library Index

## anger-and-forgiveness
- **Title:** Anger and Forgiveness
- **Teacher:** Ajahn Brahm
- **Source:** https://www.youtube.com/watch?v=d4JAjEj2d_c
- **Themes:** anger, forgiveness
- **Path:** library/anger-and-forgiveness/

## patience
- **Title:** Patience
- **Teacher:** Thanissaro Bhikkhu
- **Source:** https://www.dhammatalks.org/audio/morning/2026/260612-patience.html
- **Themes:** patience
- **Path:** library/patience/
"""


def test_find_existing_slug_matches_by_source_identity():
    find = fetch_talk.find_existing_slug
    # The same video under any URL spelling is the same talk.
    assert find(INDEX_TEXT, "https://youtu.be/d4JAjEj2d_c") == "anger-and-forgiveness"
    assert (
        find(INDEX_TEXT, "https://www.youtube.com/watch?v=d4JAjEj2d_c&t=9s")
        == "anger-and-forgiveness"
    )
    # Exact match for non-YouTube sources.
    assert (
        find(INDEX_TEXT, "https://www.dhammatalks.org/audio/morning/2026/260612-patience.html")
        == "patience"
    )
    assert find(INDEX_TEXT, "https://www.youtube.com/watch?v=other123456") is None
    assert find("", "https://youtu.be/d4JAjEj2d_c") is None


def test_clean_youtube_title_strips_pipe_tails_and_trailing_dates():
    clean = fetch_talk.clean_youtube_title
    assert clean("Anger and Forgiveness | Ajahn Brahm | 27 January 2023") == (
        "Anger and Forgiveness"
    )
    assert clean("Anger and Forgiveness (27 January 2023)") == "Anger and Forgiveness"
    assert clean("Dealing with people that irritate us | Ajahn Brahm") == (
        "Dealing with people that irritate us"
    )
    assert clean("Patience") == "Patience"  # clean titles pass through
    assert clean("Guided Meditation 2023-01-27") == "Guided Meditation"
    # Never empty: a title that is ONLY a tail survives as itself.
    assert clean("") == "talk"


def test_format_duration_renders_mm_ss_and_hours():
    fmt = fetch_talk.format_duration
    assert fmt(65) == "1:05"
    assert fmt(3452) == "57:32"
    assert fmt(3725) == "1:02:05"
    assert fmt(0) == ""
    assert fmt(None) == ""


def test_pick_thumbnail_url_prefers_the_medium_variants():
    pick = fetch_talk.pick_thumbnail_url
    info = {
        "thumbnail": "https://i.ytimg.com/vi/x/maxresdefault.jpg",
        "thumbnails": [
            {"id": "0", "url": "https://i.ytimg.com/vi/x/default.jpg"},
            {"id": "1", "url": "https://i.ytimg.com/vi/x/mqdefault.jpg"},
            {"id": "2", "url": "https://i.ytimg.com/vi/x/hqdefault.jpg"},
            {"id": "3", "url": "https://i.ytimg.com/vi/x/maxresdefault.jpg"},
        ],
    }
    assert pick(info) == "https://i.ytimg.com/vi/x/hqdefault.jpg"
    no_hq = {"thumbnails": [{"url": "https://i.ytimg.com/vi/x/mqdefault.jpg"}]}
    assert pick(no_hq) == "https://i.ytimg.com/vi/x/mqdefault.jpg"
    # Fallback: the declared best thumbnail, else nothing.
    assert pick({"thumbnail": "https://i.ytimg.com/vi/x/best.jpg"}) == (
        "https://i.ytimg.com/vi/x/best.jpg"
    )
    assert pick({}) is None


# --- VTT with timing: transcript.json segments --------------------------------

ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
so the question is

00:00:02.000 --> 00:00:04.000
so the question is
about anger

00:00:04.000 --> 00:00:06.500
about anger
and what to do
"""


def test_parse_vtt_segments_dedupes_rolling_captions_with_timing():
    segments = fetch_talk.parse_vtt_segments(ROLLING_VTT)
    assert [s["text"] for s in segments] == [
        "so the question is",
        "about anger",
        "and what to do",
    ]
    assert segments[0]["start"] == 0.0
    assert segments[1]["start"] == 2.0
    assert segments[2]["start"] == 4.0
    assert segments[2]["end"] == 6.5
    # A repeated line extends the earlier segment's end instead of duplicating.
    assert segments[0]["end"] >= 2.0


def test_parse_vtt_segments_text_matches_parse_vtt():
    # Parity: the segment texts joined are exactly the plain transcript.
    for vtt in (ROLLING_VTT, "WEBVTT\n\n00:00.000 --> 00:02.000\n<c>hello</c> there\n"):
        joined = " ".join(s["text"] for s in fetch_talk.parse_vtt_segments(vtt))
        assert joined == fetch_talk.parse_vtt(vtt)


def test_parse_vtt_segments_handles_hourless_stamps_and_cue_settings():
    vtt = """WEBVTT

00:01.500 --> 00:03.000 align:start position:0%
hello there

01:02:03.250 --> 01:02:05.000
deep into the talk
"""
    segments = fetch_talk.parse_vtt_segments(vtt)
    assert segments[0]["start"] == 1.5
    assert segments[1]["start"] == 3723.25
    assert segments[1]["end"] == 3725.0


def test_parse_vtt_segments_empty_and_junk():
    assert fetch_talk.parse_vtt_segments("") == []
    assert fetch_talk.parse_vtt_segments("WEBVTT\n\nNOTE hi\n") == []


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


# --- verified ingest: probe first, trust nothing -------------------------------


def test_page_title_extraction():
    assert fetch_talk.page_title("<html><head><title> Patience | dhammatalks.org </title></head></html>") == (
        "Patience | dhammatalks.org"
    )
    assert fetch_talk.page_title("<TITLE>Upper Case</TITLE>") == "Upper Case"
    assert fetch_talk.page_title("<p>no title here</p>") is None


def test_titles_match_is_fuzzy_but_not_gullible():
    match = fetch_talk.titles_match
    assert match("Killing Anger", "Killing Anger | dhammatalks.org")
    assert match("Anger Issues (Thanissaro Bhikkhu, 2019)", "Anger Issues")
    assert match("Anger Eating Demons", "Anger Eating Demons | Ajahn Brahm | 07-10-2011")
    assert not match("Killing Anger", "Metta for Beginners")
    assert not match("Killing Anger", "")
    assert not match("", "Killing Anger")


def test_transcript_chars_counts_only_the_body(tmp_path):
    talk = tmp_path / "talk"
    talk.mkdir()
    (talk / "transcript.md").write_text(
        "# T\n\n- Teacher: X\n- Source: y\n\n## Full Transcript\n\nhello there\n"
    )
    assert fetch_talk.transcript_chars(talk) == len("hello there")
    (talk / "transcript.md").unlink()
    assert fetch_talk.transcript_chars(talk) == 0


def test_ensure_valid_transcript_removes_a_junk_fresh_ingest(tmp_path):
    talk = tmp_path / "library" / "junk-talk"
    talk.mkdir(parents=True)
    (talk / "transcript.md").write_text(
        "# J\n\n## Full Transcript\n\n[Music]\n"
    )
    with pytest.raises(SystemExit) as excinfo:
        fetch_talk.ensure_valid_transcript(talk, fresh=True)
    assert "too small" in str(excinfo.value)
    assert not talk.exists()  # the partial dir is gone
    # A refresh of an existing talk reports but never deletes.
    talk.mkdir(parents=True)
    (talk / "transcript.md").write_text("# J\n\n## Full Transcript\n\nhi\n")
    (talk / "notes.md").write_text("keep me")
    with pytest.raises(SystemExit):
        fetch_talk.ensure_valid_transcript(talk, fresh=False)
    assert (talk / "notes.md").exists()
    # A real transcript sails through.
    (talk / "transcript.md").write_text(
        "# J\n\n## Full Transcript\n\n" + ("word " * 200) + "\n"
    )
    fetch_talk.ensure_valid_transcript(talk, fresh=True)
    assert talk.exists()


# --- readings: text pages ingest as transcripts --------------------------------

DHAMMATALKS_SUTTA_HTML = """<html><head>
<title>SN 36:6  The Arrow | Sallattha Sutta | sutta on dhammatalks.org</title>
<script>var junk = "never body text";</script>
<style>.hidden { color: red; }</style>
</head><body>
<nav><a href="/suttas/SN/SN36_5.html">Previous page</a></nav>
<main id="content" class="container px-0">
<div id="sutta">
<h1 id="SN36.6">The Arrow<br>Sallattha Sutta  (SN 36:6)</h1>
<p>“Monks, an uninstructed run-of-the-mill person feels feelings of pleasure.”</p>
<p>“When touched with a feeling of pain, he sorrows &amp; grieves.”</p>
<div class="verse"><p>The discerning person,</p><p>learned,</p></div>
</div><!--end:sutta-->
</main>
<div class="footer container"><ul><li><a href="/search.html">search everywhere</a></li></ul></div>
</body></html>"""

GENERIC_PAGE_HTML = """<html><head><title>On Patience | some site</title>
<script>tracker();</script></head>
<body>
<nav><a href="/">home</a> <a href="/about">about the site</a></nav>
<div class="content">
<p>Patience is the antidote the texts keep returning to.</p>
<p>It is not grim endurance.</p>
</div>
<footer>copyright somewhere</footer>
</body></html>"""


def test_extract_reading_dhammatalks_sutta_shape():
    reading = fetch_talk.extract_reading(
        DHAMMATALKS_SUTTA_HTML, "https://www.dhammatalks.org/suttas/SN/SN36_6.html"
    )
    # The title is the page's, with site tails dropped.
    assert reading["title"] == "SN 36:6 The Arrow"
    text = reading["text"]
    assert "uninstructed run-of-the-mill person" in text
    assert "sorrows & grieves" in text  # entities unescaped
    assert "The discerning person" in text
    # Boilerplate never leaks: nav, footer, scripts, styles.
    assert "Previous page" not in text
    assert "search everywhere" not in text
    assert "junk" not in text and "color: red" not in text
    # Paragraphs survive as blank-line breaks.
    assert "\n\n" in text


def test_extract_reading_generic_fallback_takes_the_body_text():
    reading = fetch_talk.extract_reading(
        GENERIC_PAGE_HTML, "https://example.org/on-patience.html"
    )
    assert reading["title"] == "On Patience"
    assert "not grim endurance" in reading["text"]
    assert "Patience is the antidote" in reading["text"]
    assert "about the site" not in reading["text"]
    assert "tracker" not in reading["text"]
    assert "copyright somewhere" not in reading["text"]


SUTTACENTRAL_API_JSON = json.dumps(
    {
        "translation_text": {
            "sn36.6:0.1": "Linked Discourses 36.6 ",
            "sn36.6:0.3": "An Arrow ",
            "sn36.6:1.1": "“Mendicants, an unlearned ordinary person feels pleasant feeling. ",
            "sn36.6:1.2": "So does a learned noble disciple. ",
            "sn36.6:2.1": "It’s like a person struck by two arrows. ",
        },
        "keys_order": [
            "sn36.6:0.1", "sn36.6:0.3", "sn36.6:1.1", "sn36.6:1.2", "sn36.6:2.1",
        ],
    }
)


def test_suttacentral_reading_speaks_the_bilara_api(monkeypatch):
    # suttacentral.net pages are a JS shell with no text in them — the
    # extractor asks the public bilara API for the segments instead.
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return SUTTACENTRAL_API_JSON

    monkeypatch.setattr(fetch_talk, "fetch_page", fake_fetch)
    reading = fetch_talk.fetch_reading("https://suttacentral.net/sn36.6/en/sujato")
    assert calls == ["https://suttacentral.net/api/bilarasuttas/sn36.6/sujato?lang=en"]
    assert reading["title"] == "An Arrow"
    # Same-section segments join into one paragraph; sections break.
    assert (
        "unlearned ordinary person feels pleasant feeling. So does a learned "
        "noble disciple." in reading["text"]
    )
    assert "\n\n" in reading["text"]
    # Heading segments (section 0) feed the title, not the body.
    assert "Linked Discourses" not in reading["text"]
    # A bare suttacentral URL (no translator) aborts with clear words.
    with pytest.raises(SystemExit):
        fetch_talk.fetch_suttacentral_reading("https://suttacentral.net/sn36.6")


def test_probe_source_reading_kind_and_word_count(monkeypatch):
    monkeypatch.setattr(fetch_talk, "fetch_page", lambda url: DHAMMATALKS_SUTTA_HTML)
    probe = fetch_talk.probe_source("https://www.dhammatalks.org/suttas/SN/SN36_6.html")
    assert probe["kind"] == "reading"
    assert probe["title"] == "SN 36:6 The Arrow"
    assert probe["words"] == len(probe["text"].split())
    assert probe["words"] > 0
    assert probe["duration"] == "~1 min read"
    assert probe["final_url"] == "https://www.dhammatalks.org/suttas/SN/SN36_6.html"
    # A page that offers no audio link is a reading too — never an error.
    monkeypatch.setattr(fetch_talk, "fetch_page", lambda url: GENERIC_PAGE_HTML)
    probe = fetch_talk.probe_source("https://example.org/on-patience.html")
    assert probe["kind"] == "reading"
    assert "not grim endurance" in probe["text"]


def test_reading_minutes():
    assert fetch_talk.reading_minutes(5) == 1  # never zero
    assert fetch_talk.reading_minutes(100) == 1
    assert fetch_talk.reading_minutes(1000) == 5


def test_ingest_reading_writes_transcript_and_index(tmp_path):
    library = tmp_path / "library"
    text = ("Patience is the antidote. " * 40).strip()
    slug = fetch_talk.ingest_reading(
        library=library,
        url="https://www.dhammatalks.org/suttas/SN/SN36_6.html",
        title="SN 36:6 The Arrow",
        teacher="trans. Thanissaro Bhikkhu",
        themes="two arrows, feeling",
        text=text,
        existing=None,
    )
    assert slug == "sn-36-6-the-arrow"
    md = (library / slug / "transcript.md").read_text()
    assert md.startswith("# SN 36:6 The Arrow")
    assert "- Teacher: trans. Thanissaro Bhikkhu" in md
    assert "- Source: https://www.dhammatalks.org/suttas/SN/SN36_6.html" in md
    # The header is honest: an extraction, no audio, the page is the authority.
    assert "- Origin: reading" in md
    assert "extract" in md
    assert "## Full Transcript" in md
    assert "Patience is the antidote." in md
    # No audio, no transcript.json — a reading has neither.
    assert not list((library / slug).glob("audio.*"))
    assert not (library / slug / "transcript.json").exists()
    index = (library / "INDEX.md").read_text()
    assert f"## {slug}" in index
    assert "- **Origin:** reading" in index
    assert "- **Duration:** ~1 min read" in index
    assert "- **Themes:** two arrows, feeling" in index


def test_ingest_reading_rejects_a_trivial_extraction(tmp_path):
    library = tmp_path / "library"
    with pytest.raises(SystemExit) as excinfo:
        fetch_talk.ingest_reading(
            library=library,
            url="https://example.org/x.html",
            title="X",
            teacher="Unknown",
            themes="",
            text="nothing much",
            existing=None,
        )
    assert "too small" in str(excinfo.value)
    assert not (library / "x").exists()
    assert not (library / "INDEX.md").exists()  # nothing indexed

