# Hermes bridge setup (~/.hermes)

How to wire a locally running [hermes-agent](https://hermes-agent.nousresearch.com/docs)
to Second Arrow so its OpenAI-compatible gateway (127.0.0.1:8642) can act
in the study space through exactly three reviewed tools — and nothing else.
The bridge brain in `tools/serve_shelf.py` (later work) will talk to that
gateway; `tools/hermes_probe.py` is its startup gate.

Config keys below were verified against the live docs on 2026-07-01:

- MCP: <https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp>
- API server: <https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server>
- Configuration: <https://hermes-agent.nousresearch.com/docs/user-guide/configuration>
- Toolsets reference: <https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference>
- Security: <https://hermes-agent.nousresearch.com/docs/user-guide/security>

## 1. Register our MCP server — `~/.hermes/config.yaml`

Hermes gets tools ONLY through our stdio MCP server. Under the documented
top-level `mcp_servers:` key (stdio transport uses `command` + `args`;
`tools.include` is the documented include-list, and "include wins" when
both include and exclude are present):

```yaml
mcp_servers:
  second_arrow:
    command: "uv"
    args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]
    tools:
      include: [fetch_talk, rebuild_shelf, speak]
      prompts: false
      resources: false
```

Per the docs, each MCP server generates a runtime toolset named
`mcp-<server>` — so this one is **`mcp-second_arrow`** — and the tools
register as `mcp_second_arrow_fetch_talk` etc.

## 2. Pin the API-server platform to that toolset

Top-level `platform_toolsets:` with the platform key, listing the derived
toolset name (not the bare server name):

```yaml
platform_toolsets:
  api_server:
    - mcp-second_arrow
    - clarify        # asks the user a question; touches nothing
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

## 4. API server — `~/.hermes/.env`

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
streaming), `GET /v1/toolsets`, `GET /health`. Keep `~/.hermes/.env` at
`chmod 600`; the bridge brain will read the same key from `HERMES_API_KEY`.

## 5. Model phases

- **Phase 1 (now):** Hermes runs on the existing codex/gpt-5.5 provider —
  a hosted brain doing the reasoning, our MCP server doing the hands.
- **Phase 2:** swap `model:` to local `gemma4:12b` (Ollama's
  OpenAI-compatible endpoint via `provider: custom`,
  `base_url: http://localhost:11434/v1`). Config shape per the
  configuration docs:

```yaml
model:
  default: gpt-5.5           # phase 2: gemma4:12b
  provider: custom           # your codex-backed OpenAI-compatible endpoint
  base_url: https://<your-codex-provider>/v1
  api_key: ${CODEX_API_KEY}  # ${VAR} substitution from ~/.hermes/.env
```

## 6. The privacy rule

Hosted brains (phase 1, and any future non-local model) receive **talk
transcripts and curriculum context only — never the journal**. `journal/`
and `library/.chat/` stay local: they are not exposed as MCP tools or
resources, the bridge never puts them in a prompt to the gateway, and the
disabled toolsets above remove any Hermes-side path (file/terminal/memory)
that could reach them. The three tools can write only what serve_shelf's
`validate_tool_call` allows (library ingest, shelf rebuild, an mp3 under
`library/`).

## 7. Verify before trusting

```bash
# 1. The MCP server answers a real handshake with exactly three tools:
uv run /Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py   # Hermes-side; or the smoke client

# 2. Start hermes-agent, then gate-check the gateway:
HERMES_API_KEY=<your API_SERVER_KEY> uv run /Users/jacob/Git/second-arrow/tools/hermes_probe.py
```

The probe exits 0 only when the exposed toolsets ⊆
`{mcp-second_arrow, clarify}`; otherwise it exits 1 listing the excess.
The bridge brain will run the same gate at startup and refuse to talk to
an over-provisioned gateway.
