# Hermes reference (distilled)

Standing knowledge base for the `second-arrow` Hermes profile. Grounded in
the **full local mirror** of the docs site at [docs/hermes/](hermes/INDEX.md)
(352 pages, mirrored 2026-07-02 from `NousResearch/hermes-agent@30e947e0`,
which is **Hermes Agent v0.18.0** / release v2026.7.1, 2026-07-01 — one
release ahead of the v0.17.0 app we first wired against), cross-checked
against the live site and the gateway source. Facts over prose; each section
cites its mirrored page. Builders: read this before re-fetching anything.

Changes vs the v0.17.0-era draft of this file are marked **[0.18]**.

## 1. Install & first run

[quickstart](hermes/getting-started/quickstart.md) ·
[providers](hermes/integrations/providers.md)

- `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` (or the desktop app).
- Setup: `hermes setup` (wizard), `hermes model` (provider walk-through), `hermes setup --portal`.
- **[0.18]** `hermes setup` now offers a **Blank Slate** mode: everything off
  except provider/model + file + terminal toolsets; it writes an explicit
  `platform_toolsets.cli` list plus `agent.disabled_toolsets` — the same
  keys our wire script writes, now an officially supported shape.
- Secrets live in `~/.hermes/.env`; settings in `~/.hermes/config.yaml`
  (per profile: under `~/.hermes/profiles/<name>/`).
- Models need a **minimum 64K-token context window** (rejected at startup);
  for Ollama set `OLLAMA_CONTEXT_LENGTH=64000` before startup.
- Diagnostics: `hermes doctor [--fix]`, `hermes status` (shows `Model: <provider>/<model>`).

## 2. Profile lifecycle

[profiles](hermes/user-guide/profiles.md) ·
[profile-commands](hermes/reference/profile-commands.md)

- Each profile is a full isolated agent under `~/.hermes/profiles/<name>/`:
  its own `config.yaml`, `.env`, `SOUL.md`, memories, sessions, skills,
  **cron jobs**, and state database. Isolation works via `HERMES_HOME`.
- `hermes profile create <name> [--clone|--clone-all|--clone-from <src>]
  [--description "..."] [--no-skills]`, `list`, `show`, `use <name>`
  (sticky default), `delete`, `rename`, `alias`, `export`/`import`,
  `describe`.
- `--clone` copies exactly: `config.yaml`, `.env`, `SOUL.md`, and skills
  (fresh sessions/memory). `--clone-all` copies everything except
  per-profile history (sessions, `state.db`, backups, snapshots,
  checkpoints).
- Every profile auto-gets a command alias at `~/.local/bin/<name>` —
  `second-arrow gateway restart` ≡ `hermes -p second-arrow gateway restart`.
  `-p` works with every subcommand, in any position.
- **A profile is NOT a sandbox.** The local terminal backend keeps full
  user-account filesystem access; tool cwd is `terminal.cwd`, not the
  profile dir. Our toolset restriction (§5) is the actual boundary.
- Each profile runs **its own gateway process** (`hermes -p <name> gateway
  run|start|stop|restart|status|install`; `gateway list` shows all
  profiles' gateways; `--all` acts on every profile). Distinct
  `API_SERVER_PORT` per profile `.env` for concurrent gateways.
- **[0.18]** Profiles can be shared as git-repo **distributions**
  (`hermes profile install <repo>` / `profile update`) — SOUL, config,
  skills, cron, MCP connections travel; credentials/memories/sessions stay
  per machine. (A future path for shipping the second-arrow persona.)

## 3. Model selection — who decides, who displays

[configuring-models](hermes/user-guide/configuring-models.md) ·
[desktop](hermes/user-guide/desktop.md) ·
[api-server](hermes/user-guide/features/api-server.md)

- Per-profile default in the profile `config.yaml`:
  `model: {default: ..., provider: ..., base_url: ..., api_mode: ...}`
  (a fresh install has `model: ""` until first setup upgrades it to the
  mapping). Set it via:
  - `hermes -p second-arrow config set model.default <model>` (+
    `model.provider`) — scalar-only writes;
  - `hermes -p second-arrow model` — interactive picker, "the canonical way
    to switch defaults";
  - dashboard **Models** page (writes the same keys);
  - `/model <model> --provider <p> --global` in chat (persists AND switches
    the running session in place; without `--global` it's session-only).
- **[0.18]** `model_aliases:` (top-level, full mapping) or
  `hermes config set model.aliases.<name> provider/model` (scalar form)
  define custom `/model <alias>` shortcuts; `model_aliases` wins on clash.
- **[0.18]** 11 **auxiliary model slots** (`auxiliary.<task>` —
  compression, vision, title_generation, approval, web extract, ...) default
  to `provider: auto` = use the main model; each can be pinned to a cheaper
  model independently. Compression's model must have a context window ≥ the
  main model's.
- The desktop **composer model picker** is sticky per-device UI state and
  never touches the profile default; only the Models settings page does.
- Taking effect: a changed default applies to the **next new session**;
  existing sessions keep theirs; `hermes gateway restart` forces all
  sessions to pick it up. **[0.18]** `model.context_length` and any
  `compression.*` key now hot-reload on a running gateway (next message);
  model/API-key/tool config still needs restart or the usual reload paths.
  Per-session `/model` overrides now persist across gateway restarts
  (landed at our mirror commit, post-v2026.7.1).
- **Per-request `model` on the API server — corrected [0.18]:** by default
  still cosmetic ("accepted but the actual LLM model used is configured
  server-side"), **but** the gateway now supports a `model_routes` block
  (source-verified `gateway/platforms/api_server.py`; NOT yet on the docs
  page): map an alias the client sends as `model` to
  `{model, provider, api_key?, base_url?}` under the api_server platform's
  `extra` config, and requests naming that alias route to that backend.
  Precedence per request: session `/model` override → matched
  `model_routes` alias → profile default. Unknown values still fall through
  silently to the default.
- `GET /v1/models` advertises `API_SERVER_MODEL_NAME` > active profile name
  (ours: `second-arrow`) > `hermes-agent`, **[0.18]** plus one entry per
  `model_routes` alias (`root` = resolved model name — the one place the
  API leaks a real model name). Without routes, the actual LLM is still not
  readable over the API: to display it truthfully, read the profile
  `config.yaml` → `model.default` locally.
- Custom OpenAI-compatible endpoints: `provider: custom` + `base_url`;
  `api_mode: chat_completions` (default) or `anthropic_messages`; `${VAR}`
  substitution from the profile `.env`. Ollama/vLLM/llama.cpp work this way.

## 4. MCP registration

[mcp](hermes/user-guide/features/mcp.md) ·
[mcp-config-reference](hermes/reference/mcp-config-reference.md)

- Config: profile `config.yaml`, top-level `mcp_servers:`. Stdio:
  `command:` + `args:` (+ `env:` — only explicit env + a safe baseline are
  passed to the subprocess); HTTP: `url:` + `headers:` or `auth: oauth`.
  Other keys: `enabled: false` (skip server entirely), `timeout`,
  `connect_timeout`, `supports_parallel_tool_calls` (opt-in concurrency),
  `client_cert`/`client_key` (mTLS).
- CLI: `hermes mcp add <name> [--command CMD] [--args ...] [--url URL]`
  (`--args` swallows the rest of argv — put it last), `list`,
  `test <name>`, `configure <name>` (re-open the include checklist),
  `remove <name>`, `login <name>` (OAuth). **[0.18]** also a curated
  catalog: `hermes mcp` / `mcp catalog` / `mcp install <entry>`.
- Per-server filtering: `tools: {include: [...], exclude: [...],
  prompts: false, resources: false}`; **include wins** when both present.
  Utility wrappers (`list_resources`, `get_prompt`, ...) only register when
  the server actually supports the capability AND config allows it.
- Naming: toolset `mcp-<server>` (created only if ≥1 tool registers),
  tools `mcp_<server>_<tool>`.
- Reload: `/reload-mcp` in a session re-reads config — no gateway restart
  for MCP changes. **[0.18]** servers can also push
  `notifications/tools/list_changed` and Hermes re-fetches automatically.
  Editing config.yaml under a running CLI session auto-reloads MCP with a
  30s timeout (too short for OAuth — use `hermes mcp login` separately).
- **[0.18] Sampling:** MCP servers may request LLM inference from Hermes
  (`sampling/createMessage`) — **enabled by default**, rate-limited
  (10 rpm, 4096 tokens, 5 tool rounds). Our server never uses it; for
  least-privilege set `mcp_servers.second_arrow.sampling.enabled: false`.

## 5. Toolset restriction

[toolsets-reference](hermes/reference/toolsets-reference.md) ·
[configuration](hermes/user-guide/configuration.md)

- **Ambiguity resolved (source-verified, `hermes_cli/toolset_validation.py`):**
  `platform_toolsets:` keys are **short platform names** (`cli`,
  `api_server`, `cron`, `telegram`, ...); the **values** are toolset names —
  platform bundles (`hermes-cli`, `hermes-api-server`), core sets
  (`clarify`, `file`), or derived `mcp-<server>` names. Our snippet
  (`api_server: [mcp-second_arrow, clarify]`) is the right shape.
- **[0.18]** Invalid toolset names in `platform_toolsets` now produce loud
  startup warnings (including "resolves to zero valid toolsets — the agent
  will have no tools") instead of silent tool loss (the old #38798 trap).
- Global kill list: `agent.disabled_toolsets` applies AFTER per-platform
  config — listed toolsets are removed everywhere. Core toolset names only;
  never platform-bundle names.
- `hermes tools` = interactive per-platform UI (also covers the **cron**
  platform); `hermes tools --summary` prints state; no non-interactive set
  syntax — edit config.yaml for scripted changes.
- Default bundle for the gateway is `hermes-api-server` = `hermes-cli`
  minus `clarify` + `text_to_speech` — i.e. terminal/file/web/browser and
  everything else. Our pinning is what removes all that.
- Verify what a gateway actually exposes with `GET /v1/toolsets`
  (`tools/hermes_probe.py` gates on it); it returns toolsets resolved for
  the `api_server` platform with each one's concrete `tools` list.

## 6. API server (OpenAI-compatible gateway)

[api-server](hermes/user-guide/features/api-server.md)

- Enable via the profile `.env`: `API_SERVER_ENABLED=true`,
  `API_SERVER_KEY=<required — every deployment, incl. 127.0.0.1>`,
  `API_SERVER_PORT=8642`, `API_SERVER_HOST=127.0.0.1`, optional
  `API_SERVER_CORS_ORIGINS`, `API_SERVER_MODEL_NAME`. Docs still say
  "config.yaml support coming"; in source the gateway also merges a
  `platforms:`/`gateway.platforms:` → `api_server:` block (that's where
  `extra.model_routes` lives), with env vars overriding — treat config-yaml
  enablement as undocumented; keep using `.env`.
- Start: `hermes -p <name> gateway run` (foreground) or `start`
  (service); restart with `hermes -p <name> gateway restart` (or the
  profile alias / `--all`).
- Auth: `Authorization: Bearer <API_SERVER_KEY>` on every request.
- Endpoints:
  - `POST /v1/chat/completions` — OpenAI shape. SSE streaming = standard
    `chat.completion.chunk` deltas plus custom `event: hermes.tool.progress`
    events (tool-start UX). Inline images ok (http(s) or `data:image/...`);
    uploaded files / non-image data → `400 unsupported_content_type`.
  - `POST /v1/responses`, `GET|DELETE /v1/responses/{id}` — Responses
    shape; stateful via `previous_response_id` or named `conversation`
    (auto-chains to latest). Streaming uses spec-native events
    (`response.output_text.delta`, `function_call` items, ...). Stored
    responses persist in SQLite, **max 100, LRU eviction**.
  - `/v1/runs` family — `POST /v1/runs`, `GET /v1/runs/{id}`,
    `GET /v1/runs/{id}/events` (SSE), `POST .../stop`, **[0.18]**
    `POST .../approval` (resolve a human-approval gate, scoped by run id).
  - `/api/sessions` family — REST session control: list/create/read/
    PATCH/delete, `/{id}/messages`, `/{id}/fork`, `POST /{id}/chat`
    (one synchronous turn), `POST /{id}/chat/stream` (SSE:
    `assistant.delta`, `tool.started`, `tool.completed`, `run.completed`).
  - `/api/jobs` family — cron over REST (§7): GET/POST `/api/jobs`,
    GET/PATCH/DELETE `/api/jobs/{id}`, POST `.../pause|resume|run`.
  - Discovery: `GET /v1/models`, `/v1/capabilities` (feature flags incl.
    `session_*`, `run_approval`, `session_key_header`), `/v1/skills`,
    `/v1/toolsets`, `/health` (alias **[0.18]** `/v1/health`),
    `/health/detailed`.
- Frontend `system` messages / `instructions` are layered ON TOP of the
  core system prompt (SOUL.md et al.), never replacing it.
- Concurrency: shared cap across chat/responses/runs —
  `gateway.api_server.max_concurrent_runs` in config.yaml (default 10,
  0 disables, negative → 0, non-int → 10; verified in tests). Over the cap
  → **HTTP 429**. No per-session locking — serialize turns per thread
  client-side.
- **[0.18]** CORS preflights cached 10 min; `Idempotency-Key` request
  header supported (responses deduplicated by key for 5 minutes).
- Proxy mode: another gateway with `GATEWAY_PROXY_URL` pointed here
  forwards all messages to this agent (split deployments).

## 7. Cron / scheduled jobs — the nightly-prep home

[cron](hermes/user-guide/features/cron.md) ·
[automate-with-cron](hermes/guides/automate-with-cron.md) ·
[cron-troubleshooting](hermes/guides/cron-troubleshooting.md)

- **Execution is the gateway daemon's job**: it ticks the scheduler every
  60s, loads `~/.hermes/<profile>/cron/jobs.json`, runs due jobs in fresh
  isolated agent sessions, delivers the final response. Our profile's
  gateway (the same process serving the API) must be running; CLI warns on
  create/list when it isn't. Jobs are per profile (HERMES_HOME).
- Create: `hermes -p second-arrow cron create "<schedule>" "<prompt>"
  [--name N] [--skill S ...] [--workdir DIR] [--deliver T] [--no-agent
  --script F]`; or the agent-facing `cronjob` tool (actions
  create/list/update/pause/resume/run/remove); or REST `/api/jobs` (same
  body shape as `hermes cron`). Also `/cron ...` in chat. `pause`,
  `resume`, `run`, `remove`, `edit`, `status`, `tick`; job reference =
  hex id or case-insensitive name (ambiguous names refused).
- Schedules: relative one-shot (`30m`), intervals (`every 2h`,
  `every 1d at 09:00`), 5-field cron (`0 4 * * *`), ISO timestamps;
  `repeat=` overrides.
- **Provider pinning — the integration gotcha [0.18]:** an unpinned job
  snapshots the global provider+model at creation and **fails closed** if
  the global default later changes (skips the run, alerts, no inference
  call) — so a nightly job must be re-pinned (`cronjob action=update
  job_id=... provider=... model=...`) after any model switch, or created
  with explicit `provider`/`model` from the start. Pin ours explicitly.
  Cron `base_url` overrides are blocked (credential-exfil hardening).
- Toolsets: per-job `enabled_toolsets=[...]` wins; else the `cron`
  platform row in `hermes tools` (or `platform_toolsets.cron`); else
  defaults (`hermes-cron` = full `hermes-cli`!). **[0.18]** enabled MCP
  servers are layered onto per-job toolsets — so a job with
  `enabled_toolsets=["mcp-second_arrow"]` gets exactly our tools. Pin
  `platform_toolsets.cron` like `api_server`. Cron sessions cannot create
  more cron jobs (recursion guard).
- `workdir=` runs the job inside a directory (context files injected,
  file/terminal tools anchored there; such jobs run serialized). Not
  needed for us — our MCP tools carry their own paths.
- Delivery: `deliver` = `origin` | `local` (default on CLI-created jobs:
  files under `~/.hermes/<profile>/cron/output/<job_id>/<ts>.md`) |
  platform targets | `all` | comma lists. Output wrapped with a
  "Cronjob Response" header unless `cron.wrap_response: false`. A final
  response containing `[SILENT]` suppresses delivery (still saved
  locally); failures always deliver.
- `script=` pre-run gate (must live in `~/.hermes/scripts/`; timeout
  `cron.script_timeout_seconds`, default 3600): last stdout line
  `{"wakeAgent": false}` skips the agent for that tick — $0 change
  detection. `no_agent=True` = script-only job, stdout delivered verbatim,
  zero LLM. `context_from=<job|[jobs]>` prepends other jobs' most recent
  output (pipelines).
- Job prompts are scanned for prompt-injection/exfil patterns at
  create/update. Prompts must be self-contained — fresh session, no chat
  history.

## 8. Sessions & continuity

[api-server](hermes/user-guide/features/api-server.md) ·
[open-webui](hermes/user-guide/messaging/open-webui.md) ·
source `gateway/platforms/api_server.py`

- **No header (stateless):** client sends full history each turn; server
  derives a stable session id by hashing system prompt + first user
  message. Server-side tool-call context between turns is not replayed
  from the body.
- **`X-Hermes-Session-Id` header:** server-owned continuity. Requires
  API-key auth (403 otherwise). When present, history is loaded from
  state.db and body history is ignored — send only the new user message;
  tool-call context survives across turns. Echoed back in response header
  and JSON. Max 256 chars; control chars and path-shaped ids rejected.
  Works on `/v1/chat/completions`, `/v1/responses`, `/v1/runs`.
- **`X-Hermes-Session-Key` header:** stable per-channel identity for
  long-term memory (Honcho) — independent of the transcript-scoped session
  id (which rotates on `/new`). Same 256-char/control-char rules; echoed
  back; advertised in `/v1/capabilities` as `session_key_header`.
- **Responses API:** `previous_response_id` or `conversation: <name>` —
  both bounded by the 100-stored-responses LRU; prefer session-id
  continuity for long threads.
- Desktop-app chats do NOT flow through the gateway (the app runs its own
  backend); app sessions and API-server sessions are separate records in
  the same profile state.

## 9. Persona: SOUL.md

[personality](hermes/user-guide/features/personality.md)

- `SOUL.md` = slot #1 in the system prompt, replacing the default identity;
  no wrapper text added. Per profile at `~/.hermes/profiles/<name>/SOUL.md`.
- Durable baseline (vs `/personality` session overlays, AGENTS.md
  project-scoped). Context files are truncated at
  `context_file_max_chars` (default 20000) — keep it tight.
- Changes take effect on new sessions; existing sessions keep the old
  prompt state.

## 10. Security posture

[security](hermes/user-guide/security.md)

- "The API server gives full access to hermes-agent's toolset, **including
  terminal commands**" — toolset restriction (§5) is the boundary; our
  profile exposes only `mcp-second_arrow` + `clarify` (and the same pin
  should cover the `cron` platform, §7).
- `API_SERVER_KEY` required even on loopback; default bind 127.0.0.1;
  CORS off by default.
- Dangerous-command approval modes `manual`/`smart`/`off` + unconditional
  blocklist; container backends isolate agent commands entirely. (Moot for
  us with `terminal` disabled.)
- SSRF protection always on for web tools; context files scanned for
  prompt-injection; MCP credential output redacted; **[0.18]** cron
  prompts scanned too, cron `base_url` exfil blocked, MCP-config
  persistence attack surface hardened.
- Gateway messaging platforms: default-deny without allowlists.

## 11. Version-fragile notes (recheck on Hermes upgrades)

- `model_routes` and config-yaml platform blocks for the api_server are
  **source-verified but undocumented** — shapes may shift; the docs page
  still says env-only + cosmetic `model` field.
- `X-Hermes-Session-Id` = "body history ignored, state.db wins" is
  verified in source, loosely documented — keep `hermes_probe.py`
  asserting it.
- `/v1/responses` stored-response cap (100, LRU) breaks long `conversation`
  chains; prefer session-id continuity.
- Cron fail-closed provider snapshot means every `hermes model` /
  `config set model.*` change **strands unpinned cron jobs** — after a
  model switch, re-pin or update the nightly job.
- MCP sampling default-on: re-add `sampling.enabled: false` if we ever
  regenerate the profile config.
- `/v1/models` advertises the profile name (plus route aliases), not
  `model.default` — the local-file read in the shelf stays authoritative.
- Local mirror provenance: `docs/hermes/` = site @ v0.18.0
  (`30e947e0`, fetched 2026-07-02). Re-mirror on the next Hermes update:
  shallow-clone the repo, run the mirror over `website/docs/`.
