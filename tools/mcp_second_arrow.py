#!/usr/bin/env python3
# /// script
# dependencies = ["mcp"]
# ///
"""The guide's entire world, as an MCP stdio server for a Hermes profile.

A hermes-agent profile whose ONLY toolset is this server gets everything
the study guide needs and nothing else (registered in ~/.hermes/config.yaml
under mcp_servers, stdio transport; see docs/hermes-bridge.md):

Actions (through serve_shelf.validate_tool_call, the unchanged wall):
    fetch_talk, rebuild_shelf, speak
Reads (pinned inside the study space; "not found" messages, not exceptions):
    get_path (STUDY.md), get_library_index (library/INDEX.md),
    read_transcript (paginated ~8k chars per call), read_notes,
    get_curriculum (curriculum/*.md concatenated),
    search_history (past conversations, via serve_shelf.search_sessions)
Scoped writes (the claude chat brain's allowlist, mirrored; ~64KB cap;
every result says what changed):
    update_path (STUDY.md, wholesale), update_notes (library/<slug>/notes.md),
    append_journal (journal/YYYY-MM-DD.md, today's date, append-only)
Interactive pages (rendered on the shelf behind a sandboxed iframe + a
no-network CSP; ~256KB cap, path pinned by serve_shelf.artifact_path):
    write_artifact (library/<slug>/artifacts/<name>.html — one
    self-contained single-file HTML page, inline CSS/JS only)
Session freshness (shelf sessions under library/.chat/sessions/; note
Hermes sessions are NOT shelf sessions — use only with a known id):
    update_session_summary (title ≤80, summary ≤300; sidecar preserved)

There is deliberately NO journal read tool: hosted models see whatever
tools return, and the journal never leaves the machine. No terminal, no
general file access, no web.

The action wall stays serve_shelf.validate_tool_call: every action call is
turned into an argv list by that one function (loaded read-only from the
sibling serve_shelf.py by path — its heavy deps, fastapi/uvicorn, are
lazy-imported inside create_app()/main(), so importing the module pulls in
stdlib only). No validation logic is duplicated here. A rejected call
comes back to the model as a plain "Tool call rejected: ..." message —
never an exception — and an accepted argv runs as a direct subprocess
(no shell) with a 600s ceiling, returning the output tail.

SECOND_ARROW_ROOT (env) overrides the study-space root — for tests and
smoke runs against a throwaway copy; unset, it is this repo.

Run standalone (Hermes does this for you):
    uv run tools/mcp_second_arrow.py

Tests (offline, no mcp package needed — the SDK import is lazy):
    uv run --with pytest pytest tools/tests/test_mcp_second_arrow.py -v
"""

import importlib.util
import os
import re
import subprocess
from datetime import date
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
TOOL_TIMEOUT = 600  # seconds per subprocess — matches serve_shelf's ceiling
OUTPUT_TAIL = 1500  # chars of stdout+stderr handed back to the model
PAGE_CHARS = 8000  # transcript page size: small models must not drown
MAX_WRITE_CHARS = 64 * 1024  # ~64KB ceiling on any single write
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")  # lowercase slug chars only

_serve_shelf = None


def repo_root() -> Path:
    """The study-space root: SECOND_ARROW_ROOT (env) or this repo.

    Read per call so tests and smoke runs can point the whole read/write
    surface at a throwaway copy — the real STUDY.md/journal/library stay
    untouched.
    """
    override = os.environ.get("SECOND_ARROW_ROOT")
    return Path(override).resolve() if override else DEFAULT_ROOT


def inside_root(path: Path, root: Path) -> bool:
    """Belt-and-braces guard: does the resolved path stay under root?"""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def load_serve_shelf():
    """Import the sibling serve_shelf.py by path, once (read-only).

    Same importlib pattern the tests use. Safe at tool-call time:
    serve_shelf's top-level imports are stdlib-only (fastapi/uvicorn are
    lazy inside create_app()/main()), and nothing here calls anything but
    pure functions (validate_tool_call, search_sessions).
    """
    global _serve_shelf
    if _serve_shelf is None:
        path = Path(__file__).resolve().parent / "serve_shelf.py"
        spec = importlib.util.spec_from_file_location("serve_shelf", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        _serve_shelf = module
    return _serve_shelf


def run_tool(argv: list[str], timeout: int = TOOL_TIMEOUT) -> tuple[bool, str]:
    """Execute a validated argv directly (never shell=True); (ok, summary)."""
    try:
        proc = subprocess.run(
            argv,
            cwd=repo_root(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"{argv[2]} timed out after {timeout}s."
    except OSError as error:
        return False, f"{argv[2]} could not start: {error}"
    tail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-OUTPUT_TAIL:]
    if proc.returncode != 0:
        return False, f"{argv[2]} failed (exit {proc.returncode}):\n{tail}"
    return True, f"{argv[2]} succeeded:\n{tail}"


def call_tool(name: str, args: dict) -> str:
    """validate_tool_call → subprocess → text the model can read.

    The wall: serve_shelf.validate_tool_call either returns a safe argv or
    raises ValueError; the rejection becomes tool output, not a crash.
    """
    try:
        argv = load_serve_shelf().validate_tool_call(name, args)
    except ValueError as error:
        return f"Tool call rejected: {error}"
    ok, summary = run_tool(argv)
    return summary


# --- small shared helpers -----------------------------------------------------


def _check_slug(slug) -> str | None:
    """A rejection message for a bad slug, or None when it is clean."""
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        return (
            f"{slug!r} is not a valid talk slug — use the lowercase "
            "dashed name shown in the library index (get_library_index)."
        )
    return None


def _read_text(path: Path, missing: str) -> str:
    if not path.is_file():
        return missing
    return path.read_text(encoding="utf-8")


def _check_write(content) -> str | None:
    """A rejection message for bad write content, or None when acceptable."""
    if not isinstance(content, str) or not content.strip():
        return "Write rejected: content must be non-empty text."
    if len(content) > MAX_WRITE_CHARS:
        return (
            f"Write rejected: content is {len(content)} chars, the cap is "
            f"{MAX_WRITE_CHARS}. Send less — these files stay small."
        )
    return None


# --- actions (serve_shelf.validate_tool_call is the wall) ---------------------


def fetch_talk(url: str, title: str = "", teacher: str = "", themes: str = "") -> str:
    """Ingest ONE talk into the library from a URL the user explicitly
    gave (captioned YouTube preferred). Never invent or guess URLs.
    Optional title/teacher/themes label the shelf entry."""
    return call_tool(
        "fetch_talk", {"url": url, "title": title, "teacher": teacher, "themes": themes}
    )


def rebuild_shelf() -> str:
    """Regenerate the shelf page after any library change, then tell the
    user to refresh."""
    return call_tool("rebuild_shelf", {})


def speak(text: str, out_name: str) -> str:
    """Record a short reflection as an mp3 on the shelf. out_name becomes
    a slug under library/."""
    return call_tool("speak", {"text": text, "out_name": out_name})


# --- reads (pinned inside the study space) ------------------------------------


def get_path() -> str:
    """Read STUDY.md — the study path: where we are, what's studied,
    what's queued, open questions. Call this at session start."""
    return _read_text(
        repo_root() / "STUDY.md",
        "STUDY.md not found — the study path has not been started yet.",
    )


def get_library_index() -> str:
    """Read library/INDEX.md — every talk on the shelf, with its slug,
    teacher, and themes. Call this at session start."""
    return _read_text(
        repo_root() / "library" / "INDEX.md",
        "library/INDEX.md not found — the library is empty; fetch_talk adds to it.",
    )


def read_transcript(slug: str, offset: int = 0, limit: int = PAGE_CHARS) -> str:
    """Read a talk's transcript, ~8000 chars per call. slug is the
    lowercase dashed name from the library index. When there is more, the
    reply ends with the offset to pass next time — keep calling until it
    stops saying so."""
    problem = _check_slug(slug)
    if problem:
        return problem
    path = repo_root() / "library" / slug / "transcript.md"
    if not inside_root(path, repo_root()) or not path.is_file():
        return f"No transcript for {slug!r} — check the slug in get_library_index."
    text = path.read_text(encoding="utf-8")
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), PAGE_CHARS))
    if offset >= len(text) and offset > 0:
        return (
            f"offset {offset} is past the end — the transcript is "
            f"{len(text)} chars."
        )
    end = min(offset + limit, len(text))
    page = text[offset:end]
    if end < len(text):
        page += (
            f"\n\n…more ({len(text) - end} chars left) — "
            f"call again with offset={end}"
        )
    return page


def read_notes(slug: str) -> str:
    """Read a talk's notes.md — earlier takeaways and reflections for
    that talk."""
    problem = _check_slug(slug)
    if problem:
        return problem
    path = repo_root() / "library" / slug / "notes.md"
    if not inside_root(path, repo_root()) or not path.is_file():
        return f"No notes yet for {slug!r}."
    return path.read_text(encoding="utf-8")


def get_curriculum() -> str:
    """Read the curriculum — every curriculum/*.md file, in order. Use it
    when choosing what to study next."""
    folder = repo_root() / "curriculum"
    files = sorted(folder.glob("*.md")) if folder.is_dir() else []
    if not files:
        return "No curriculum files found under curriculum/."
    parts = [
        f"--- {path.name} ---\n{path.read_text(encoding='utf-8')}" for path in files
    ]
    return "\n\n".join(parts)


def search_history(query: str) -> str:
    """Search past conversations ("that story we talked about") by a few
    keywords. Returns matching sessions with snippets — answer from what
    it returns, never from guesswork."""
    if not isinstance(query, str) or not query.strip():
        return "No past conversation matched — give a few keywords to search for."
    sessions_dir = repo_root() / "library" / ".chat" / "sessions"
    searcher = getattr(load_serve_shelf(), "search_sessions", None)
    results = (
        searcher(query, sessions_dir) if searcher else _search_fallback(query, sessions_dir)
    )
    if not results:
        return f"No past conversation matched {query!r}."
    lines = [
        f"- [{hit['session_id']}] {hit['title']} ({hit['when']}): {hit['snippet']}"
        for hit in results
    ]
    return "\n".join(lines)


def _search_fallback(query: str, sessions_dir: Path, limit: int = 8) -> list[dict]:
    """Minimal keyword search over sessions/*.jsonl — only used if the
    working-tree serve_shelf ever loses search_sessions."""
    import json

    terms = {w for w in re.findall(r"[a-z']+", query.lower()) if len(w) > 2}
    hits: list[dict] = []
    for turns_path in sorted(sessions_dir.glob("*.jsonl")) if sessions_dir.is_dir() else []:
        best = ""
        score = 0
        for line in turns_path.read_text(encoding="utf-8").splitlines():
            try:
                turn = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = turn.get("content") if isinstance(turn, dict) else None
            if not isinstance(content, str):
                continue
            overlap = len(terms & set(re.findall(r"[a-z']+", content.lower())))
            if overlap > score:
                score, best = overlap, content
        if score:
            hits.append(
                {
                    "session_id": turns_path.stem,
                    "title": turns_path.stem,
                    "snippet": " ".join(best.split())[:180],
                    "when": "",
                }
            )
    return hits[:limit]


# --- scoped writes: STUDY.md, journal/**, library/**/notes.md — nothing else --


def update_path(content: str) -> str:
    """Replace STUDY.md wholesale (it is small). Keep its four sections:
    Where we are, Studied, Queued, Open questions."""
    problem = _check_write(content)
    if problem:
        return problem
    root = repo_root()
    path = root / "STUDY.md"
    assert inside_root(path, root)
    existed = path.is_file()
    path.write_text(content, encoding="utf-8")
    verb = "replaced" if existed else "created"
    return f"STUDY.md {verb} ({len(content)} chars)."


def update_notes(slug: str, content: str) -> str:
    """Replace a talk's notes.md (takeaways, reflections). The talk must
    already exist in the library."""
    problem = _check_slug(slug) or _check_write(content)
    if problem:
        return problem
    root = repo_root()
    talk_dir = root / "library" / slug
    if not inside_root(talk_dir, root) or not talk_dir.is_dir():
        return f"No talk {slug!r} in the library — check get_library_index."
    path = talk_dir / "notes.md"
    existed = path.is_file()
    path.write_text(content, encoding="utf-8")
    verb = "updated" if existed else "created"
    return f"library/{slug}/notes.md {verb} ({len(content)} chars)."


def write_artifact(slug: str, name: str, html: str) -> str:
    """Write a SELF-CONTAINED interactive HTML page (practice page,
    reflection card, timer) into a talk's artifacts/ folder. Inline
    CSS/JS only — no external scripts, styles, fonts, or requests: it
    renders behind a no-network sandbox, so anything external simply
    won't load. Media only via relative paths into the talk folder
    (e.g. ../../<slug>/audio.mp3). name is lowercase slug chars +
    ".html". After writing, call rebuild_shelf so it appears."""
    root = repo_root()
    try:
        path = load_serve_shelf().write_artifact(root / "library", slug, name, html)
    except ValueError as error:
        return f"Write rejected: {error}"
    assert inside_root(path, root)
    return (
        f"Wrote {path.relative_to(root)} ({len(html)} chars). "
        "Call rebuild_shelf so it appears on the shelf, then tell the "
        "user to refresh."
    )


def update_session_summary(session_id: str, title: str, summary: str) -> str:
    """Update a shelf conversation's sidebar title and short summary
    (title at most 80 chars, summary at most 300). Use only when a shelf
    session id is actually known — a Hermes conversation is NOT a shelf
    session and has no id of its own."""
    sessions_dir = repo_root() / "library" / ".chat" / "sessions"
    try:
        meta = load_serve_shelf().update_session_summary(
            sessions_dir, session_id, title, summary
        )
    except ValueError as error:
        return f"Update rejected: {error}"
    return f"Session {session_id} is now titled {meta['title']!r}."


def append_journal(content: str) -> str:
    """Append a reflection to today's journal entry (journal/YYYY-MM-DD.md,
    created with a date heading if new). Append-only: the journal is
    written here, never read back through any tool."""
    problem = _check_write(content)
    if problem:
        return problem
    root = repo_root()
    today = date.today().isoformat()
    path = root / "journal" / f"{today}.md"
    assert inside_root(path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    piece = content if content.endswith("\n") else content + "\n"
    if path.is_file():
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + piece)
        return f"Appended {len(content)} chars to journal/{today}.md."
    path.write_text(f"# {today}\n\n{piece}", encoding="utf-8")
    return f"Created journal/{today}.md with the entry ({len(content)} chars)."


# The whole world: three actions, six reads, three scoped writes, one
# artifact write, one session-freshness write — fourteen tools. No journal
# read, no terminal, no general file access — by design.
TOOL_HANDLERS = {
    "fetch_talk": fetch_talk,
    "rebuild_shelf": rebuild_shelf,
    "speak": speak,
    "get_path": get_path,
    "get_library_index": get_library_index,
    "read_transcript": read_transcript,
    "read_notes": read_notes,
    "get_curriculum": get_curriculum,
    "search_history": search_history,
    "update_path": update_path,
    "update_notes": update_notes,
    "append_journal": append_journal,
    "write_artifact": write_artifact,
    "update_session_summary": update_session_summary,
}


def build_server():
    """Register the handlers on a FastMCP server (SDK import is lazy so
    the tests can load this module without the mcp package)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        "second_arrow",
        instructions=(
            "The Second Arrow study space: read the study path, the "
            "library index, transcripts, notes, and curriculum; search "
            "past conversations; ingest a talk the user asked for; rebuild "
            "the shelf page; record a short spoken reflection; and keep "
            "STUDY.md, per-talk notes, and the journal current. Use a tool "
            "only when the conversation asks for the thing it does."
        ),
    )
    for handler in TOOL_HANDLERS.values():
        server.tool()(handler)
    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
