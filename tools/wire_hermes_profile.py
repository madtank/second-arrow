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
5. Registers our MCP server (14 tools) + platform_toolsets pinning.
6. Enables the profile's API server on 127.0.0.1:8642 with a fresh key
   (printed ONCE so you can export HERMES_API_KEY for the aX bridge).

After running: restart the Hermes gateway on the second-arrow profile, then
verify with:  uv run tools/hermes_probe.py
"""

import re
import secrets
import shutil
import sys
import time
from pathlib import Path

PROFILE = Path.home() / ".hermes/profiles/second-arrow"
CONFIG = PROFILE / "config.yaml"
ENV = PROFILE / ".env"

MCP_BLOCK = """
mcp_servers:
  second_arrow:
    command: "uv"
    args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]
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


def main() -> None:
    if not CONFIG.exists():
        raise SystemExit(f"Profile config not found: {CONFIG} — create the "
                         "second-arrow profile in the Hermes app first.")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    changed = []

    text = CONFIG.read_text()
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
                       "+ platform_toolsets pinned")

    if text != original:
        backup = CONFIG.with_suffix(f".yaml.bak-{stamp}")
        shutil.copy2(CONFIG, backup)
        CONFIG.write_text(text)
        print(f"config.yaml updated (backup: {backup.name})")
    else:
        print("config.yaml already wired — no changes")

    env_text = ENV.read_text() if ENV.exists() else ""
    if "API_SERVER_ENABLED" not in env_text:
        key = secrets.token_hex(24)
        backup = ENV.with_suffix(f".env.bak-{stamp}")
        if ENV.exists():
            shutil.copy2(ENV, backup)
        ENV.write_text(env_text.rstrip("\n") + f"""

# Second Arrow: API server for the shelf/aX bridge
API_SERVER_ENABLED=true
API_SERVER_KEY={key}
API_SERVER_PORT=8642
API_SERVER_HOST=127.0.0.1
""")
        ENV.chmod(0o600)
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
