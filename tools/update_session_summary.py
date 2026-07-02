#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""Set a shelf session's title + short summary (the guide's freshness tool).

A stdlib-only CLI over serve_shelf.update_session_summary: session ids are
validated against the id rules and must exist; title is capped at 80 chars,
summary at 300; everything else in the sidecar (talks, claude thread,
created stamp) is preserved. The chat guide calls this when a conversation
meaningfully turns or wraps — the current session id arrives in its
[session: ...] prompt line — so the sidebar stays fresh without waiting
for the user to leave.

Run with:
    uv run tools/update_session_summary.py <session-id> "<title>" "<summary>"
"""

import argparse
import importlib.util
from pathlib import Path


def load_serve_shelf():
    path = Path(__file__).resolve().parent / "serve_shelf.py"
    spec = importlib.util.spec_from_file_location("serve_shelf", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update a shelf session's title and summary."
    )
    parser.add_argument("session_id", help="the session id (from the [session: ...] line)")
    parser.add_argument("title", help="new title, at most 80 chars")
    parser.add_argument("summary", help="new summary, at most 300 chars")
    parser.add_argument("--sessions-dir", default=None, help="override the sessions dir")
    args = parser.parse_args()

    serve_shelf = load_serve_shelf()
    sessions_dir = (
        Path(args.sessions_dir) if args.sessions_dir else serve_shelf.SESSIONS_DIR
    )
    try:
        meta = serve_shelf.update_session_summary(
            sessions_dir, args.session_id, args.title, args.summary
        )
    except ValueError as error:
        raise SystemExit(f"rejected: {error}")
    print(f"Session {args.session_id} is now titled {meta['title']!r}.")


if __name__ == "__main__":
    main()
