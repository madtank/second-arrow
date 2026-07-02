"""The one scratch-library builder the test suites share.

Extracted from test_build_shelf.py so the browser-level e2e suite
(tools/tests/e2e/) builds on the SAME library shape the unit tests
render — one fixture, not three drifting copies. Everything here writes
only under the tmp_path it is given; the real library/ is never touched.

make_library gives four talks that between them cover every card shape
build_shelf renders:

    quiet-mind   local audio + primer + notes + artifacts/ + a
                 whisper-shaped transcript.json (timed segments)
    far-talk     transcript.md only (the plain rendered transcript)
    demon-story  YouTube source + thumbnail + captions-shaped
                 transcript.json
    bare-yt      YouTube source, nothing else

plus a .listening.jsonl with one finished talk (and one torn line, so
tolerance stays exercised).
"""

import json


def make_library(tmp_path):
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
    (quiet / "notes.md").write_text(
        "# Notes\n\nWhat landed: **kindness** wins.\n\n"
        "## Moments\n\n"
        "- 0:04 — how it settles\n"
        "- 12:00 — past the end (dropped: outside the transcript range)\n"
    )
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
