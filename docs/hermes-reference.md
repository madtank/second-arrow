# Hermes reference (distilled from live docs)

Standing knowledge base for the `second-arrow` Hermes profile, fetched from
<https://hermes-agent.nousresearch.com/docs> and the
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
source on **2026-07-02**. Facts over prose; each section cites its page.
Builders: read this before re-fetching the docs.

## 1. Install & first run

[quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)

- `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` (or the desktop app).
- Setup: `hermes setup` (full wizard), `hermes model` (provider walk-through), or `hermes setup --portal`.
- Secrets live in `~/.hermes/.env`; settings in `~/.hermes/config.yaml`.
- Models need a **minimum 64K-token context window** for tool use
  ([providers](https://hermes-agent.nousresearch.com/docs/integrations/providers));
  for Ollama set `OLLAMA_CONTEXT_LENGTH=64000` before startup.
- Diagnostics: `hermes doctor [--fix]`, `hermes status` (shows `Model: <provider>/<model>`).

## 2. Profile lifecycle

[profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) ·
[cli-commands](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)

- Each profile is a full isolated agent under `~/.hermes/profiles/<name>/`:
  its own `config.yaml`, `.env`, `SOUL.md`, memories, sessions, skills, cron
  jobs, and state database.
- `hermes profile create <name> [--clone|--clone-all|--clone-from <src>]`,
  `list`, `show`, `use <name>` (sticky default, "like kubectl config
  use-context"), `delete`, `rename`, `alias`, `export`/`import`.
- Target a profile per-invocation with `hermes -p <name> <cmd>` — works with
  every subcommand — or via a profile alias command.
- Each profile runs **its own gateway process**; run several concurrently by
  giving each a distinct `API_SERVER_PORT` in its `.env`.
- Desktop app has a Profiles pane; sessions can run across multiple profiles
  simultaneously.

## 3. Model selection — who decides, who displays

[configuring-models](https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models) ·
[desktop](https://hermes-agent.nousresearch.com/docs/user-guide/desktop) ·
[api-server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)

- The per-profile default lives in the profile's `config.yaml`:
  `model: {default: ..., provider: ..., base_url: ..., api_mode: ...}`.
  Set it via `hermes -p <name> config set model.default <model>`, the
  dashboard **Settings → Model** pane ("the only place that writes it"), or
  `/model <model> --provider <p> --global` in chat.
- The desktop **composer model picker** (next to the mic) is "sticky UI state
  and never touches your default" — remembered per device, affects only that
  app conversation. It does NOT change what the API server uses.
- `/model X` without `--global` switches the current session only.
- A model change applies to the **next new session**; "existing sessions keep
  their model." A running gateway needs `hermes gateway restart` to pick up a
  changed default.
- **The API server never honors a per-request `model`.** Docs: "the `model`
  field in requests is accepted but the actual LLM model used is configured
  server-side in config.yaml." Source (`gateway/platforms/api_server.py`):
  `model_name = body.get("model", self._model_name)` — used only to echo in
  response metadata. Unknown values produce no error.
- **The actual LLM model is not readable over the API.** `GET /v1/models`
  advertises `API_SERVER_MODEL_NAME` > active profile name > `hermes-agent`
  (so ours reports `second-arrow`); `/v1/capabilities` and `/health/detailed`
  don't expose it either. To display it truthfully, read
  `~/.hermes/profiles/second-arrow/config.yaml` → `model.default` locally.
- Custom OpenAI-compatible endpoints: `provider: custom` + `base_url`;
  `api_mode: chat_completions` (default) or `anthropic_messages`; env
  substitution via `key_env: ENV_VAR`. Ollama/vLLM/llama.cpp all work through
  their OpenAI-compatible endpoints.

## 4. MCP registration

[mcp](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)

- Config lives in the profile `config.yaml` under top-level `mcp_servers:`.
  Stdio transport: `command:` + `args:` (+ optional `env:`); HTTP: `url:` +
  `headers:` or `auth: oauth`.
- Official CLI: `hermes mcp add <name> [--command CMD] [--args ...] [--url URL]`
  ("--args passes the remaining argv to the stdio command, so put it last"),
  `hermes mcp list`, `hermes mcp test <name>`, `hermes mcp remove <name>`.
- Per-server tool filtering: `tools: {include: [...], exclude: [...],
  prompts: false, resources: false}` — "If both are present: `include` wins."
  `hermes mcp configure <name>` reopens an interactive checklist for the same
  thing.
- Each MCP server becomes a runtime toolset named `mcp-<server>`, tools named
  `mcp_<server>_<tool>`.
- `/reload-mcp` in a session reloads MCP servers from config and refreshes the
  tool list — no gateway restart needed for MCP changes.
- Desktop app has a Settings pane for MCP servers; granular per-tool toggling
  in the GUI is not documented — use `hermes mcp configure` or config.yaml.

## 5. Toolset restriction

[toolsets-reference](https://hermes-agent.nousresearch.com/docs/reference/toolsets-reference) ·
[configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)

- Per-platform pinning: top-level `platform_toolsets:` mapping platform key
  (`api_server`, `cli`, ...) to a toolset list. Use the derived
  `mcp-<server>` name, not the bare server name.
- Global kill list: `agent.disabled_toolsets` is applied AFTER per-platform
  config — a toolset listed there is removed everywhere. Put only core
  toolset names here, never platform-bundle names (`hermes-api-server` etc.).
- `hermes tools` is an interactive per-platform enable/disable UI
  (`--summary` prints state); there is no non-interactive flag syntax — edit
  config.yaml for scripted changes.
- Verify what a gateway actually exposes with `GET /v1/toolsets` (that is
  what `tools/hermes_probe.py` gates on).

## 6. API server (OpenAI-compatible gateway)

[api-server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)

- Enable via the profile `.env` **only** ("config.yaml support coming in a
  future release"): `API_SERVER_ENABLED=true`, `API_SERVER_KEY=<required —
  every deployment, including 127.0.0.1>`, `API_SERVER_PORT=8642`,
  `API_SERVER_HOST=127.0.0.1`, optional `API_SERVER_CORS_ORIGINS`,
  `API_SERVER_MODEL_NAME`. Start with `hermes gateway run|start` (per
  profile: `hermes -p <name> gateway ...`).
- Auth: `Authorization: Bearer <API_SERVER_KEY>` on every request.
- Endpoints:
  - `POST /v1/chat/completions` — OpenAI shape; SSE streaming with
    token deltas plus a custom `hermes.tool.progress` event.
  - `POST /v1/responses`, `GET|DELETE /v1/responses/{id}` — OpenAI Responses
    shape, stateful via `previous_response_id` or a named `conversation`
    param ("the server automatically chains to the latest response").
    Stored responses persist in SQLite but **max 100, LRU eviction**.
  - `/v1/runs` family — create run, poll, SSE events, stop, approvals.
  - `/api/sessions` family — full REST session control: list/create/fork,
    `POST /api/sessions/{id}/chat` and `/chat/stream`.
  - `/api/jobs` family — scheduled jobs.
  - Discovery: `GET /v1/models`, `/v1/capabilities`, `/v1/skills`,
    `/v1/toolsets`, `/health`, `/health/detailed`.
- Frontend `system` messages / `instructions` are layered ON TOP of the core
  system prompt (SOUL.md et al.), not replacing it.
- Concurrency: shared cap across chat/responses/runs,
  `gateway.api_server.max_concurrent_runs` in config.yaml (default 10,
  0 disables); over the cap → **HTTP 429** (verified in source). No
  per-session locking — callers should serialize turns within one thread.
- Uploaded files / non-image data: URLs → `400 unsupported_content_type`;
  inline images OK.

## 7. Sessions & continuity

[api-server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server) ·
source `gateway/platforms/api_server.py`

- **No header (stateless):** client sends full history each turn; the server
  derives a stable session id by hashing system prompt + first user message
  (so an Open WebUI-style conversation keeps mapping to one Hermes session).
  Server-side tool-call context between turns is not replayed from the body.
- **`X-Hermes-Session-Id` header:** server-owned continuity. Requires API-key
  auth (403 otherwise). When present, "history is loaded from state.db
  instead of from the request body" — send only the new user message. The id
  is echoed back in the response header and JSON. Max 256 chars, control
  chars and path-shaped ids rejected.
- **`X-Hermes-Session-Key` header:** stable per-channel identity for
  long-term memory (Honcho) independent of the transcript-scoped session id.
- **Responses API:** `previous_response_id` (explicit chain, keeps tool-call
  context) or `conversation: <name>` (auto-chain) — both bounded by the
  100-stored-responses LRU.
- **Sessions REST API:** external dashboards; fork + single-turn chat/stream.
- Desktop-app chats do NOT flow through the gateway (the app "runs its own
  `hermes serve` backend"); app sessions and API-server sessions are separate
  records inside the same profile state.

## 8. Persona: SOUL.md

[personality](https://hermes-agent.nousresearch.com/docs/user-guide/features/personality)

- `SOUL.md` occupies "slot #1 in the system prompt" — the agent's primary
  identity; per profile at `~/.hermes/profiles/<name>/SOUL.md`.
- Durable baseline (vs `/personality` temporary overlays, AGENTS.md
  project-scoped). Large files are truncated; keep it tight.

## 9. Security posture

[security](https://hermes-agent.nousresearch.com/docs/user-guide/security)

- "The API server gives full access to hermes-agent's toolset, **including
  terminal commands**" — toolset restriction (§5) is the boundary; our
  profile exposes only `mcp-second_arrow` + `clarify`.
- `API_SERVER_KEY` required even on loopback; default bind 127.0.0.1; CORS
  off by default.
- Dangerous-command approval modes: `manual` (default) / `smart` / `off`,
  plus an unconditional blocklist ("regardless of `--yolo`"). Container
  backends (docker/modal/daytona) isolate agent commands entirely.
- SSRF protection always on for web tools (private ranges blocked,
  fail-closed DNS). Context files scanned for prompt-injection patterns; MCP
  credential output redacted.
- Gateway messaging platforms: default-deny without allowlists.

## 10. Version-fragile notes (recheck on Hermes upgrades)

- API server config is env-only today; config.yaml support is announced.
- `X-Hermes-Session-Id` = "body history ignored, state.db wins" is verified
  in source, only loosely documented — keep `hermes_probe.py` asserting it.
- `/v1/responses` stored-response cap (100, LRU) makes long-lived
  `conversation` chains breakable; prefer session-id continuity.
- `platform_toolsets` key naming (`api_server` vs `hermes-api-server`)
  is inconsistent across doc pages; trust `GET /v1/toolsets` output.
- `/v1/models` advertises the profile name, not the LLM — any future
  endpoint exposing `model.default` would supersede our local-file read.
