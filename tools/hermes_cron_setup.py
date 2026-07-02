#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""Install the durable nightly-prep cron job on the Hermes gateway.

User-run and idempotent: creates or updates exactly ONE job named
`nightly-prep` on the RUNNING second-arrow gateway via its REST jobs API
(docs/hermes-reference.md §7 — POST/PATCH /api/jobs, same body shape as
`hermes cron`):

- schedule: 03:23 daily (5-field cron `23 3 * * *`);
- provider + model PINNED to the `deep` route's pair (gpt-5.5 via
  openai-codex) — an unpinned job snapshots the global default and FAILS
  CLOSED when that default later changes (v0.18 gotcha), so pin from the
  start and re-run this script after any deliberate model switch;
- enabled_toolsets: ["mcp-second_arrow"] — v0.18 layers MCP toolsets onto
  per-job toolsets, so the job gets exactly our 14 tools and nothing else;
- deliver: local (files under the profile's cron/output/), and the prompt
  ends in [SILENT] so nothing pings any platform — failures still deliver.

On success it also writes/refreshes library/.prep-cron.json
({installed_at, schedule}) — the marker serve_shelf's /health surfaces on
the begin-here machinery card. The marker records that THIS script ran;
the job itself lives in the gateway.

Run:
    HERMES_API_KEY=... uv run tools/hermes_cron_setup.py
    uv run tools/hermes_cron_setup.py --dry-run   # print the job JSON only

Requirements: the gateway must be up (hermes -p second-arrow gateway
start) and HERMES_API_KEY set (or readable from the profile .env — a
READ-ONLY fallback; this script never writes under ~/.hermes).

Tests: uv run --with pytest pytest tools/tests/test_hermes_cron_setup.py -v
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKER_PATH = REPO_ROOT / "library" / ".prep-cron.json"

DEFAULT_URL = "http://127.0.0.1:8642"
PROFILE_ENV = Path.home() / ".hermes" / "profiles" / "second-arrow" / ".env"
TIMEOUT = 10  # seconds per REST call

JOB_NAME = "nightly-prep"
SCHEDULE = "23 3 * * *"  # 03:23 daily, 5-field cron
PROVIDER = "openai-codex"  # the `deep` route's underlying pair, pinned
MODEL = "gpt-5.5"

PROMPT = """\
Data-only nightly prep for the Second Arrow library. Using only your
tools, quietly and within these walls:

1. Read STUDY.md (get_path) and the library index (get_library_index).
2. For each talk in STUDY.md's Queued section that is ALREADY in the
   library: make sure it has notes and a primer. If a primer is missing,
   read the transcript (read_transcript), write a short 60-90 second
   primer — who the teacher is, what to listen for — into the talk's
   notes via update_notes (under a "## Primer" heading), and speak it
   with speak.
3. NEVER ingest anything that is not explicitly listed with a URL in the
   curriculum (get_curriculum) AND already queued in STUDY.md; downloads
   are single-item only. When in doubt, fetch nothing.
4. No games, no artifacts, no journal entries overnight.
5. If anything changed: rebuild_shelf, and update ONLY the Queued
   annotations in STUDY.md via update_path — never reorder or rewrite
   the other sections.

Finish with a summary of at most 3 lines ending with [SILENT]."""


# --- pure parts (tested in tools/tests/test_hermes_cron_setup.py) -----------


def build_job() -> dict:
    """The one nightly-prep job, as the /api/jobs body (hermes-cron shape)."""
    return {
        "name": JOB_NAME,
        "schedule": SCHEDULE,
        "prompt": PROMPT,
        "provider": PROVIDER,
        "model": MODEL,
        "enabled_toolsets": ["mcp-second_arrow"],
        "deliver": "local",
    }


def find_job(payload, name: str = JOB_NAME):
    """The stored job matching `name` (case-insensitive), or None.

    The docs pin the endpoints but not the list body; tolerate a bare
    list or a {"jobs"|"data": [...]} wrapper, and read the id from
    "id"/"job_id". Anything unrecognizable is simply not a match.
    """
    if isinstance(payload, dict):
        items = payload.get("jobs", payload.get("data", []))
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").lower() == name.lower():
            job_id = item.get("id") or item.get("job_id")
            if isinstance(job_id, (str, int)) and str(job_id):
                return {"id": str(job_id), "job": item}
    return None


def marker_content(now: str | None = None) -> dict:
    return {
        "installed_at": now
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schedule": SCHEDULE,
    }


def read_api_key(env_path: Path | None = None) -> str:
    """HERMES_API_KEY, else a READ-ONLY parse of the profile .env."""
    key = os.environ.get("HERMES_API_KEY", "")
    if key:
        return key
    path = env_path or PROFILE_ENV
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"^\s*API_SERVER_KEY\s*=\s*(\S+)\s*$", text, re.M)
    return match.group(1) if match else ""


# --- the REST calls ----------------------------------------------------------


def _request(method: str, base: str, path: str, api_key: str, body: dict | None = None):
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {api_key}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read()
    return json.loads(raw) if raw.strip() else {}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Install/refresh the nightly-prep cron job on the gateway."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the job JSON and exit — no gateway, no marker",
    )
    args = parser.parse_args(argv)

    job = build_job()
    if args.dry_run:
        print(json.dumps(job, indent=2))
        return 0

    base = os.environ.get("HERMES_URL", DEFAULT_URL)
    api_key = read_api_key()
    if not api_key:
        print(
            "No Hermes API key — export HERMES_API_KEY (or wire the profile "
            "first: uv run tools/wire_hermes_profile.py).",
            file=sys.stderr,
        )
        return 1

    try:
        _request("GET", base, "/health", api_key)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
        print(
            f"Hermes gateway not reachable at {base} ({error}) — start it: "
            "hermes -p second-arrow gateway start",
            file=sys.stderr,
        )
        return 1

    try:
        existing = find_job(_request("GET", base, "/api/jobs", api_key))
    except urllib.error.HTTPError as error:
        print(
            f"GET /api/jobs answered {error.code} — check HERMES_API_KEY.",
            file=sys.stderr,
        )
        return 1
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
        print(f"GET /api/jobs failed: {error}", file=sys.stderr)
        return 1

    try:
        if existing:
            _request("PATCH", base, f"/api/jobs/{existing['id']}", api_key, job)
            print(f"updated job {JOB_NAME!r} (id {existing['id']})")
        else:
            _request("POST", base, "/api/jobs", api_key, job)
            print(f"created job {JOB_NAME!r}")
    except urllib.error.HTTPError as error:
        print(
            f"writing the job answered {error.code} — the gateway refused it; "
            "check the gateway logs (hermes -p second-arrow gateway status).",
            file=sys.stderr,
        )
        return 1
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
        print(f"writing the job failed: {error}", file=sys.stderr)
        return 1

    marker = marker_content()
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    print(f"marker refreshed: {MARKER_PATH} ({marker['schedule']})")
    print(
        f"nightly prep runs at 03:23 daily, pinned to {PROVIDER}/{MODEL}, "
        "toolset mcp-second_arrow, delivering local + [SILENT]."
    )
    print(
        "NOTE: after any deliberate model switch, re-run this script so the "
        "pin follows (unpinned/stale jobs fail closed by design)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
