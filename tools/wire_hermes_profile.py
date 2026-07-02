#!/usr/bin/env python3
"""Wire the ~/.hermes second-arrow profile to the Second Arrow guide.

Run it yourself (it edits your Hermes profile, so it should be your hand):

    uv run tools/wire_hermes_profile.py

What it does — all with timestamped backups, all idempotent:
1. Restricts the profile's toolsets to our MCP server (+ clarify).
2. Disables the inherited ax-platform plugin (it carries your OLD agent's
   identity; the second-arrow aX presence goes through tools/ax_presence.py).
3. Fills agent.disabled_toolsets (belt and braces per docs/hermes-bridge.md).
4. Sets the phase-1 model: gpt-5.5 via your openai-codex provider
   (ollama-launch stays configured — flip the dropdown for phase 2).
5. Registers our MCP server (14 tools) + platform_toolsets pinning —
   api_server, cli, AND cron (v0.18 layers MCP toolsets onto cron jobs;
   the cron default would otherwise be the full hermes-cli bundle).
6. Pins mcp_servers.second_arrow.sampling.enabled: false — v0.18 enables
   MCP sampling (server-requested inference) by default; our server never
   uses it, so least privilege says off.
7. Defines two model_routes for the gateway — deep (gpt-5.5/openai-codex)
   and local (gemma4:12b via the local Ollama custom endpoint) — so the
   shelf's per-request `model` picker has honest, named targets.
   (model_routes is source-verified in gateway/platforms/api_server.py,
   not yet documented — see docs/hermes-reference.md §3.)
8. Enables the profile's API server on 127.0.0.1:8642 with a fresh key
   (printed ONCE so you can export HERMES_API_KEY for the aX bridge).

Profile dir override (tests, odd layouts):
    SECOND_ARROW_HERMES_PROFILE=/path/to/profile uv run tools/wire_hermes_profile.py

After running: restart the Hermes gateway on the second-arrow profile, then
verify with:  uv run tools/hermes_probe.py

Tests: uv run --with pytest pytest tools/tests/test_wire_hermes_profile.py -v
"""

import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

PROFILE = Path(
    os.environ.get(
        "SECOND_ARROW_HERMES_PROFILE",
        str(Path.home() / ".hermes/profiles/second-arrow"),
    )
)

MCP_BLOCK = """
mcp_servers:
  second_arrow:
    command: "uv"
    args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]
    sampling:
      enabled: false
    tools:
      include:
        - fetch_talk
        - rebuild_shelf
        - speak
        - get_path
        - get_library_index
        - read_transcript
        - read_notes
        - get_curriculum
        - search_history
        - update_path
        - update_notes
        - append_journal
        - update_session_summary
        - write_artifact
      prompts: false
      resources: false

platform_toolsets:
  api_server:
    - mcp-second_arrow
    - clarify
  cli:
    - mcp-second_arrow
    - clarify
  cron:
    - mcp-second_arrow
"""

# The exact stdio args line MCP_BLOCK writes — the anchor for inserting
# sampling.enabled: false into a config wired by an older run.
ARGS_LINE = (
    '    args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]\n'
)
SAMPLING_LINES = "    sampling:\n      enabled: false\n"

CRON_ROW = "  cron:\n    - mcp-second_arrow\n"

# Named model routes for the api_server platform (undocumented but
# source-verified; the docs page still calls the per-request model
# cosmetic). Shape per route: {model, provider, api_key?, base_url?}.
# Local Ollama goes through the documented Custom Endpoint flow
# (provider: custom + base_url, no key needed).
ROUTES_BLOCK = """
# Second Arrow: named model routes for the shelf's per-request picker
# (source-verified in gateway/platforms/api_server.py; see
# docs/hermes-reference.md §3). The profile default in `model:` stays
# the source of truth — these are opt-in aliases.
platforms:
  api_server:
    extra:
      model_routes:
        deep:
          model: gpt-5.5
          provider: openai-codex
        local:
          model: gemma4:12b
          provider: custom
          base_url: http://localhost:11434/v1
"""

DISABLED = """  disabled_toolsets:
    - terminal
    - file
    - web
    - browser
    - code_execution
    - coding
    - computer_use
    - search
    - x_search
    - debugging
    - delegation
    - cronjob
    - project
    - kanban
    - todo
    - skills
    - memory
    - session_search
    - context_engine
    - image_gen
    - video_gen
    - vision
    - video
    - tts
    - spotify
    - homeassistant
    - discord
    - discord_admin
    - feishu_doc
    - feishu_drive
    - yuanbao
    - safe
"""


def add_sampling_off(text: str) -> tuple[str, bool]:
    """Pin sampling.enabled: false on an already-wired second_arrow block.

    Anchored on the exact args line the wire script writes; a config that
    already says sampling (anywhere under mcp_servers) is left alone.
    """
    if "mcp_servers:" not in text or "sampling:" in text:
        return text, False
    if ARGS_LINE not in text:
        print(
            "! could not find the second_arrow args line — add "
            "sampling: {enabled: false} to mcp_servers.second_arrow manually",
            file=sys.stderr,
        )
        return text, False
    return text.replace(ARGS_LINE, ARGS_LINE + SAMPLING_LINES, 1), True


def add_cron_pinning(text: str) -> tuple[str, bool]:
    """Add the cron platform row to an existing platform_toolsets block."""
    match = re.search(r"^platform_toolsets:[ \t]*\n((?:[ \t]+\S.*\n)*)", text, re.M)
    if not match:
        return text, False
    if re.search(r"^  cron:", match.group(1), re.M):
        return text, False
    insert_at = match.start(1)
    return text[:insert_at] + CRON_ROW + text[insert_at:], True


def add_model_routes(text: str) -> tuple[str, bool]:
    """Append the model_routes platforms block, once.

    A config that already has a top-level platforms: block would need a
    hand-merge (appending a duplicate key is not YAML) — say so instead
    of guessing.
    """
    if "model_routes:" in text:
        return text, False
    if re.search(r"^platforms:", text, re.M):
        print(
            "! config already has a top-level platforms: block — merge the "
            "model_routes from tools/wire_hermes_profile.py (ROUTES_BLOCK) "
            "into it by hand",
            file=sys.stderr,
        )
        return text, False
    return text.rstrip("\n") + "\n" + ROUTES_BLOCK, True


def main(profile: Path | None = None) -> None:
    profile = profile or PROFILE
    config = profile / "config.yaml"
    env = profile / ".env"
    if not config.exists():
        raise SystemExit(f"Profile config not found: {config} — create the "
                         "second-arrow profile in the Hermes app first.")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    changed = []

    text = config.read_text()
    original = text

    if "toolsets:\n  - mcp-second_arrow" not in text:
        new = text.replace("toolsets:\n  - hermes-cli\n  - web\n",
                           "toolsets:\n  - mcp-second_arrow\n  - clarify\n", 1)
        if new == text:
            print("! could not find the expected `toolsets:` block — set it "
                  "manually to [mcp-second_arrow, clarify]", file=sys.stderr)
        else:
            text = new
            changed.append("toolsets restricted to mcp-second_arrow + clarify")

    if "enabled:\n    - ax-platform" in text:
        text = text.replace(
            "plugins:\n  disabled: []\n  enabled:\n    - ax-platform\n",
            "plugins:\n  disabled:\n    - ax-platform\n  enabled: []\n", 1)
        changed.append("ax-platform plugin disabled (old agent identity)")

    if "  disabled_toolsets: []\n" in text:
        text = text.replace("  disabled_toolsets: []\n", DISABLED, 1)
        changed.append("agent.disabled_toolsets filled (belt and braces)")

    ollama_model = ("model:\n  api_key: ollama\n"
                    "  base_url: http://127.0.0.1:11434/v1\n"
                    "  default: gemma4:12b\n  provider: ollama-launch\n")
    if ollama_model in text:
        text = text.replace(ollama_model,
                            "model:\n  default: gpt-5.5\n"
                            "  provider: openai-codex\n", 1)
        changed.append("model: gpt-5.5 via openai-codex (phase 1)")

    if "mcp_servers:" not in text:
        marker = "\n# ── Fallback Model"
        if marker in text:
            text = text.replace(marker, MCP_BLOCK + marker, 1)
        else:
            text = text.rstrip("\n") + "\n" + MCP_BLOCK
        changed.append("mcp_servers.second_arrow registered (14 tools) "
                       "+ platform_toolsets pinned (api_server, cli, cron)")

    # Hardening for configs wired by an earlier run of this script —
    # each step finds its own anchor and is a no-op the second time.
    text, did = add_sampling_off(text)
    if did:
        changed.append("mcp sampling disabled (least privilege, v0.18 "
                       "default-on)")
    text, did = add_cron_pinning(text)
    if did:
        changed.append("platform_toolsets.cron pinned to mcp-second_arrow")
    text, did = add_model_routes(text)
    if did:
        changed.append("model_routes defined: deep (gpt-5.5/openai-codex), "
                       "local (gemma4:12b via local Ollama)")

    if text != original:
        backup = config.with_suffix(f".yaml.bak-{stamp}")
        shutil.copy2(config, backup)
        config.write_text(text)
        print(f"config.yaml updated (backup: {backup.name})")
    else:
        print("config.yaml already wired — no changes")

    env_text = env.read_text() if env.exists() else ""
    if "API_SERVER_ENABLED" not in env_text:
        key = secrets.token_hex(24)
        backup = env.with_suffix(f".env.bak-{stamp}")
        if env.exists():
            shutil.copy2(env, backup)
        env.write_text(env_text.rstrip("\n") + f"""

# Second Arrow: API server for the shelf/aX bridge
API_SERVER_ENABLED=true
API_SERVER_KEY={key}
API_SERVER_PORT=8642
API_SERVER_HOST=127.0.0.1
""")
        env.chmod(0o600)
        changed.append("API server enabled on 127.0.0.1:8642")
        print(f".env updated (backup: {backup.name})")
        print(f"\n  export HERMES_API_KEY={key}\n")
        print("  ^ save this — the aX bridge and probe read it; it is "
              "also in the profile .env as API_SERVER_KEY")
    else:
        m = re.search(r"^API_SERVER_KEY=(\S+)", env_text, re.M)
        print(".env already has API_SERVER_ENABLED — untouched"
              + (f" (key ends …{m.group(1)[-6:]})" if m else ""))

    print("\nDone." if changed else "\nNothing to do.")
    for c in changed:
        print(f"  • {c}")
    print("\nNext: restart the Hermes gateway on the second-arrow profile, "
          "then run:  uv run tools/hermes_probe.py")


if __name__ == "__main__":
    main()
