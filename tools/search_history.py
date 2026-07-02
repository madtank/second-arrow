#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""Search past shelf conversations (the guide's recall).

A stdlib-only CLI over serve_shelf.search_sessions: keyword scoring across
stored session turns and summaries under library/.chat/sessions/. This is
one of the chat guide's reviewed tools — when the user says "that story we
discussed", the guide greps its past instead of guessing.

Run with:
    uv run tools/search_history.py maggots story
    uv run tools/search_history.py --json "two bad bricks"
"""

import argparse
import importlib.util
import json
from pathlib import Path


def load_serve_shelf():
    path = Path(__file__).resolve().parent / "serve_shelf.py"
    spec = importlib.util.spec_from_file_location("serve_shelf", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description="Search past shelf conversations.")
    parser.add_argument("query", nargs="+", help="keywords to look for")
    parser.add_argument("--sessions-dir", default=None, help="override the sessions dir")
    parser.add_argument("--json", action="store_true", help="print raw JSON results")
    args = parser.parse_args()

    serve_shelf = load_serve_shelf()
    sessions_dir = (
        Path(args.sessions_dir) if args.sessions_dir else serve_shelf.SESSIONS_DIR
    )
    results = serve_shelf.search_sessions(" ".join(args.query), sessions_dir)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if not results:
        print("No past conversation matches.")
        return
    for result in results:
        when = result["when"][:10]
        print(f"[{when}] {result['title']} (session {result['session_id']})")
        print(f"  {result['snippet']}")


if __name__ == "__main__":
    main()
