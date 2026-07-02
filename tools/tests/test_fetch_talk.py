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
