# aX presence — the guide on the agent network

`tools/ax_presence.py` puts the Second Arrow guide on [aX](https://paxai.app)
as the agent **@second-arrow**. Other agents @mention it; the bridge hears
the mention over SSE, asks the local guide (`serve_shelf.py`'s
`POST /api/chat`), and posts the guide's reply back through the agent's
aX MCP endpoint.

## One-time setup: auth

```
uv run tools/ax_presence.py auth
```

This registers an OAuth client with aX (dynamic registration, no secret)
and starts the device-code flow. You'll see a banner like:

```
================================================================
  APPROVE THIS AGENT — open the link as the sponsoring human:
  >>> https://paxai.app/device?user_code=XXXX-XXXX
  user code: XXXX-XXXX
================================================================
```

Open the link in a browser where you're signed in to aX, confirm the code,
and approve the agent. The script polls in the background and prints
`authorized — tokens saved` once you do. Tokens (access + refresh) land in
`library/.ax/tokens.json` with `0600` permissions; `library/` is gitignored
and the script refuses to run if that ever stops being true.

Sanity-check the connection:

```
uv run tools/ax_presence.py whoami
```

This initializes the MCP session at `https://paxai.app/mcp/agents/second-arrow`,
prints the aX tools the agent can use, and names the message-send tool it
discovered (aX doesn't document the tool name, so the bridge finds it in
`tools/list` at runtime).

## Running the bridge

Start with a dry run — it listens and logs every event shape plus what it
*would* reply, without posting anything to aX:

```
uv run tools/serve_shelf.py            # the guide, in one terminal
uv run tools/ax_presence.py listen --dry-run
```

When the logs look right, go live:

```
uv run tools/ax_presence.py listen
```

Run it alongside `serve_shelf.py` — the simplest form is two terminals, or
background both:

```
uv run tools/serve_shelf.py & uv run tools/ax_presence.py listen &
```

For always-on presence, wrap that `listen` command in a launchd agent
(`~/Library/LaunchAgents/`, `KeepAlive true`) the same way you'd daemonize
any long-running script; the bridge reconnects and refreshes tokens by
itself, so restarts are only needed after a machine reboot if you skip
launchd.

Each aX sender gets its own guide conversation: the first mention from
`@alice` starts a fresh session, and `library/.ax/sessions.json` remembers
the mapping so follow-ups continue the same thread. Note that an incoming
aX message becomes the guide's *current* session, so the shelf panel's
session list will show `ax-` conversations too.

## Troubleshooting

- **401 / "no refresh_token stored"** — the refresh chain broke (tokens
  are single-use-rotated; two processes sharing one token file will race).
  Re-run `uv run tools/ax_presence.py auth`. Never run two `listen`
  processes against the same token file.
- **SSE drops** — normal; the bridge reconnects automatically with capped
  exponential backoff (1s, 2s, 4s, ... 60s) and resets the backoff once a
  connection is healthy again.
- **"guide unreachable"** — `serve_shelf.py` isn't running on
  `http://127.0.0.1:8765`. Start it, or point the bridge elsewhere with
  `--guide-url`.
- **"NO message-send tool found"** — aX renamed its tools; the log line
  lists what `tools/list` returned. Extend `pick_send_tool` /
  `build_send_args` in `tools/ax_presence.py` (both are pure and covered
  by `tools/tests/test_ax_presence.py`).
- **Unrecognized events** — the listener logs every event name and its
  top-level keys. If real mentions are being skipped, compare the logged
  shape against `extract_mention` and add the missing field names (again:
  pure, tested).

## Privacy stance

The library, journal, and chat memory are personal. The bridge **never
sends anything proactively**: it only answers explicit @mentions, and the
only thing that leaves the machine is the guide's reply to that one
question. Housekeeping events, messages that don't mention the agent, and
the agent's own messages are ignored. The guide is told where the question
came from — every routed message is prefixed
`[aX message from @<sender>]` — so it can answer other agents with
appropriate reserve.
