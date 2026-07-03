#!/usr/bin/env python3
# /// script
# dependencies = ["yt-dlp"]
# ///
"""Search YouTube for talks — read-only, one JSON line per result.

Flat extraction only: nothing is downloaded, nothing is written.
Searching is free; downloads stay explicit via fetch_talk.

Run with:
    uv run tools/find_talks.py "thanissaro anger" --limit 5
"""

import argparse
import json


def _ydl():
    """The YoutubeDL class, imported lazily so tests can monkeypatch."""
    import yt_dlp

    return yt_dlp.YoutubeDL


def _download_error():
    """yt-dlp's DownloadError class, imported lazily so tests can monkeypatch."""
    import yt_dlp

    return yt_dlp.utils.DownloadError


def search(query: str, limit: int = 5) -> list[dict]:
    """Flat-search YouTube; return rows of title/channel/duration/url."""
    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with _ydl()(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    except _download_error() as error:
        raise SystemExit(f"search failed: {error}")
    rows = []
    for entry in (info or {}).get("entries") or []:
        if not entry:
            continue
        duration = entry.get("duration")
        rows.append(
            {
                "title": entry.get("title") or "",
                "channel": entry.get("channel") or entry.get("uploader") or "",
                "duration": int(duration) if duration is not None else None,
                "url": entry.get("url") or entry.get("webpage_url") or "",
            }
        )
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Search YouTube for talks (read-only)")
    parser.add_argument("query", help="What to search for")
    parser.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    args = parser.parse_args(argv)
    for row in search(args.query, limit=args.limit):
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
