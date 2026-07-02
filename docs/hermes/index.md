<!-- source: https://hermes-agent.nousresearch.com/docs | fetched: 2026-07-02 | mirror of NousResearch/hermes-agent@30e947e0 website/docs -->

# Hermes Agent docs — local mirror index

Full mirror of the hermes-agent documentation site
(<https://hermes-agent.nousresearch.com/docs>), taken from the docs source in
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
`website/docs/` at commit `30e947e0` (Hermes Agent **v0.18.0** / release
v2026.7.1, 2026-07-01). 352 pages plus the v0.18.0 release notes
(`release-notes/v0.18.0.md`). One line per page; the distilled operational
reference for our integration lives in [`../hermes-reference.md`](../hermes-reference.md).

## (root)

- [Hermes Agent Documentation](index.md) — The self-improving AI agent built by Nous Research. A built-in learning loop that creates skills from experience, improves them during use, and remembers across sessions.
- [User Stories & Use Cases](user-stories.md) — Real stories from the Hermes Agent community — what people are actually building, scraped from X, GitHub, Reddit, Hacker News, YouTube, blogs, and podcasts.

## developer-guide

- [ACP Internals](developer-guide/acp-internals.md) — How the ACP adapter works: lifecycle, sessions, event bridge, approvals, and tool rendering
- [Adding a Platform Adapter](developer-guide/adding-platform-adapters.md) — This guide covers adding a new messaging platform to the Hermes gateway. A platform adapter connects Hermes to an external messaging service (Telegram, Discord,…
- [Adding Providers](developer-guide/adding-providers.md) — How to add a new inference provider to Hermes Agent — auth, runtime resolution, CLI flows, adapters, tests, and docs
- [Adding Tools](developer-guide/adding-tools.md) — How to add a new tool to Hermes Agent — schemas, handlers, registration, and toolsets
- [Agent Loop Internals](developer-guide/agent-loop.md) — Detailed walkthrough of AIAgent execution, API modes, tools, callbacks, and fallback behavior
- [Architecture](developer-guide/architecture.md) — Hermes Agent internals — major subsystems, execution paths, data flow, and where to read next
- [Browser CDP Supervisor](developer-guide/browser-supervisor.md) — How Hermes detects and responds to native JS dialogs and interacts with cross-origin iframes via a persistent CDP connection.
- [Context Compression and Caching](developer-guide/context-compression-and-caching.md) — Hermes Agent uses a dual compression system and Anthropic prompt caching to
- [Context Engine Plugins](developer-guide/context-engine-plugin.md) — How to build a context engine plugin that replaces the built-in ContextCompressor
- [Contributing](developer-guide/contributing.md) — How to contribute to Hermes Agent — dev setup, code style, PR process
- [Creating Skills](developer-guide/creating-skills.md) — How to create skills for Hermes Agent — SKILL.md format, guidelines, and publishing
- [Cron Internals](developer-guide/cron-internals.md) — How Hermes stores, schedules, edits, pauses, skill-loads, and delivers cron jobs
- [Extending the CLI](developer-guide/extending-the-cli.md) — Build wrapper CLIs that extend the Hermes TUI with custom widgets, keybindings, and layout changes
- [Gateway Internals](developer-guide/gateway-internals.md) — How the messaging gateway boots, authorizes users, routes sessions, and delivers messages
- [Image Generation Provider Plugins](developer-guide/image-gen-provider-plugin.md) — How to build an image-generation backend plugin for Hermes Agent
- [Memory Provider Plugins](developer-guide/memory-provider-plugin.md) — How to build a memory provider plugin for Hermes Agent
- [Model Provider Plugins](developer-guide/model-provider-plugin.md) — How to build a model provider (inference backend) plugin for Hermes Agent
- [Plugin LLM Access](developer-guide/plugin-llm-access.md) — Run any LLM call from inside a plugin via ctx.llm — chat or structured, sync or async. Host-owned auth, fail-closed trust gate, optional JSON Schema validation.
- [Programmatic Integration](developer-guide/programmatic-integration.md) — Three protocols for driving hermes-agent from external programs: ACP, the TUI gateway JSON-RPC, and the OpenAI-compatible HTTP API
- [Prompt Assembly](developer-guide/prompt-assembly.md) — How Hermes builds the system prompt, preserves cache stability, and injects ephemeral layers
- [Provider Runtime Resolution](developer-guide/provider-runtime.md) — How Hermes resolves providers, credentials, API modes, and auxiliary models at runtime
- [Session Storage](developer-guide/session-storage.md) — Hermes Agent uses a SQLite database (~/.hermes/state.db) to persist session
- [Tools Runtime](developer-guide/tools-runtime.md) — Runtime behavior of the tool registry, toolsets, dispatch, and terminal environments
- [Trajectory Format](developer-guide/trajectory-format.md) — Hermes Agent saves conversation trajectories in ShareGPT-compatible JSONL format
- [Video Generation Provider Plugins](developer-guide/video-gen-provider-plugin.md) — How to build a video-generation backend plugin for Hermes Agent
- [Web Search Provider Plugins](developer-guide/web-search-provider-plugin.md) — How to build a web-search/extract/crawl backend plugin for Hermes Agent

## getting-started

- [Installation](getting-started/installation.md) — Install Hermes Agent on Linux, macOS, WSL2, native Windows, or Android via Termux
- [Learning Path](getting-started/learning-path.md) — Choose your learning path through the Hermes Agent documentation based on your experience level and goals.
- [Nix & NixOS Setup](getting-started/nix-setup.md) — Install and deploy Hermes Agent with Nix — from quick `nix run` to fully declarative NixOS module with container mode
- [Platform Support](getting-started/platform-support.md) — Which operating systems, distribution methods, and features Hermes Agent supports.
- [Quickstart](getting-started/quickstart.md) — Your first conversation with Hermes Agent — from install to chatting in under 5 minutes
- [Android / Termux](getting-started/termux.md) — Run Hermes Agent directly on an Android phone with Termux
- [Updating & Uninstalling](getting-started/updating.md) — How to update Hermes Agent to the latest version or uninstall it

## guides

- [Automate Anything with Cron](guides/automate-with-cron.md) — Real-world automation patterns using Hermes cron — monitoring, reports, pipelines, and multi-skill workflows
- [Automation Blueprints](guides/automation-blueprints.md) — Ready-to-use automation blueprints — scheduled tasks, GitHub event triggers, API webhooks, and multi-skill workflows
- [AWS Bedrock](guides/aws-bedrock.md) — Use Hermes Agent with Amazon Bedrock — native Converse API, IAM authentication, Guardrails, and cross-region inference
- [Microsoft Foundry](guides/azure-foundry.md) — Use Hermes Agent with Microsoft Foundry — OpenAI-style and Anthropic-style endpoints, auto-detection of transport and deployed models
- [Build a Hermes Plugin](guides/build-a-hermes-plugin.md) — Step-by-step guide to building a complete Hermes plugin with tools, hooks, data files, and skills
- [Script-Only Cron Jobs (No LLM)](guides/cron-script-only.md) — Classic watchdog cron jobs that skip the LLM entirely — a script runs on schedule and its stdout gets delivered to your messaging platform. Memory alerts, disk alerts, CI pings, periodic health checks.
- [Cron Troubleshooting](guides/cron-troubleshooting.md) — Diagnose and fix common Hermes cron issues — jobs not firing, delivery failures, skill loading errors, and performance problems
- [Tutorial: Daily Briefing Bot](guides/daily-briefing-bot.md) — Build an automated daily briefing bot that researches topics, summarizes findings, and delivers them to Telegram or Discord every morning
- [Delegation & Parallel Work](guides/delegation-patterns.md) — When and how to use subagent delegation — patterns for parallel research, code review, and multi-file work
- [Tutorial: GitHub PR Review Agent](guides/github-pr-review-agent.md) — Build an automated AI code reviewer that monitors your repos, reviews pull requests, and delivers feedback — hands-free
- [Google Gemini](guides/google-gemini.md) — Use Hermes Agent with Google Gemini — native AI Studio API, API-key setup, tool calling, streaming, and quota guidance
- [Google Vertex AI](guides/google-vertex.md) — Use Hermes Agent with Gemini on Google Cloud Vertex AI — OAuth2 service account or ADC, GCP billing and quotas, no static API key
- [Run Local LLMs on Mac](guides/local-llm-on-mac.md) — Set up a local OpenAI-compatible LLM server on macOS with llama.cpp or MLX, including model selection, memory optimization, and real benchmarks on Apple Silicon
- [Run Hermes Locally with Ollama — Zero API Cost](guides/local-ollama-setup.md) — Step-by-step guide to running Hermes Agent entirely on your own machine with Ollama and open-weight models like Gemma 4, no cloud API keys or paid subscriptions needed
- [Register a Microsoft Graph Application](guides/microsoft-graph-app-registration.md) — Azure portal walkthrough for creating the app registration that powers the Teams meeting pipeline
- [Migrate from OpenClaw](guides/migrate-from-openclaw.md) — Complete guide to migrating your OpenClaw / Clawdbot setup to Hermes Agent — what gets migrated, how config maps, and what to check after.
- [MiniMax OAuth](guides/minimax-oauth.md) — Log into MiniMax via browser OAuth and use MiniMax-M2.7 models in Hermes Agent — no API key required
- [OAuth over SSH / Remote Hosts](guides/oauth-over-ssh.md) — How to complete browser-based OAuth (xAI, Spotify, MCP servers) when Hermes runs on a remote machine, container, or behind a jump box
- [Operate the Teams Meeting Pipeline](guides/operate-teams-meeting-pipeline.md) — Runbook, go-live checklist, and operator worksheet for the Microsoft Teams meeting pipeline
- [Pipe Script Output to Messaging Platforms](guides/pipe-script-output.md) — Send text from any shell script, cron job, CI hook, or monitoring daemon to Telegram, Discord, Slack, Signal, and other platforms using `hermes send`.
- [Using Hermes as a Python Library](guides/python-library.md) — Embed AIAgent in your own Python scripts, web apps, or automation pipelines — no CLI required
- [Run Hermes Agent with Nous Portal](guides/run-hermes-with-nous-portal.md) — Start-to-finish walkthrough: subscribe, set up, switch models, enable gateway tools, and verify routing
- [Run Nemotron 3 Ultra free in Hermes Agent](guides/run-nemotron-3-ultra-free.md) — Try NVIDIA Nemotron 3 Ultra on Nous Portal — free June 4–18 — with day 0 support in Hermes Agent
- [Tutorial: Team Telegram Assistant](guides/team-telegram-assistant.md) — Step-by-step guide to setting up a Telegram bot that your whole team can use for code help, research, system admin, and more
- [Tips & Best Practices](guides/tips.md) — Practical advice to get the most out of Hermes Agent — prompt tips, CLI shortcuts, context files, memory, cost optimization, and security
- [Use MCP with Hermes](guides/use-mcp-with-hermes.md) — A practical guide to connecting MCP servers to Hermes Agent, filtering their tools, and using them safely in real workflows
- [Use SOUL.md with Hermes](guides/use-soul-with-hermes.md) — How to use SOUL.md to shape Hermes Agent's default voice, what belongs there, and how it differs from AGENTS.md and /personality
- [Use Voice Mode with Hermes](guides/use-voice-mode-with-hermes.md) — A practical guide to setting up and using Hermes voice mode across CLI, Telegram, Discord, and Discord voice channels
- [Automated GitHub PR Comments with Webhooks](guides/webhook-github-pr-review.md) — Connect Hermes to GitHub so it automatically fetches PR diffs, reviews code changes, and posts comments — triggered by webhooks with no manual prompting
- [Working with Skills](guides/work-with-skills.md) — Find, install, use, and create skills — on-demand knowledge that teaches Hermes new workflows
- [xAI Grok OAuth (SuperGrok / X Premium+)](guides/xai-grok-oauth.md) — Sign in with your SuperGrok or X Premium+ subscription to use Grok models in Hermes Agent — no API key required

## integrations

- [Integrations](integrations/index.md) — Hermes Agent connects to external systems for AI inference, tool servers, IDE workflows, programmatic access, and more. These integrations extend what Hermes ca…
- [Nous Portal](integrations/nous-portal.md) — One subscription, 300+ frontier models, the Tool Gateway, and Nous Chat — the recommended way to run Hermes Agent
- [AI Providers](integrations/providers.md) — This page covers setting up inference providers for Hermes Agent — from cloud APIs like OpenRouter and Anthropic, to self-hosted endpoints like Ollama and vLLM,…

## reference

- [Automation Blueprints Catalog](reference/automation-blueprints-catalog.md) — Ready-to-run automation blueprints — set one up from the dashboard, CLI, TUI, any messenger, or the desktop app.
- [CLI Commands Reference](reference/cli-commands.md) — Authoritative reference for Hermes terminal commands and command families
- [Environment Variables](reference/environment-variables.md) — Complete reference of all environment variables used by Hermes Agent
- [FAQ & Troubleshooting](reference/faq.md) — Frequently asked questions and solutions to common issues with Hermes Agent
- [MCP Config Reference](reference/mcp-config-reference.md) — Reference for Hermes Agent MCP configuration keys, filtering semantics, and utility-tool policy
- [Model Catalog](reference/model-catalog.md) — Remotely-hosted manifest driving curated model picker lists for OpenRouter and Nous Portal.
- [Optional Skills Catalog](reference/optional-skills-catalog.md) — Official optional skills shipped with hermes-agent — install via hermes skills install official/<category>/<skill>
- [Profile Commands Reference](reference/profile-commands.md) — This page covers all commands related to Hermes profiles. For general CLI commands, see CLI Commands Reference.
- [Bundled Skills Catalog](reference/skills-catalog.md) — Catalog of bundled skills that ship with Hermes Agent
- [Slash Commands Reference](reference/slash-commands.md) — Complete reference for interactive CLI and messaging slash commands
- [Built-in Tools Reference](reference/tools-reference.md) — Authoritative reference for Hermes built-in tools, grouped by toolset
- [Toolsets Reference](reference/toolsets-reference.md) — Reference for Hermes core, composite, platform, and dynamic toolsets

## user-guide

- [Checkpoints and /rollback](user-guide/checkpoints-and-rollback.md) — Filesystem safety nets for destructive operations using shadow git repos and automatic snapshots
- [CLI Interface](user-guide/cli.md) — Master the Hermes Agent terminal interface — commands, keybindings, personalities, and more
- [Configuration](user-guide/configuration.md) — Configure Hermes Agent — config.yaml, providers, models, API keys, and more
- [Configuring Models](user-guide/configuring-models.md) — Hermes uses two kinds of model slots:
- [Desktop App](user-guide/desktop.md) — The native Hermes desktop app — a polished experience for chatting with Hermes, with streaming tool output, side-by-side previews, a file browser, voice, cron, profiles, skills, and settings. macOS, Windows, and Linux.
- [Docker](user-guide/docker.md) — Running Hermes Agent in Docker and using Docker as a terminal backend
- [Git Worktrees](user-guide/git-worktrees.md) — Run multiple Hermes agents safely on the same repository using git worktrees and isolated checkouts
- [Managed Scope](user-guide/managed-scope.md) — Administrator-pinned, user-immutable config and secrets via a system-level managed directory
- [Running Many Gateways at Once](user-guide/multi-profile-gateways.md) — Operate multiple profiles — each with its own bot tokens,
- [Profile Distributions: Share a Whole Agent](user-guide/profile-distributions.md) — A profile distribution packages a complete Hermes agent — personality, skills, cron jobs, MCP connections, config — as a git repository. Anyone with access to t…
- [Profiles: Running Multiple Agents](user-guide/profiles.md) — Run multiple independent Hermes agents on the same machine — each with its own config, API keys, memory, sessions, skills, and gateway state.
- [Security](user-guide/security.md) — Security model, dangerous command approval, user authorization, container isolation, and production deployment best practices
- [Sessions](user-guide/sessions.md) — Session persistence, resume, search, management, and per-platform session tracking
- [TUI](user-guide/tui.md) — Launch the modern terminal UI for Hermes — mouse-friendly, rich overlays, and non-blocking input.
- [Windows (Native) Guide](user-guide/windows-native.md) — Run Hermes Agent natively on Windows 10 / 11 — install, feature matrix, UTF-8 console, Git Bash, gateway as a Scheduled Task, editor handling, PATH, uninstall, and common pitfalls
- [Windows (WSL2) Guide](user-guide/windows-wsl-quickstart.md) — Run Hermes Agent on Windows via WSL2 — setup, filesystem access between Windows and Linux, networking, and common pitfalls

## user-guide/features

- [ACP Editor Integration](user-guide/features/acp.md) — Use Hermes Agent inside ACP-compatible editors such as VS Code, Zed, and JetBrains
- [API Server](user-guide/features/api-server.md) — Expose hermes-agent as an OpenAI-compatible API for any frontend
- [Batch Processing](user-guide/features/batch-processing.md) — Generate agent trajectories at scale — parallel processing, checkpointing, and toolset distributions
- [Browser Automation](user-guide/features/browser.md) — Control browsers with multiple providers, local Chromium-family browsers via CDP, or cloud browsers for web interaction, form filling, scraping, and more.
- [Built-in Plugins](user-guide/features/built-in-plugins.md) — Plugins shipped with Hermes Agent that run automatically via lifecycle hooks — disk-cleanup and friends
- [Code Execution](user-guide/features/code-execution.md) — Programmatic Python execution with RPC tool access — collapse multi-step workflows into a single turn
- [Codex App-Server Runtime (optional)](user-guide/features/codex-app-server-runtime.md) — Hermes can optionally hand openai/ and openai-codex/ turns to the Codex CLI app-server instead of running its own tool loop. When enabled, terminal commands, fi…
- [Computer Use](user-guide/features/computer-use.md) — Hermes Agent can drive your desktop — clicking, typing, scrolling,
- [Context Files](user-guide/features/context-files.md) — Project context files — .hermes.md, AGENTS.md, CLAUDE.md, global SOUL.md, and .cursorrules — automatically injected into every conversation
- [Context References](user-guide/features/context-references.md) — Inline @-syntax for attaching files, folders, git diffs, and URLs directly into your messages
- [Credential Pools](user-guide/features/credential-pools.md) — Pool multiple API keys or OAuth tokens per provider for automatic rotation and rate limit recovery.
- [Scheduled Tasks (Cron)](user-guide/features/cron.md) — Schedule automated tasks with natural language, manage them with one cron tool, and attach one or more skills
- [Curator](user-guide/features/curator.md) — Background maintenance for agent-created skills — usage tracking, staleness, archival, and LLM-driven review
- [Subagent Delegation](user-guide/features/delegation.md) — Spawn isolated child agents for parallel workstreams with delegate_task
- [Deliverable Mode (Artifacts in Chat)](user-guide/features/deliverable-mode.md) — How the agent ships generated charts, PDFs, spreadsheets, and other files as native attachments in messaging platforms.
- [Extending the Dashboard](user-guide/features/extending-the-dashboard.md) — Build themes and plugins for the Hermes web dashboard — palettes, typography, layouts, custom tabs, shell slots, page-scoped slots, and backend API routes
- [Fallback Providers](user-guide/features/fallback-providers.md) — Configure automatic failover to backup LLM providers when your primary model is unavailable.
- [Persistent Goals](user-guide/features/goals.md) — Set a standing goal and let Hermes keep working across turns until it's done. Our take on the Ralph loop.
- [Honcho Memory](user-guide/features/honcho.md) — AI-native persistent memory via Honcho — dialectic reasoning, multi-agent user modeling, and deep personalization
- [Event Hooks](user-guide/features/hooks.md) — Run custom code at key lifecycle points — log activity, send alerts, post to webhooks
- [Image Generation](user-guide/features/image-generation.md) — Generate images via FAL.ai — 11 models including FLUX 2, GPT Image (1.5 & 2), Nano Banana Pro, Ideogram, Recraft V4 Pro, Krea 2, and more, selectable via `hermes tools`.
- [Kanban tutorial](user-guide/features/kanban-tutorial.md) — A walkthrough of the four use-cases the Hermes Kanban system was designed for, with the dashboard open in a browser. If you haven't read the Kanban overview yet…
- [Kanban worker lanes](user-guide/features/kanban-worker-lanes.md) — A worker lane is a class of process that the kanban dispatcher can route tasks to. Each lane has an identity (the assignee string), a spawn mechanism, and a con…
- [Kanban (Multi-Agent Board)](user-guide/features/kanban.md) — Durable SQLite-backed task board for coordinating multiple Hermes profiles
- [LSP — Semantic Diagnostics](user-guide/features/lsp.md) — Real language servers (pyright, gopls, rust-analyzer, …) wired into the post-write lint check used by write_file and patch.
- [MCP (Model Context Protocol)](user-guide/features/mcp.md) — Connect Hermes Agent to external tool servers via MCP — and control exactly which MCP tools Hermes loads
- [Memory Providers](user-guide/features/memory-providers.md) — External memory provider plugins — Honcho, OpenViking, Mem0, Hindsight, Holographic, RetainDB, ByteRover, Supermemory
- [Persistent Memory](user-guide/features/memory.md) — How Hermes Agent remembers across sessions — MEMORY.md, USER.md, and session search
- [Mixture of Agents](user-guide/features/mixture-of-agents.md) — Create named MoA presets that appear as selectable models under the Mixture of Agents provider
- [Features Overview](user-guide/features/overview.md) — Hermes Agent includes a rich set of capabilities that extend far beyond basic chat. From persistent memory and file-aware context to browser automation and voic…
- [Personality & SOUL.md](user-guide/features/personality.md) — Customize Hermes Agent's personality with a global SOUL.md, built-in personalities, and custom persona definitions
- [Pets (Petdex Mascots)](user-guide/features/pets.md) — Adopt an animated mascot that reacts to agent activity across the CLI, TUI, and desktop app
- [Plugins](user-guide/features/plugins.md) — Extend Hermes with custom tools, hooks, and integrations via the plugin system
- [Provider Routing](user-guide/features/provider-routing.md) — Configure OpenRouter provider preferences to optimize for cost, speed, or quality.
- [Skills System](user-guide/features/skills.md) — On-demand knowledge documents — progressive disclosure, agent-managed skills, and the Skills Hub
- [Skins & Themes](user-guide/features/skins.md) — Customize the Hermes CLI with built-in and user-defined skins
- [Spotify](user-guide/features/spotify.md) — Hermes can control Spotify directly — playback, queue, search, playlists, saved tracks/albums, and listening history — using Spotify's official Web API with PKC…
- [Subscription Proxy](user-guide/features/subscription-proxy.md) — Use your Nous Portal subscription (or other OAuth provider) as an OpenAI-compatible endpoint for external apps
- [Nous Tool Gateway](user-guide/features/tool-gateway.md) — One subscription, every tool. Web search, image generation, TTS, and cloud browsers — all routed through Nous Portal with no extra API keys.
- [Tool Search](user-guide/features/tool-search.md) — When you have many MCP servers or non-core plugin tools attached to a
- [Tools & Toolsets](user-guide/features/tools.md) — Overview of Hermes Agent's tools — what's available, how toolsets work, and terminal backends
- [Voice & TTS](user-guide/features/tts.md) — Text-to-speech and voice message transcription across all platforms
- [Vision & Image Paste](user-guide/features/vision.md) — Paste images from your clipboard into the Hermes CLI for multimodal vision analysis.
- [Voice Mode](user-guide/features/voice-mode.md) — Real-time voice conversations with Hermes Agent — CLI, Telegram, Discord (DMs, text channels, and voice channels)
- [Web Dashboard](user-guide/features/web-dashboard.md) — Browser-based administration panel for managing configuration, API keys, MCP servers, messaging pairing, webhooks, the gateway, memory, credentials, sessions, logs, analytics, cron jobs, and skills
- [Web Search & Extract](user-guide/features/web-search.md) — Search the web and extract page content with multiple backend providers — including free self-hosted SearXNG.
- [X (Twitter) Search](user-guide/features/x-search.md) — Search X (Twitter) posts and threads from within the agent using xAI's built-in x_search Responses tool — works with either a SuperGrok OAuth login or an XAI_API_KEY.

## user-guide/messaging

- [BlueBubbles (iMessage)](user-guide/messaging/bluebubbles.md) — Connect Hermes to Apple iMessage via BlueBubbles — a free, open-source macOS server that bridges iMessage to any device.
- [DingTalk](user-guide/messaging/dingtalk.md) — Set up Hermes Agent as a DingTalk chatbot
- [Discord](user-guide/messaging/discord.md) — Set up Hermes Agent as a Discord bot
- [Email](user-guide/messaging/email.md) — Set up Hermes Agent as an email assistant via IMAP/SMTP
- [Feishu / Lark](user-guide/messaging/feishu.md) — Set up Hermes Agent as a Feishu or Lark bot
- [Google Chat](user-guide/messaging/google_chat.md) — Set up Hermes Agent as a Google Chat bot using Cloud Pub/Sub
- [Home Assistant](user-guide/messaging/homeassistant.md) — Control your smart home with Hermes Agent via Home Assistant integration.
- [Messaging Gateway](user-guide/messaging/index.md) — Chat with Hermes from Telegram, Discord, Slack, WhatsApp, Signal, SMS, Email, Home Assistant, Mattermost, Matrix, DingTalk, Yuanbao, Microsoft Teams, LINE, Raft, Webhooks, or any OpenAI-compatible frontend via the API server — architecture and setup overview
- [IRC](user-guide/messaging/irc.md) — The IRC adapter connects Hermes to any IRC server and relays messages between an IRC channel (or direct messages) and the agent. It speaks the IRC protocol over…
- [LINE](user-guide/messaging/line.md) — Set up Hermes Agent as a LINE Messaging API bot
- [Matrix](user-guide/messaging/matrix.md) — Set up Hermes Agent as a Matrix bot
- [Mattermost](user-guide/messaging/mattermost.md) — Set up Hermes Agent as a Mattermost bot
- [Microsoft Graph Webhook Listener](user-guide/messaging/msgraph-webhook.md) — Receive Microsoft Graph change notifications (meetings, calendar, chat, etc.) in Hermes
- [ntfy](user-guide/messaging/ntfy.md) — ntfy is a simple HTTP-based pub-sub notification service. It works with the free public server at ntfy.sh or any self-hosted instance, and supports any client t…
- [Open WebUI](user-guide/messaging/open-webui.md) — Connect Open WebUI to Hermes Agent via the OpenAI-compatible API server
- [Photon iMessage](user-guide/messaging/photon.md) — Connect Hermes to iMessage through [Photon][photon], a managed
- [QQ Bot](user-guide/messaging/qqbot.md) — Connect Hermes to QQ via the Official QQ Bot API (v2) — supporting private (C2C), group @-mentions, guild, and direct messages with voice transcription.
- [Raft](user-guide/messaging/raft.md) — Connect Hermes Agent to Raft as an external agent via wake-channel bridge
- [Signal](user-guide/messaging/signal.md) — Set up Hermes Agent as a Signal messenger bot via signal-cli daemon
- [SimpleX Chat](user-guide/messaging/simplex.md) — SimpleX Chat is a private, decentralised messaging platform where users own their contacts and groups. Unlike other platforms, SimpleX assigns no persistent use…
- [Slack](user-guide/messaging/slack.md) — Set up Hermes Agent as a Slack bot using Socket Mode
- [SMS (Twilio)](user-guide/messaging/sms.md) — Set up Hermes Agent as an SMS chatbot via Twilio
- [Teams Meetings](user-guide/messaging/teams-meetings.md) — Set up the Microsoft Teams meeting summary pipeline with Microsoft Graph webhooks
- [Microsoft Teams](user-guide/messaging/teams.md) — Set up Hermes Agent as a Microsoft Teams bot
- [Telegram](user-guide/messaging/telegram.md) — Set up Hermes Agent as a Telegram bot
- [Webhooks](user-guide/messaging/webhooks.md) — Receive events from GitHub, GitLab, and other services to trigger Hermes agent runs
- [WeCom Callback (Self-Built App)](user-guide/messaging/wecom-callback.md) — Connect Hermes to WeCom (Enterprise WeChat) as a self-built enterprise application using the callback/webhook model.
- [WeCom (Enterprise WeChat)](user-guide/messaging/wecom.md) — Connect Hermes Agent to WeCom via the AI Bot WebSocket gateway
- [Weixin (WeChat)](user-guide/messaging/weixin.md) — Connect Hermes Agent to personal WeChat accounts via the iLink Bot API
- [WhatsApp Business (Cloud API)](user-guide/messaging/whatsapp-cloud.md) — Set up Hermes Agent as a WhatsApp bot via Meta's official Business Cloud API
- [WhatsApp](user-guide/messaging/whatsapp.md) — Set up Hermes Agent as a WhatsApp bot via the built-in Baileys bridge
- [Yuanbao](user-guide/messaging/yuanbao.md) — Connect Hermes Agent to the Yuanbao enterprise messaging platform via WebSocket gateway

## user-guide/secrets

- [Bitwarden Secrets Manager](user-guide/secrets/bitwarden.md) — Pull API keys from Bitwarden Secrets Manager at process startup instead of storing them in plaintext inside ~/.hermes/.env. One bootstrap secret (a machine-acco…
- [Secrets](user-guide/secrets/index.md) — Hermes can pull API keys from external secret managers at process startup instead of storing them in ~/.hermes/.env. The bootstrap token for the secret manager…

## user-guide/skills

- [Google Workspace — Gmail, Calendar, Drive, Sheets & Docs](user-guide/skills/google-workspace.md) — Send email, manage calendar events, search Drive, read/write Sheets, and access Docs — all through OAuth2-authenticated Google APIs

## user-guide/skills/bundled/apple

- [Apple Notes — Manage Apple Notes via memo CLI: create, search, edit](user-guide/skills/bundled/apple/apple-apple-notes.md) — Manage Apple Notes via memo CLI: create, search, edit
- [Apple Reminders — Apple Reminders via remindctl: add, list, complete](user-guide/skills/bundled/apple/apple-apple-reminders.md) — Apple Reminders via remindctl: add, list, complete
- [Findmy — Track Apple devices/AirTags via FindMy](user-guide/skills/bundled/apple/apple-findmy.md) — Track Apple devices/AirTags via FindMy
- [Imessage — Send and receive iMessages/SMS via the imsg CLI on macOS](user-guide/skills/bundled/apple/apple-imessage.md) — Send and receive iMessages/SMS via the imsg CLI on macOS
- [Macos Computer Use](user-guide/skills/bundled/apple/apple-macos-computer-use.md) — Drive the macOS desktop in the background — screenshots, mouse, keyboard, scroll, drag — without stealing the user's cursor, keyboard focus, or Space

## user-guide/skills/bundled/autonomous-ai-agents

- [Claude Code — Delegate coding to Claude Code CLI (features, PRs)](user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-claude-code.md) — Delegate coding to Claude Code CLI (features, PRs)
- [Codex — Delegate coding to OpenAI Codex CLI (features, PRs)](user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-codex.md) — Delegate coding to OpenAI Codex CLI (features, PRs)
- [Hermes Agent — Configure, extend, or contribute to Hermes Agent](user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-hermes-agent.md) — Configure, extend, or contribute to Hermes Agent
- [Kanban Codex Lane](user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-kanban-codex-lane.md) — Use when a Hermes Kanban worker wants to run Codex CLI as an isolated implementation lane while Hermes keeps ownership of task lifecycle, reconciliation, tes...
- [Opencode — Delegate coding to OpenCode CLI (features, PR review)](user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-opencode.md) — Delegate coding to OpenCode CLI (features, PR review)

## user-guide/skills/bundled/creative

- [Architecture Diagram — Dark-themed SVG architecture/cloud/infra diagrams as HTML](user-guide/skills/bundled/creative/creative-architecture-diagram.md) — Dark-themed SVG architecture/cloud/infra diagrams as HTML
- [Ascii Art — ASCII art: pyfiglet, cowsay, boxes, image-to-ascii](user-guide/skills/bundled/creative/creative-ascii-art.md) — ASCII art: pyfiglet, cowsay, boxes, image-to-ascii
- [Ascii Video — ASCII video: convert video/audio to colored ASCII MP4/GIF](user-guide/skills/bundled/creative/creative-ascii-video.md) — ASCII video: convert video/audio to colored ASCII MP4/GIF
- [Baoyu Infographic — Infographics: 21 layouts x 21 styles (信息图, 可视化)](user-guide/skills/bundled/creative/creative-baoyu-infographic.md) — Infographics: 21 layouts x 21 styles (信息图, 可视化)
- [Claude Design — Design one-off HTML artifacts (landing, deck, prototype)](user-guide/skills/bundled/creative/creative-claude-design.md) — Design one-off HTML artifacts (landing, deck, prototype)
- [Comfyui](user-guide/skills/bundled/creative/creative-comfyui.md) — Generate images, video, and audio with ComfyUI — install, launch, manage nodes/models, run workflows with parameter injection
- [Design Md — Author/validate/export Google's DESIGN](user-guide/skills/bundled/creative/creative-design-md.md) — Author/validate/export Google's DESIGN
- [Excalidraw — Hand-drawn Excalidraw JSON diagrams (arch, flow, seq)](user-guide/skills/bundled/creative/creative-excalidraw.md) — Hand-drawn Excalidraw JSON diagrams (arch, flow, seq)
- [Humanizer — Humanize text: strip AI-isms and add real voice](user-guide/skills/bundled/creative/creative-humanizer.md) — Humanize text: strip AI-isms and add real voice
- [Manim Video — Manim CE animations: 3Blue1Brown math/algo videos](user-guide/skills/bundled/creative/creative-manim-video.md) — Manim CE animations: 3Blue1Brown math/algo videos
- [P5Js — p5](user-guide/skills/bundled/creative/creative-p5js.md) — p5
- [Popular Web Designs — 54 real design systems (Stripe, Linear, Vercel) as HTML/CSS](user-guide/skills/bundled/creative/creative-popular-web-designs.md) — 54 real design systems (Stripe, Linear, Vercel) as HTML/CSS
- [Pretext](user-guide/skills/bundled/creative/creative-pretext.md) — Use when building creative browser demos with @chenglou/pretext — DOM-free text layout for ASCII art, typographic flow around obstacles, text-as-geometry gam...
- [Sketch — Throwaway HTML mockups: 2-3 design variants to compare](user-guide/skills/bundled/creative/creative-sketch.md) — Throwaway HTML mockups: 2-3 design variants to compare
- [Songwriting And Ai Music — Songwriting craft and Suno AI music prompts](user-guide/skills/bundled/creative/creative-songwriting-and-ai-music.md) — Songwriting craft and Suno AI music prompts
- [Touchdesigner Mcp](user-guide/skills/bundled/creative/creative-touchdesigner-mcp.md) — Control a running TouchDesigner instance via twozero MCP — create operators, set parameters, wire connections, execute Python, build real-time visuals

## user-guide/skills/bundled/data-science

- [Jupyter Live Kernel — Iterative Python via live Jupyter kernel (hamelnb)](user-guide/skills/bundled/data-science/data-science-jupyter-live-kernel.md) — Iterative Python via live Jupyter kernel (hamelnb)

## user-guide/skills/bundled/dogfood

- [Dogfood — Exploratory QA of web apps: find bugs, evidence, reports](user-guide/skills/bundled/dogfood/dogfood-dogfood.md) — Exploratory QA of web apps: find bugs, evidence, reports

## user-guide/skills/bundled/email

- [Himalaya — Himalaya CLI: IMAP/SMTP email from terminal](user-guide/skills/bundled/email/email-himalaya.md) — Himalaya CLI: IMAP/SMTP email from terminal

## user-guide/skills/bundled/github

- [Codebase Inspection — Inspect codebases w/ pygount: LOC, languages, ratios](user-guide/skills/bundled/github/github-codebase-inspection.md) — Inspect codebases w/ pygount: LOC, languages, ratios
- [Github Auth — GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login](user-guide/skills/bundled/github/github-github-auth.md) — GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login
- [Github Code Review — Review PRs: diffs, inline comments via gh or REST](user-guide/skills/bundled/github/github-github-code-review.md) — Review PRs: diffs, inline comments via gh or REST
- [Github Issues — Create, triage, label, assign GitHub issues via gh or REST](user-guide/skills/bundled/github/github-github-issues.md) — Create, triage, label, assign GitHub issues via gh or REST
- [Github Pr Workflow — GitHub PR lifecycle: branch, commit, open, CI, merge](user-guide/skills/bundled/github/github-github-pr-workflow.md) — GitHub PR lifecycle: branch, commit, open, CI, merge
- [Github Repo Management — Clone/create/fork repos; manage remotes, releases](user-guide/skills/bundled/github/github-github-repo-management.md) — Clone/create/fork repos; manage remotes, releases

## user-guide/skills/bundled/media

- [Gif Search — Search/download GIFs from Tenor via curl + jq](user-guide/skills/bundled/media/media-gif-search.md) — Search/download GIFs from Tenor via curl + jq
- [Heartmula — HeartMuLa: Suno-like song generation from lyrics + tags](user-guide/skills/bundled/media/media-heartmula.md) — HeartMuLa: Suno-like song generation from lyrics + tags
- [Songsee — Audio spectrograms/features (mel, chroma, MFCC) via CLI](user-guide/skills/bundled/media/media-songsee.md) — Audio spectrograms/features (mel, chroma, MFCC) via CLI
- [Youtube Content — YouTube transcripts to summaries, threads, blogs](user-guide/skills/bundled/media/media-youtube-content.md) — YouTube transcripts to summaries, threads, blogs

## user-guide/skills/bundled/mlops

- [Evaluating Llms Harness — lm-eval-harness: benchmark LLMs (MMLU, GSM8K, etc](user-guide/skills/bundled/mlops/mlops-evaluation-lm-evaluation-harness.md) — lm-eval-harness: benchmark LLMs (MMLU, GSM8K, etc
- [Weights And Biases — W&B: log ML experiments, sweeps, model registry, dashboards](user-guide/skills/bundled/mlops/mlops-evaluation-weights-and-biases.md) — W&B: log ML experiments, sweeps, model registry, dashboards
- [Huggingface Hub — HuggingFace hf CLI: search/download/upload models, datasets](user-guide/skills/bundled/mlops/mlops-huggingface-hub.md) — HuggingFace hf CLI: search/download/upload models, datasets
- [Llama Cpp — llama](user-guide/skills/bundled/mlops/mlops-inference-llama-cpp.md) — llama
- [Serving Llms Vllm — vLLM: high-throughput LLM serving, OpenAI API, quantization](user-guide/skills/bundled/mlops/mlops-inference-vllm.md) — vLLM: high-throughput LLM serving, OpenAI API, quantization
- [Audiocraft Audio Generation — AudioCraft: MusicGen text-to-music, AudioGen text-to-sound](user-guide/skills/bundled/mlops/mlops-models-audiocraft.md) — AudioCraft: MusicGen text-to-music, AudioGen text-to-sound
- [Segment Anything Model — SAM: zero-shot image segmentation via points, boxes, masks](user-guide/skills/bundled/mlops/mlops-models-segment-anything.md) — SAM: zero-shot image segmentation via points, boxes, masks

## user-guide/skills/bundled/note-taking

- [Obsidian — Read, search, create, and edit notes in the Obsidian vault](user-guide/skills/bundled/note-taking/note-taking-obsidian.md) — Read, search, create, and edit notes in the Obsidian vault

## user-guide/skills/bundled/productivity

- [Airtable — Airtable REST API via curl](user-guide/skills/bundled/productivity/productivity-airtable.md) — Airtable REST API via curl
- [Google Workspace — Gmail, Calendar, Drive, Docs, Sheets via gws CLI or Python](user-guide/skills/bundled/productivity/productivity-google-workspace.md) — Gmail, Calendar, Drive, Docs, Sheets via gws CLI or Python
- [Maps — Geocode, POIs, routes, timezones via OpenStreetMap/OSRM](user-guide/skills/bundled/productivity/productivity-maps.md) — Geocode, POIs, routes, timezones via OpenStreetMap/OSRM
- [Nano Pdf — Edit PDF text/typos/titles via nano-pdf CLI (NL prompts)](user-guide/skills/bundled/productivity/productivity-nano-pdf.md) — Edit PDF text/typos/titles via nano-pdf CLI (NL prompts)
- [Notion — Notion API + ntn CLI: pages, databases, markdown, Workers](user-guide/skills/bundled/productivity/productivity-notion.md) — Notion API + ntn CLI: pages, databases, markdown, Workers
- [Ocr And Documents — Extract text from PDFs/scans (pymupdf, marker-pdf)](user-guide/skills/bundled/productivity/productivity-ocr-and-documents.md) — Extract text from PDFs/scans (pymupdf, marker-pdf)
- [Petdex — Install and select animated petdex mascots for Hermes](user-guide/skills/bundled/productivity/productivity-petdex.md) — Install and select animated petdex mascots for Hermes
- [Powerpoint — Create, read, edit](user-guide/skills/bundled/productivity/productivity-powerpoint.md) — Create, read, edit
- [Teams Meeting Pipeline](user-guide/skills/bundled/productivity/productivity-teams-meeting-pipeline.md) — Operate the Teams meeting summary pipeline via Hermes CLI — summarize meetings, inspect pipeline status, replay jobs, manage Microsoft Graph subscriptions

## user-guide/skills/bundled/research

- [Arxiv — Search arXiv papers by keyword, author, category, or ID](user-guide/skills/bundled/research/research-arxiv.md) — Search arXiv papers by keyword, author, category, or ID
- [Blogwatcher — Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool](user-guide/skills/bundled/research/research-blogwatcher.md) — Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool
- [Llm Wiki — Karpathy's LLM Wiki: build/query interlinked markdown KB](user-guide/skills/bundled/research/research-llm-wiki.md) — Karpathy's LLM Wiki: build/query interlinked markdown KB
- [Polymarket — Query Polymarket: markets, prices, orderbooks, history](user-guide/skills/bundled/research/research-polymarket.md) — Query Polymarket: markets, prices, orderbooks, history
- [Research Paper Writing — Write ML papers for NeurIPS/ICML/ICLR: design→submit](user-guide/skills/bundled/research/research-research-paper-writing.md) — Write ML papers for NeurIPS/ICML/ICLR: design→submit

## user-guide/skills/bundled/smart-home

- [Openhue — Control Philips Hue lights, scenes, rooms via OpenHue CLI](user-guide/skills/bundled/smart-home/smart-home-openhue.md) — Control Philips Hue lights, scenes, rooms via OpenHue CLI

## user-guide/skills/bundled/social-media

- [Xurl — X/Twitter via xurl CLI: post, search, DM, media, v2 API](user-guide/skills/bundled/social-media/social-media-xurl.md) — X/Twitter via xurl CLI: post, search, DM, media, v2 API

## user-guide/skills/bundled/software-development

- [Hermes Agent Skill Authoring — Author in-repo SKILL](user-guide/skills/bundled/software-development/software-development-hermes-agent-skill-authoring.md) — Author in-repo SKILL
- [Node Inspect Debugger — Debug Node](user-guide/skills/bundled/software-development/software-development-node-inspect-debugger.md) — Debug Node
- [Plan — Plan mode: write an actionable markdown plan to](user-guide/skills/bundled/software-development/software-development-plan.md) — Plan mode: write an actionable markdown plan to
- [Python Debugpy — Debug Python: pdb REPL + debugpy remote (DAP)](user-guide/skills/bundled/software-development/software-development-python-debugpy.md) — Debug Python: pdb REPL + debugpy remote (DAP)
- [Requesting Code Review — Pre-commit review: security scan, quality gates, auto-fix](user-guide/skills/bundled/software-development/software-development-requesting-code-review.md) — Pre-commit review: security scan, quality gates, auto-fix
- [Simplify Code — Parallel 3-agent cleanup of recent code changes](user-guide/skills/bundled/software-development/software-development-simplify-code.md) — Parallel 3-agent cleanup of recent code changes
- [Spike — Throwaway experiments to validate an idea before build](user-guide/skills/bundled/software-development/software-development-spike.md) — Throwaway experiments to validate an idea before build
- [Systematic Debugging — 4-phase root cause debugging: understand bugs before fixing](user-guide/skills/bundled/software-development/software-development-systematic-debugging.md) — 4-phase root cause debugging: understand bugs before fixing
- [Test Driven Development — TDD: enforce RED-GREEN-REFACTOR, tests before code](user-guide/skills/bundled/software-development/software-development-test-driven-development.md) — TDD: enforce RED-GREEN-REFACTOR, tests before code

## user-guide/skills/bundled/yuanbao

- [Yuanbao — Yuanbao (元宝) groups: @mention users, query info/members](user-guide/skills/bundled/yuanbao/yuanbao-yuanbao.md) — Yuanbao (元宝) groups: @mention users, query info/members

## user-guide/skills/optional/autonomous-ai-agents

- [Antigravity Cli — Operate the Antigravity CLI (agy): plugins, auth, sandbox](user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-antigravity-cli.md) — Operate the Antigravity CLI (agy): plugins, auth, sandbox
- [Blackbox — Delegate coding tasks to Blackbox AI CLI agent](user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-blackbox.md) — Delegate coding tasks to Blackbox AI CLI agent
- [Grok — Delegate coding to xAI Grok Build CLI (features, PRs)](user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-grok.md) — Delegate coding to xAI Grok Build CLI (features, PRs)
- [Honcho](user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-honcho.md) — Configure and use Honcho memory with Hermes -- cross-session user modeling, multi-profile peer isolation, observation config, dialectic reasoning, session su...
- [Openhands — Delegate coding to OpenHands CLI (model-agnostic, LiteLLM)](user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-openhands.md) — Delegate coding to OpenHands CLI (model-agnostic, LiteLLM)

## user-guide/skills/optional/blockchain

- [Evm — Read-only EVM client: wallets, tokens, gas across 8 chains](user-guide/skills/optional/blockchain/blockchain-evm.md) — Read-only EVM client: wallets, tokens, gas across 8 chains
- [Hyperliquid — Hyperliquid market data, account history, trade review](user-guide/skills/optional/blockchain/blockchain-hyperliquid.md) — Hyperliquid market data, account history, trade review
- [Solana](user-guide/skills/optional/blockchain/blockchain-solana.md) — Query Solana blockchain data with USD pricing — wallet balances, token portfolios with values, transaction details, NFTs, whale detection, and live network s...

## user-guide/skills/optional/communication

- [One Three One Rule — Structured decision-making framework for technical proposals and trade-off analysis](user-guide/skills/optional/communication/communication-one-three-one-rule.md) — Structured decision-making framework for technical proposals and trade-off analysis

## user-guide/skills/optional/creative

- [Baoyu Article Illustrator — Article illustrations: type × style × palette consistency](user-guide/skills/optional/creative/creative-baoyu-article-illustrator.md) — Article illustrations: type × style × palette consistency
- [Baoyu Comic — Knowledge comics (知识漫画): educational, biography, tutorial](user-guide/skills/optional/creative/creative-baoyu-comic.md) — Knowledge comics (知识漫画): educational, biography, tutorial
- [Blender Mcp — Control Blender directly from Hermes via socket connection to the blender-mcp addon](user-guide/skills/optional/creative/creative-blender-mcp.md) — Control Blender directly from Hermes via socket connection to the blender-mcp addon
- [Concept Diagrams](user-guide/skills/optional/creative/creative-concept-diagrams.md) — Generate flat, minimal light/dark-aware SVG diagrams as standalone HTML files, using a unified educational visual language with 9 semantic color ramps, sente...
- [Creative Ideation — Generate ideas via named methods from creative practice](user-guide/skills/optional/creative/creative-creative-ideation.md) — Generate ideas via named methods from creative practice
- [Hyperframes](user-guide/skills/optional/creative/creative-hyperframes.md) — Create HTML-based video compositions, animated title cards, social overlays, captioned talking-head videos, audio-reactive visuals, and shader transitions us...
- [Kanban Video Orchestrator — Plan, set up, and monitor a multi-agent video production pipeline backed by Hermes Kanban](user-guide/skills/optional/creative/creative-kanban-video-orchestrator.md) — Plan, set up, and monitor a multi-agent video production pipeline backed by Hermes Kanban
- [Meme Generation — Generate real meme images by picking a template and overlaying text with Pillow](user-guide/skills/optional/creative/creative-meme-generation.md) — Generate real meme images by picking a template and overlaying text with Pillow
- [Pixel Art — Pixel art w/ era palettes (NES, Game Boy, PICO-8)](user-guide/skills/optional/creative/creative-pixel-art.md) — Pixel art w/ era palettes (NES, Game Boy, PICO-8)

## user-guide/skills/optional/devops

- [Inference Sh Cli — Run 150+ AI apps via inference](user-guide/skills/optional/devops/devops-cli.md) — Run 150+ AI apps via inference
- [Docker Management](user-guide/skills/optional/devops/devops-docker-management.md) — Manage Docker containers, images, volumes, networks, and Compose stacks — lifecycle ops, debugging, cleanup, and Dockerfile optimization
- [Hermes S6 Container Supervision](user-guide/skills/optional/devops/devops-hermes-s6-container-supervision.md) — Modify, debug, or extend the s6-overlay supervision tree inside the Hermes Agent Docker image — adding new services, debugging profile gateways, understandin...
- [Pinggy Tunnel — Zero-install localhost tunnels over SSH via Pinggy](user-guide/skills/optional/devops/devops-pinggy-tunnel.md) — Zero-install localhost tunnels over SSH via Pinggy
- [Watchers — Poll RSS, JSON APIs, and GitHub with watermark dedup](user-guide/skills/optional/devops/devops-watchers.md) — Poll RSS, JSON APIs, and GitHub with watermark dedup

## user-guide/skills/optional/dogfood

- [Adversarial Ux Test — Roleplay the most difficult, tech-resistant user for your product](user-guide/skills/optional/dogfood/dogfood-adversarial-ux-test.md) — Roleplay the most difficult, tech-resistant user for your product

## user-guide/skills/optional/email

- [Agentmail — Give the agent its own dedicated email inbox via AgentMail](user-guide/skills/optional/email/email-agentmail.md) — Give the agent its own dedicated email inbox via AgentMail

## user-guide/skills/optional/finance

- [3 Statement Model](user-guide/skills/optional/finance/finance-3-statement-model.md) — Build fully-integrated 3-statement models (IS, BS, CF) in Excel with working capital schedules, D&A roll-forwards, debt schedule, and the plugs that make cas...
- [Comps Analysis](user-guide/skills/optional/finance/finance-comps-analysis.md) — Build comparable company analysis in Excel — operating metrics, valuation multiples, statistical benchmarking vs peer sets
- [Dcf Model](user-guide/skills/optional/finance/finance-dcf-model.md) — Build institutional-quality DCF valuation models in Excel — revenue projections, FCF build, WACC, terminal value, Bear/Base/Bull scenarios, 5x5 sensitivity t...
- [Excel Author](user-guide/skills/optional/finance/finance-excel-author.md) — Build auditable Excel workbooks headless with openpyxl — blue/black/green cell conventions, formulas over hardcodes, named ranges, balance checks, sensitivit...
- [Lbo Model](user-guide/skills/optional/finance/finance-lbo-model.md) — Build leveraged buyout models in Excel — sources & uses, debt schedule, cash sweep, exit multiple, IRR/MOIC sensitivity
- [Merger Model — Build accretion/dilution (merger) models in Excel — pro-forma P&L, synergies, financing mix, EPS impact](user-guide/skills/optional/finance/finance-merger-model.md) — Build accretion/dilution (merger) models in Excel — pro-forma P&L, synergies, financing mix, EPS impact
- [Pptx Author — Build PowerPoint decks headless with python-pptx](user-guide/skills/optional/finance/finance-pptx-author.md) — Build PowerPoint decks headless with python-pptx
- [Stocks — Stock quotes, history, search, compare, crypto via Yahoo](user-guide/skills/optional/finance/finance-stocks.md) — Stock quotes, history, search, compare, crypto via Yahoo

## user-guide/skills/optional/gaming

- [Minecraft Modpack Server — Host modded Minecraft servers (CurseForge, Modrinth)](user-guide/skills/optional/gaming/gaming-minecraft-modpack-server.md) — Host modded Minecraft servers (CurseForge, Modrinth)
- [Pokemon Player — Play Pokemon via headless emulator + RAM reads](user-guide/skills/optional/gaming/gaming-pokemon-player.md) — Play Pokemon via headless emulator + RAM reads

## user-guide/skills/optional/health

- [Fitness Nutrition — Gym workout planner and nutrition tracker](user-guide/skills/optional/health/health-fitness-nutrition.md) — Gym workout planner and nutrition tracker
- [Neuroskill Bci](user-guide/skills/optional/health/health-neuroskill-bci.md) — Connect to a running NeuroSkill instance and incorporate the user's real-time cognitive and emotional state (focus, relaxation, mood, cognitive load, drowsin...

## user-guide/skills/optional/mcp

- [Fastmcp — Build, test, inspect, install, and deploy MCP servers with FastMCP in Python](user-guide/skills/optional/mcp/mcp-fastmcp.md) — Build, test, inspect, install, and deploy MCP servers with FastMCP in Python
- [Mcporter](user-guide/skills/optional/mcp/mcp-mcporter.md) — Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type gene...

## user-guide/skills/optional/migration

- [Openclaw Migration — Migrate a user's OpenClaw customization footprint into Hermes Agent](user-guide/skills/optional/migration/migration-openclaw-migration.md) — Migrate a user's OpenClaw customization footprint into Hermes Agent

## user-guide/skills/optional/mlops

- [Huggingface Accelerate — Simplest distributed training API](user-guide/skills/optional/mlops/mlops-accelerate.md) — Simplest distributed training API
- [Chroma — Open-source embedding database for AI applications](user-guide/skills/optional/mlops/mlops-chroma.md) — Open-source embedding database for AI applications
- [Clip — OpenAI's model connecting vision and language](user-guide/skills/optional/mlops/mlops-clip.md) — OpenAI's model connecting vision and language
- [Faiss — Facebook's library for efficient similarity search and clustering of dense vectors](user-guide/skills/optional/mlops/mlops-faiss.md) — Facebook's library for efficient similarity search and clustering of dense vectors
- [Optimizing Attention Flash](user-guide/skills/optional/mlops/mlops-flash-attention.md) — Optimizes transformer attention with Flash Attention for 2-4x speedup and 10-20x memory reduction
- [Guidance](user-guide/skills/optional/mlops/mlops-guidance.md) — Control LLM output with regex and grammars, guarantee valid JSON/XML/code generation, enforce structured formats, and build multi-step workflows with Guidanc...
- [Huggingface Tokenizers — Fast tokenizers optimized for research and production](user-guide/skills/optional/mlops/mlops-huggingface-tokenizers.md) — Fast tokenizers optimized for research and production
- [Outlines — Outlines: structured JSON/regex/Pydantic LLM generation](user-guide/skills/optional/mlops/mlops-inference-outlines.md) — Outlines: structured JSON/regex/Pydantic LLM generation
- [Instructor](user-guide/skills/optional/mlops/mlops-instructor.md) — Extract structured data from LLM responses with Pydantic validation, retry failed extractions automatically, parse complex JSON with type safety, and stream ...
- [Lambda Labs Gpu Cloud — Reserved and on-demand GPU cloud instances for ML training and inference](user-guide/skills/optional/mlops/mlops-lambda-labs.md) — Reserved and on-demand GPU cloud instances for ML training and inference
- [Llava — Large Language and Vision Assistant](user-guide/skills/optional/mlops/mlops-llava.md) — Large Language and Vision Assistant
- [Modal Serverless Gpu — Serverless GPU cloud platform for running ML workloads](user-guide/skills/optional/mlops/mlops-modal.md) — Serverless GPU cloud platform for running ML workloads
- [Nemo Curator — GPU-accelerated data curation for LLM training](user-guide/skills/optional/mlops/mlops-nemo-curator.md) — GPU-accelerated data curation for LLM training
- [Obliteratus — OBLITERATUS: abliterate LLM refusals (diff-in-means)](user-guide/skills/optional/mlops/mlops-obliteratus.md) — OBLITERATUS: abliterate LLM refusals (diff-in-means)
- [Peft Fine Tuning — Parameter-efficient fine-tuning for LLMs using LoRA, QLoRA, and 25+ methods](user-guide/skills/optional/mlops/mlops-peft.md) — Parameter-efficient fine-tuning for LLMs using LoRA, QLoRA, and 25+ methods
- [Pinecone — Managed vector database for production AI applications](user-guide/skills/optional/mlops/mlops-pinecone.md) — Managed vector database for production AI applications
- [Pytorch Fsdp](user-guide/skills/optional/mlops/mlops-pytorch-fsdp.md) — Expert guidance for Fully Sharded Data Parallel training with PyTorch FSDP - parameter sharding, mixed precision, CPU offloading, FSDP2
- [Pytorch Lightning](user-guide/skills/optional/mlops/mlops-pytorch-lightning.md) — High-level PyTorch framework with Trainer class, automatic distributed training (DDP/FSDP/DeepSpeed), callbacks system, and minimal boilerplate
- [Qdrant Vector Search — High-performance vector similarity search engine for RAG and semantic search](user-guide/skills/optional/mlops/mlops-qdrant.md) — High-performance vector similarity search engine for RAG and semantic search
- [Dspy — DSPy: declarative LM programs, auto-optimize prompts, RAG](user-guide/skills/optional/mlops/mlops-research-dspy.md) — DSPy: declarative LM programs, auto-optimize prompts, RAG
- [Sparse Autoencoder Training](user-guide/skills/optional/mlops/mlops-saelens.md) — Provides guidance for training and analyzing Sparse Autoencoders (SAEs) using SAELens to decompose neural network activations into interpretable features
- [Simpo Training — Simple Preference Optimization for LLM alignment](user-guide/skills/optional/mlops/mlops-simpo.md) — Simple Preference Optimization for LLM alignment
- [Slime Rl Training — Provides guidance for LLM post-training with RL using slime, a Megatron+SGLang framework](user-guide/skills/optional/mlops/mlops-slime.md) — Provides guidance for LLM post-training with RL using slime, a Megatron+SGLang framework
- [Stable Diffusion Image Generation](user-guide/skills/optional/mlops/mlops-stable-diffusion.md) — State-of-the-art text-to-image generation with Stable Diffusion models via HuggingFace Diffusers
- [Tensorrt Llm — Optimizes LLM inference with NVIDIA TensorRT for maximum throughput and lowest latency](user-guide/skills/optional/mlops/mlops-tensorrt-llm.md) — Optimizes LLM inference with NVIDIA TensorRT for maximum throughput and lowest latency
- [Distributed Llm Pretraining Torchtitan](user-guide/skills/optional/mlops/mlops-torchtitan.md) — Provides PyTorch-native distributed LLM pretraining using torchtitan with 4D parallelism (FSDP2, TP, PP, CP)
- [Axolotl — Axolotl: YAML LLM fine-tuning (LoRA, DPO, GRPO)](user-guide/skills/optional/mlops/mlops-training-axolotl.md) — Axolotl: YAML LLM fine-tuning (LoRA, DPO, GRPO)
- [Fine Tuning With Trl — TRL: SFT, DPO, PPO, GRPO, reward modeling for LLM RLHF](user-guide/skills/optional/mlops/mlops-training-trl-fine-tuning.md) — TRL: SFT, DPO, PPO, GRPO, reward modeling for LLM RLHF
- [Unsloth — Unsloth: 2-5x faster LoRA/QLoRA fine-tuning, less VRAM](user-guide/skills/optional/mlops/mlops-training-unsloth.md) — Unsloth: 2-5x faster LoRA/QLoRA fine-tuning, less VRAM
- [Whisper — OpenAI's general-purpose speech recognition model](user-guide/skills/optional/mlops/mlops-whisper.md) — OpenAI's general-purpose speech recognition model

## user-guide/skills/optional/payments

- [Mpp Agent — Pay HTTP 402 APIs via Machine Payments Protocol (MPP)](user-guide/skills/optional/payments/payments-mpp-agent.md) — Pay HTTP 402 APIs via Machine Payments Protocol (MPP)
- [Stripe Link Cli — Agent payments via Stripe Link — cards, SPT, approvals](user-guide/skills/optional/payments/payments-stripe-link-cli.md) — Agent payments via Stripe Link — cards, SPT, approvals
- [Stripe Projects — Provision SaaS services + sync creds via Stripe Projects](user-guide/skills/optional/payments/payments-stripe-projects.md) — Provision SaaS services + sync creds via Stripe Projects

## user-guide/skills/optional/productivity

- [Canvas — Canvas LMS integration — fetch enrolled courses and assignments using API token authentication](user-guide/skills/optional/productivity/productivity-canvas.md) — Canvas LMS integration — fetch enrolled courses and assignments using API token authentication
- [Here.Now — Publish static sites to {slug}](user-guide/skills/optional/productivity/productivity-here-now.md) — Publish static sites to {slug}
- [Memento Flashcards — Spaced-repetition flashcard system](user-guide/skills/optional/productivity/productivity-memento-flashcards.md) — Spaced-repetition flashcard system
- [Shop — Shop catalog search, checkout, order tracking, returns](user-guide/skills/optional/productivity/productivity-shop.md) — Shop catalog search, checkout, order tracking, returns
- [Shopify — Shopify Admin & Storefront GraphQL APIs via curl](user-guide/skills/optional/productivity/productivity-shopify.md) — Shopify Admin & Storefront GraphQL APIs via curl
- [Siyuan](user-guide/skills/optional/productivity/productivity-siyuan.md) — SiYuan Note API for searching, reading, creating, and managing blocks and documents in a self-hosted knowledge base via curl
- [Telephony — Give Hermes phone capabilities without core tool changes](user-guide/skills/optional/productivity/productivity-telephony.md) — Give Hermes phone capabilities without core tool changes

## user-guide/skills/optional/research

- [Bioinformatics — Gateway to 400+ bioinformatics skills from bioSkills and ClawBio](user-guide/skills/optional/research/research-bioinformatics.md) — Gateway to 400+ bioinformatics skills from bioSkills and ClawBio
- [Darwinian Evolver — Evolve prompts/regex/SQL/code with Imbue's evolution loop](user-guide/skills/optional/research/research-darwinian-evolver.md) — Evolve prompts/regex/SQL/code with Imbue's evolution loop
- [Domain Intel — Passive domain reconnaissance using Python stdlib](user-guide/skills/optional/research/research-domain-intel.md) — Passive domain reconnaissance using Python stdlib
- [Drug Discovery — Pharmaceutical research assistant for drug discovery workflows](user-guide/skills/optional/research/research-drug-discovery.md) — Pharmaceutical research assistant for drug discovery workflows
- [Duckduckgo Search — Free web search via DuckDuckGo — text, news, images, videos](user-guide/skills/optional/research/research-duckduckgo-search.md) — Free web search via DuckDuckGo — text, news, images, videos
- [Gitnexus Explorer](user-guide/skills/optional/research/research-gitnexus-explorer.md) — Index a codebase with GitNexus and serve an interactive knowledge graph via web UI + Cloudflare tunnel
- [Osint Investigation](user-guide/skills/optional/research/research-osint-investigation.md) — Public-records OSINT investigation framework — SEC EDGAR filings, USAspending contracts, Senate lobbying, OFAC sanctions, ICIJ offshore leaks, NYC property r...
- [Parallel Cli](user-guide/skills/optional/research/research-parallel-cli.md) — Optional vendor skill for Parallel CLI — agent-native web search, extraction, deep research, enrichment, FindAll, and monitoring
- [Qmd](user-guide/skills/optional/research/research-qmd.md) — Search personal knowledge bases, notes, docs, and meeting transcripts locally using qmd — a hybrid retrieval engine with BM25, vector search, and LLM reranking
- [Scrapling](user-guide/skills/optional/research/research-scrapling.md) — Web scraping with Scrapling - HTTP fetching, stealth browser automation, Cloudflare bypass, and spider crawling via CLI and Python
- [Searxng Search — Free meta-search via SearXNG — aggregates results from 70+ search engines](user-guide/skills/optional/research/research-searxng-search.md) — Free meta-search via SearXNG — aggregates results from 70+ search engines

## user-guide/skills/optional/security

- [1Password — Set up and use 1Password CLI (op)](user-guide/skills/optional/security/security-1password.md) — Set up and use 1Password CLI (op)
- [Godmode — Jailbreak LLMs: Parseltongue, GODMODE, ULTRAPLINIAN](user-guide/skills/optional/security/security-godmode.md) — Jailbreak LLMs: Parseltongue, GODMODE, ULTRAPLINIAN
- [Oss Forensics — Supply chain investigation, evidence recovery, and forensic analysis for GitHub repositories](user-guide/skills/optional/security/security-oss-forensics.md) — Supply chain investigation, evidence recovery, and forensic analysis for GitHub repositories
- [Sherlock — OSINT username search across 400+ social networks](user-guide/skills/optional/security/security-sherlock.md) — OSINT username search across 400+ social networks
- [Web Pentest](user-guide/skills/optional/security/security-web-pentest.md) — Authorized web application penetration testing — reconnaissance, vulnerability analysis, proof-based exploitation, and professional reporting

## user-guide/skills/optional/software-development

- [Code Wiki — Generate wiki docs + Mermaid diagrams for any codebase](user-guide/skills/optional/software-development/software-development-code-wiki.md) — Generate wiki docs + Mermaid diagrams for any codebase
- [Rest Graphql Debug — Debug REST/GraphQL APIs: status codes, auth, schemas, repro](user-guide/skills/optional/software-development/software-development-rest-graphql-debug.md) — Debug REST/GraphQL APIs: status codes, auth, schemas, repro
- [Subagent Driven Development — Execute plans via delegate_task subagents (2-stage review)](user-guide/skills/optional/software-development/software-development-subagent-driven-development.md) — Execute plans via delegate_task subagents (2-stage review)

## user-guide/skills/optional/web-development

- [Page Agent](user-guide/skills/optional/web-development/web-development-page-agent.md) — Embed alibaba/page-agent into your own web application — a pure-JavaScript in-page GUI agent that ships as a single <script> tag or npm package and lets end-...

