# Hermes bridge setup (~/.hermes)

How to run the study guide as a locally hosted
[hermes-agent](https://hermes-agent.nousresearch.com/docs) **profile**
whose ONLY toolset is our MCP server — the guide's entire world: reads,
scoped writes, and the three reviewed actions, nothing else. The profile's
OpenAI-compatible gateway (127.0.0.1:8642) is what the bridge brain in
`tools/serve_shelf.py` (later work) will talk to; `tools/hermes_probe.py`
is its startup gate.

Config keys below were verified against the live docs on 2026-07-01:

- MCP: <https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp>
- API server: <https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server>
- Configuration: <https://hermes-agent.nousresearch.com/docs/user-guide/configuration>
- Toolsets reference: <https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference>
- Profiles: <https://hermes-agent.nousresearch.com/docs/reference/profile-commands>
- SOUL.md: <https://hermes-agent.nousresearch.com/docs/user-guide/features/personality>
- Security: <https://hermes-agent.nousresearch.com/docs/user-guide/security>

## 0. Creating the second-arrow profile

Each Hermes profile carries its own `config.yaml`, `.env`, and `SOUL.md`
under `~/.hermes/profiles/<name>/` (verified: profile-commands reference),
so the study guide stays fully isolated from any other Hermes use.

In the app (v0.17.0), the **New profile** dialog has three fields:

- **Name**: `second-arrow`
- **Clone from**: your default profile (carries provider keys over)
- **SOUL.md**: paste the contents of `hermes/SOUL.md` from this repo —
  the guide persona, adapted from CLAUDE.md for a small model: the
  "Where are you right now?" opener, tense routing, hard rules, and the
  wrap-up ritual, all phrased as short imperative tool choreography.

CLI equivalent (verified against the profile-commands reference —
`--clone` copies config, .env, SOUL.md, and skills from the current
profile):

```bash
hermes profile create second-arrow --clone --description "Second Arrow study guide"
cp /Users/jacob/Git/second-arrow/hermes/SOUL.md ~/.hermes/profiles/second-arrow/SOUL.md
hermes profile use second-arrow      # or one-off: hermes -p second-arrow <command>
```

Sections 1–4 below go in the PROFILE's own
`~/.hermes/profiles/second-arrow/config.yaml` and `.env` — not the global
ones. SOUL.md occupies "slot #1 in the system prompt" (verified:
personality docs), so the persona rides every turn.

## 1. Register our MCP server — the profile's `config.yaml`

The profile gets tools ONLY through our stdio MCP server. Under the
documented top-level `mcp_servers:` key (stdio transport uses `command` +
`args`; `tools.include` is the documented include-list, and "include wins"
when both include and exclude are present):

```yaml
mcp_servers:
  second_arrow:
    command: "uv"
    args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]
    tools:
      include:
        # actions (argv-validated by serve_shelf, subprocess, no shell)
        - fetch_talk
        - rebuild_shelf
        - speak
        # reads (pinned inside the repo)
        - get_path
        - get_library_index
        - read_transcript
        - read_notes
        - get_curriculum
        - search_history
        # scoped writes (STUDY.md, per-talk notes.md, journal append-only)
        - update_path
        - update_notes
        - append_journal
      prompts: false
      resources: false
```

Per the docs, each MCP server generates a runtime toolset named
`mcp-<server>` — so this one is **`mcp-second_arrow`** — and the tools
register as `mcp_second_arrow_fetch_talk` etc.

## 2. Restrict the profile to that toolset

Top-level `platform_toolsets:` with the platform key, listing the derived
toolset name (not the bare server name). Pin every surface the profile
serves — the gateway and, if you also chat with this profile in the CLI,
the CLI too:

```yaml
platform_toolsets:
  api_server:
    - mcp-second_arrow
    - clarify        # asks the user a question; touches nothing
  cli:
    - mcp-second_arrow
    - clarify
```

**Docs ambiguity, flagged rather than guessed:** the configuration page
shows short platform keys (`cli`, `api_server`, `telegram`, ...) while the
toolsets-reference page shows `hermes-`-prefixed identifiers
(`hermes-cli`, `hermes-api-server`). This snippet follows the
configuration page (`api_server`); if the toolsets don't show up on the
gateway, try `hermes-api-server` — and either way, `hermes_probe.py` will
tell you what actually got exposed.

## 3. Belt and braces: disable the built-in toolsets globally

`agent.disabled_toolsets` is applied AFTER per-platform config, so a
toolset listed here is removed everywhere even if a platform row still
names it. Cover terminal/file/web/browser/code-exec and friends (names
from the toolsets reference):

```yaml
agent:
  disabled_toolsets:
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
```

Left enabled: `clarify` (user inquiries only) and our `mcp-second_arrow`.
Caution from the wild (hermes-agent issue #33924): put only core toolset
names in this list, never platform-bundle names like `hermes-api-server` —
a bundle name here can silently kill ALL tools on the gateway path.

## 4. API server — the profile's `.env`

The API server is configured through env vars only for now (the docs say
"config.yaml support coming in a future release"):

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=<generate-a-long-random-key>
API_SERVER_PORT=8642
API_SERVER_HOST=127.0.0.1
```

Bearer auth via the `Authorization` header, key = `API_SERVER_KEY`.
Endpoints the bridge cares about: `POST /v1/chat/completions` (SSE
streaming), `GET /v1/toolsets`, `GET /health`. Keep the `.env` at
`chmod 600`; the bridge brain will read the same key from `HERMES_API_KEY`.

## 5. Model phases

- **Phase 1 (now):** the profile runs on your existing codex/gpt-5.5
  provider — a hosted brain doing the reasoning, our MCP server doing the
  reading and the hands. In the app, pick it from the profile's model
  dropdown; in YAML:

```yaml
model:
  default: gpt-5.5           # phase 2: gemma4:12b
  provider: custom           # your codex-backed OpenAI-compatible endpoint
  base_url: https://<your-codex-provider>/v1
  api_key: ${CODEX_API_KEY}  # ${VAR} substitution from the profile .env
```

- **Phase 2:** switch the model dropdown to local `gemma4:12b` (Ollama's
  OpenAI-compatible endpoint: `provider: custom`,
  `base_url: http://localhost:11434/v1`). Nothing else changes — the
  SOUL.md choreography is written for a small model on purpose.

## 6. The privacy rule

The hosted model (phase 1) sees exactly what the tools return — so the
tool surface IS the privacy boundary:

- **The journal is write-only by design.** `append_journal` exists; no
  tool reads `journal/` back. A hosted brain can leave a reflection but
  can never retrieve one.
- Reads expose transcripts, curriculum, STUDY.md, per-talk notes, and
  keyword-matched snippets of past shelf conversations
  (`search_history`) — study material, not private prose.
- Writes land only on the claude chat brain's allowlist: `STUDY.md`,
  `library/<slug>/notes.md`, `journal/YYYY-MM-DD.md` (append). Inputs are
  size-capped (~64KB) and slugs sanitized; every path is verified to
  resolve inside the repo.
- The disabled toolsets above remove any Hermes-side path
  (file/terminal/memory) around the surface, and the actions still pass
  through serve_shelf's `validate_tool_call` unchanged.

## 7. Verify before trusting (acceptance test)

```bash
# 1. The MCP server answers a real handshake with exactly the twelve tools:
uv run /Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py   # Hermes-side; or the smoke client

# 2. Start the profile's gateway, then gate-check it:
HERMES_API_KEY=<your API_SERVER_KEY> uv run /Users/jacob/Git/second-arrow/tools/hermes_probe.py
```

The probe exits 0 only when the exposed toolsets ⊆
`{mcp-second_arrow, clarify}`; otherwise it exits 1 listing the excess.
The bridge brain will run the same gate at startup and refuse to talk to
an over-provisioned gateway.
