#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""Startup gate for the Hermes bridge: is the gateway scoped as promised?

Reads HERMES_URL (default http://127.0.0.1:8642) and HERMES_API_KEY from
the environment, GETs /health and /v1/toolsets off the hermes-agent API
server (bearer auth), prints what is exposed, and exits 0 only when the
exposed toolsets are a subset of ALLOWED_TOOLSETS:

    mcp-second_arrow  — the toolset Hermes derives from our MCP server
                        (docs: "Each configured MCP server generates a
                        mcp-<server> toolset at runtime")
    clarify           — asks the user a question, touches nothing (docs:
                        "performs user inquiries without resource
                        consumption")

Anything else — terminal, file, web, browser, code_execution, ... — means
the ~/.hermes config drifted, the probe exits 1 listing the excess, and
the bridge brain in serve_shelf must refuse to start. Read-only: two GETs,
no reconfiguration.

Run:
    HERMES_API_KEY=... uv run tools/hermes_probe.py

Tests (pure parts):
    uv run --with pytest pytest tools/tests/test_hermes_probe.py -v
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8642"
PROBE_TIMEOUT = 10  # seconds per GET

ALLOWED_TOOLSETS = frozenset({"mcp-second_arrow", "clarify"})


# --- pure parts (tested in tools/tests/test_hermes_probe.py) ----------------


def parse_toolsets(payload) -> set[str]:
    """Toolset names out of a /v1/toolsets payload, whatever its dressing.

    The docs pin the endpoint but not the body shape, so tolerate the
    obvious ones: a bare list, or a {"toolsets": [...]} / {"data": [...]}
    wrapper; items as strings or objects carrying "name"/"id". Junk items
    are dropped — an unrecognized payload parses to the empty set, which
    the gate treats as "nothing exposed" (subset, pass).
    """
    if isinstance(payload, dict):
        items = payload.get("toolsets", payload.get("data", []))
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    names: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str) and item:
            names.add(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("id")
            if isinstance(name, str) and name:
                names.add(name)
    return names


def excess_toolsets(exposed: set[str], allowed: frozenset | set) -> list[str]:
    """The toolsets that must not be there, sorted. Empty means: gate open."""
    return sorted(exposed - set(allowed))


# --- the two read-only GETs --------------------------------------------------


def _get(base: str, path: str, api_key: str):
    request = urllib.request.Request(
        base.rstrip("/") + path,
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
    )
    with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
        return json.loads(response.read())


def main() -> int:
    base = os.environ.get("HERMES_URL", DEFAULT_URL)
    api_key = os.environ.get("HERMES_API_KEY", "")
    try:
        health = _get(base, "/health", api_key)
        print(f"health: {json.dumps(health)}")
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
        print(f"Hermes gateway unreachable at {base}: {error}", file=sys.stderr)
        return 1
    try:
        payload = _get(base, "/v1/toolsets", api_key)
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as error:
        print(f"GET /v1/toolsets failed: {error}", file=sys.stderr)
        return 1
    exposed = parse_toolsets(payload)
    print(f"exposed toolsets: {sorted(exposed) or '(none reported)'}")
    excess = excess_toolsets(exposed, ALLOWED_TOOLSETS)
    if excess:
        print(
            "GATE CLOSED — toolsets beyond the allowed set "
            f"{sorted(ALLOWED_TOOLSETS)}: {excess}",
            file=sys.stderr,
        )
        return 1
    print(f"gate open: exposed ⊆ {sorted(ALLOWED_TOOLSETS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
