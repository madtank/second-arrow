# Hermes bridge setup (~/.hermes)

How to run the study guide as a locally hosted
[hermes-agent](https://hermes-agent.nousresearch.com/docs) **profile**
whose ONLY toolset is our MCP server — the guide's entire world: reads,
scoped writes, and the three reviewed actions, nothing else. The profile's
OpenAI-compatible gateway (127.0.0.1:8642) is what the bridge brain in
`tools/serve_shelf.py` (later work) will talk to; `tools/hermes_probe.py`
is its startup gate.

Distilled standing reference (endpoints, sessions, model selection,
security): [docs/hermes-reference.md](hermes-reference.md) — refreshed
2026-07-02 against a **full local mirror of the docs site** at
[docs/hermes/](hermes/INDEX.md) (Hermes v0.18.0). Config keys below were
verified against the live docs on 2026-07-01:

- MCP: <https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp>
- API server: <https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server>
- Configuration: <https://hermes-agent.nousresearch.com/docs/user-guide/configuration>
- Toolsets reference: <https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference>
- Profiles: <https://hermes-agent.nousresearch.com/docs/reference/profile-commands>
- SOUL.md: <https://hermes-agent.nousresearch.com/docs/user-guide/features/personality>
- Security: <https://hermes-agent.nousresearch.com/docs/user-guide/security>

## Wiring paths — do it by hand with the official CLI first

Hermes ships official commands for most of what
`tools/wire_hermes_profile.py` does; prefer them (they validate as they
go), and keep the script as the fallback that does everything in one
sweep. Verified against the CLI reference on 2026-07-02:

```bash
# 1. Profile (also possible in the app's Profiles pane — section 0)
hermes profile create second-arrow --clone

# 2. Register our MCP server (writes mcp_servers into the profile config;
#    --args passes the rest of argv to the stdio command, so put it last)
hermes -p second-arrow mcp add second_arrow \
  --command uv --args run /Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py
hermes -p second-arrow mcp configure second_arrow   # tick exactly our 14 tools
hermes -p second-arrow mcp test second_arrow        # handshake check

# 3. Model (phase 1) — or the app's Settings → Model pane for this profile
hermes -p second-arrow config set model.default gpt-5.5
hermes -p second-arrow config set model.provider openai-codex

# 4. Toolset restriction — interactive per-platform UI
hermes -p second-arrow tools            # pin api_server+cli to mcp-second_arrow, clarify
hermes -p second-arrow tools --summary  # confirm
```

Still manual (no CLI/GUI path exists yet):

- **API server enablement is env-only** ("config.yaml support coming in a
  future release") — edit the profile `.env` as in section 4;
  `hermes -p second-arrow config env-path` prints its location.
- `agent.disabled_toolsets` (section 3) and `platform_toolsets` beyond what
  `hermes tools` offers — `hermes config edit` or the wire script.

The desktop app covers profile creation (Profiles pane), MCP server
registration (Settings pane for MCP servers), and the per-profile model
(Settings → Model). Granular per-tool toggling and toolset pinning in the
GUI are not documented — use `hermes mcp configure` / `hermes tools`.

After any config change: `/reload-mcp` refreshes MCP servers inside a
running session, but model/toolset changes want
`hermes -p second-arrow gateway restart`. Then gate with
`uv run tools/hermes_probe.py` (section 7).

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

**Ambiguity resolved (2026-07-02, source-verified in
`hermes_cli/toolset_validation.py`):** `platform_toolsets` **keys** are the
short platform names (`cli`, `api_server`, `cron`, ...); the **values** are
toolset names (`hermes-cli`-style bundles, core sets like `clarify`, or
derived `mcp-<server>` names). The snippet above is the right shape. Since
v0.18.0, invalid toolset names here produce loud startup warnings —
including a "resolves to zero valid toolsets" alert — instead of silent
tool loss; `hermes_probe.py` still confirms what actually got exposed.
Also pin the **`cron`** platform row the same way if we ever schedule jobs
in this profile (see hermes-reference §7): the cron default is the full
`hermes-cli` bundle.

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

Continuity (verified in source, 2026-07-02): send a stable
`X-Hermes-Session-Id` per thread (`shelf-guide` for the shelf; `ax-<sender>`
per aX correspondent) with ONLY the new user message — when the header is
present the server loads history from the profile's state.db and ignores
body history, preserving tool-call context across turns; the header
requires the API key and is echoed back on responses. Don't use
`/v1/responses` chaining for long threads (stored responses cap at 100,
LRU-evicted). Concurrency: `gateway.api_server.max_concurrent_runs`
(default 10) returns HTTP 429 over the cap — the bridge should retry with
backoff and serialize turns within one thread itself.

## 5. Model phases

Who decides the model (verified 2026-07-02, configuring-models + desktop
docs): the profile's `config.yaml` `model.default` is the single source of
truth for the gateway. In the app, set it in **Settings → Model** for this
profile ("the only place that writes it") — NOT the composer dropdown next
to the mic, which is "sticky UI state and never touches your default"
(per-device, app-only). Per-request `model` on the API is accepted but
ignored for routing — **unless** it names a configured `model_routes`
alias (v0.18.0, source-verified; see hermes-reference §3), which we don't
use. `GET /v1/models` advertises the profile name (`second-arrow`), not
the LLM — so anything that wants to *display* the model reads this file's
`model.default`. Changes apply to the next new session; restart the
gateway (`hermes -p second-arrow gateway restart`) to pick them up.

- **Phase 1 (now):** the profile runs on your existing codex/gpt-5.5
  provider — a hosted brain doing the reasoning, our MCP server doing the
  reading and the hands. In the app: Settings → Model; in YAML:

```yaml
model:
  default: gpt-5.5           # phase 2: gemma4:12b
  provider: custom           # your codex-backed OpenAI-compatible endpoint
  base_url: https://<your-codex-provider>/v1
  api_key: ${CODEX_API_KEY}  # ${VAR} substitution from the profile .env
```

- **Phase 2:** switch Settings → Model to local `gemma4:12b` (Ollama's
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
