#!/usr/bin/env python3
# /// script
# dependencies = ["mcp"]
# ///
"""A scoped MCP stdio server for the Hermes bridge.

Exposes exactly three tools — fetch_talk, rebuild_shelf, speak — to a
locally running hermes-agent (registered in ~/.hermes/config.yaml under
mcp_servers, stdio transport; see docs/hermes-bridge.md). Nothing else in
the repo is reachable through it: no terminal, no file access, no journal.

The security wall stays serve_shelf.validate_tool_call: every tool call is
turned into an argv list by that one function (loaded read-only from the
sibling serve_shelf.py by path — its heavy deps, fastapi/uvicorn, are
lazy-imported inside create_app()/main(), so importing the module pulls in
stdlib only). No validation logic is duplicated here. A rejected call
comes back to the model as a plain "Tool call rejected: ..." message —
never an exception — and an accepted argv runs as a direct subprocess
(no shell) with a 600s ceiling, returning the output tail.

Run standalone (Hermes does this for you):
    uv run tools/mcp_second_arrow.py

Tests (offline, no mcp package needed — the SDK import is lazy):
    uv run --with pytest pytest tools/tests/test_mcp_second_arrow.py -v
"""

import importlib.util
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_TIMEOUT = 600  # seconds per subprocess — matches serve_shelf's ceiling
OUTPUT_TAIL = 1500  # chars of stdout+stderr handed back to the model

_serve_shelf = None


def load_serve_shelf():
    """Import the sibling serve_shelf.py by path, once (read-only).

    Same importlib pattern the tests use. Safe at tool-call time:
    serve_shelf's top-level imports are stdlib-only (fastapi/uvicorn are
    lazy inside create_app()/main()), and nothing here calls anything but
    the pure validate_tool_call.
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
            cwd=REPO_ROOT,
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


# --- the three tools (FastMCP reads name/schema off these functions) --------


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


# Exactly these three — the bridge brain gets hands, nothing else.
TOOL_HANDLERS = {
    "fetch_talk": fetch_talk,
    "rebuild_shelf": rebuild_shelf,
    "speak": speak,
}


def build_server():
    """Register the three handlers on a FastMCP server (SDK import is lazy
    so the tests can load this module without the mcp package)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        "second_arrow",
        instructions=(
            "Reviewed hands for the Second Arrow study space: ingest a talk "
            "the user asked for, rebuild the shelf page, or record a short "
            "spoken reflection. Use a tool only when the user asks for the "
            "thing it does."
        ),
    )
    for handler in TOOL_HANDLERS.values():
        server.tool()(handler)
    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
