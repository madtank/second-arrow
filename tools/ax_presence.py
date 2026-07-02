#!/usr/bin/env python3
# /// script
# dependencies = ["httpx", "mcp"]
# ///
"""aX presence bridge: the Second Arrow guide as an agent on aX (paxai.app).

Other agents @mention `second-arrow` on aX; this bridge hears the mention
over SSE, asks the local study guide (serve_shelf.py's POST /api/chat) for
a reply, and posts that reply back through the agent's aX MCP endpoint.

Subcommands
    auth      one-time device-code OAuth. Registers a public client
              (dynamic registration, cached), prints a verification URL +
              user code for the human sponsor to approve, polls for the
              token, and stores it in library/.ax/tokens.json (0600 —
              library/ is gitignored, and we verify that).
    whoami    validates the token: MCP initialize against
              https://paxai.app/mcp/agents/<agent> and a tools/list, so
              you can see the identity and which aX tools exist.
    listen    the bridge loop: GET /api/sse/messages (SSE, bearer auth),
              on a mention -> POST to the local guide, reply via the aX
              MCP message-send tool (discovered at runtime via tools/list
              — aX does not document the tool name, so we log what we
              find). Reconnects with capped exponential backoff; Ctrl-C
              exits cleanly. --dry-run logs what WOULD be sent instead
              of sending.

Sessions: each aX sender gets a stable guide conversation. serve_shelf
404s on a session id it has never seen, so the first message from a
sender is posted with session="new"; the X-Session response header names
the minted session and library/.ax/sessions.json remembers sender -> id.

Privacy: the guide's library, journal, and chat memory are personal.
This bridge NEVER sends anything proactively — it only answers explicit
mentions, and the reply is whatever the guide chose to say to that
question. Housekeeping events, plain messages that don't mention the
agent, and the agent's own messages are all ignored.

Auth notes (verified against https://paxai.app/auth.md):
    POST /oauth/register     dynamic client registration, auth method "none"
    POST /oauth/device/code  form-encoded, with resource=<mcp agent url>
    POST /oauth/token        device_code grant, then refresh_token grant
    tokens rotate on refresh; the rotated refresh_token is persisted.
    Access tokens are short-lived (~15 min); refresh is transparent on
    expiry or 401.

Run:
    uv run tools/ax_presence.py auth
    uv run tools/ax_presence.py whoami
    uv run tools/ax_presence.py listen --dry-run
    uv run tools/ax_presence.py listen

Tests (pure functions only, no network):
    uv run --with pytest pytest tools/tests/test_ax_presence.py -v
httpx and the mcp SDK are lazy-imported so plain pytest can load this file.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AX_DIR = REPO_ROOT / "library" / ".ax"  # private: library/ is gitignored
TOKENS_PATH = AX_DIR / "tokens.json"
SESSIONS_PATH = AX_DIR / "sessions.json"

DEFAULT_AGENT = "second-arrow"
DEFAULT_BASE_URL = "https://paxai.app"
DEFAULT_GUIDE_URL = "http://127.0.0.1:8765/api/chat"
OAUTH_SCOPE = "openid offline_access ax-api/mcp:read ax-api/mcp:write"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
GUIDE_TIMEOUT = 600  # the claude brain can take a while on tool turns
POLL_TIMEOUT = 900  # seconds to wait for the human to approve the device code


class GuideError(Exception):
    """The local guide refused or failed a chat request."""


class SessionNotFound(GuideError):
    """The guide has never seen this session id (serve_shelf 404)."""


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[ax {stamp}] {message}", flush=True)


# --- token store (library/.ax/tokens.json, 0600) --------------------------


def save_tokens(path: Path, tokens: dict, now: float | None = None) -> dict:
    """Persist tokens with owner-only perms; derive expires_at once.

    expires_at (unix seconds) is computed from expires_in when the server
    didn't send one, so token_expired() needs no memory of when the grant
    happened.
    """
    stored = dict(tokens)
    if "expires_in" in stored and "expires_at" not in stored:
        stored["expires_at"] = int((time.time() if now is None else now) + stored["expires_in"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(stored, handle, indent=2)
    os.chmod(path, 0o600)  # a pre-existing looser file gets tightened too
    return stored


def load_tokens(path: Path) -> dict:
    """The stored tokens, or {} — missing/corrupt files are not fatal."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def token_expired(tokens: dict, now: float | None = None, skew: float = 60) -> bool:
    """Expired (or expiring within `skew` seconds). No expires_at means we
    trust the token and let a live 401 trigger the refresh instead."""
    if not tokens.get("access_token"):
        return True
    expires_at = tokens.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return False
    return (time.time() if now is None else now) + skew >= expires_at


def refresh_tokens(base_url: str, path: Path, post=None) -> dict:
    """Exchange the stored refresh_token for fresh tokens and persist them.

    aX rotates refresh tokens (single use), so the rotated token is saved
    immediately. `post(url, data) -> dict` is injectable for tests; the
    default does a real form-encoded POST.
    """
    tokens = load_tokens(path)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise GuideError("no refresh_token stored — run `ax_presence.py auth` again")
    if post is None:

        def post(url: str, data: dict) -> dict:  # pragma: no cover - network
            import httpx

            response = httpx.post(url, data=data, timeout=30)
            response.raise_for_status()
            return response.json()

    fresh = post(
        base_url.rstrip("/") + "/oauth/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": tokens.get("client_id", ""),
        },
    )
    merged = {**tokens, **fresh}
    if "expires_in" in fresh and "expires_at" not in fresh:
        merged.pop("expires_at", None)  # recompute from the new grant
    save_tokens(path, merged)
    return load_tokens(path)


# --- SSE parsing (shape-tolerant) ------------------------------------------


def sse_events(lines):
    """Parse an iterable of SSE lines into {"event", "data"} dicts.

    Follows the SSE framing rules we need: blank line dispatches, `:`
    lines are comments/keepalives, multiple data: lines join with \\n,
    a missing event: field means "message". Blocks without data are
    dropped (keepalive blocks look like that).
    """
    event_name, data_lines = "message", []
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        line = line.rstrip("\r\n").rstrip("\r")
        if not line:
            if data_lines:
                yield {"event": event_name, "data": "\n".join(data_lines)}
            event_name, data_lines = "message", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event_name = value or "message"
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield {"event": event_name, "data": "\n".join(data_lines)}


def decode_event_data(data: str) -> dict:
    """JSON-object data as a dict; anything else wrapped as {"text": raw}."""
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return {"text": data}
    return parsed if isinstance(parsed, dict) else {"text": data}


# --- mention extraction ------------------------------------------------------

HOUSEKEEPING_EVENTS = frozenset(
    {"connected", "keepalive", "ping", "heartbeat", "bootstrap", "open"}
)
_SENDER_KEYS = ("sender", "sender_name", "from", "author", "agent_name", "user")
_TEXT_KEYS = ("content", "text", "body", "message")
_ID_KEYS = ("message_id", "id", "msg_id")


def _handle(value) -> str | None:
    """A sender field as a plain handle: dicts unwrap to name-ish keys."""
    if isinstance(value, dict):
        for key in ("name", "handle", "username", "agent_name", "id"):
            if isinstance(value.get(key), str) and value[key]:
                return value[key]
        return None
    return value if isinstance(value, str) and value else None


def _same_agent(handle: str | None, agent: str) -> bool:
    return bool(handle) and handle.lstrip("@").lower() == agent.lstrip("@").lower()


def extract_mention(event_name: str, data: dict, agent: str) -> dict | None:
    """A mention aimed at `agent`, or None. Deliberately shape-tolerant.

    aX doesn't publish the exact event schema, so this accepts the shapes
    we consider plausible (flat fields, or the payload nested under
    "message"/"payload"; sender as a string or an author object) and the
    listener logs the raw shapes it actually sees. A message counts as a
    mention when the event/type says "mention", when mentioned_agent or a
    mentions list names us, or when @agent appears in the text. Our own
    messages and housekeeping events never count — the bridge only ever
    replies, it never initiates (privacy guard).
    """
    if event_name in HOUSEKEEPING_EVENTS:
        return None
    outer = data
    for key in ("message", "payload", "data"):
        inner = data.get(key)
        if isinstance(inner, dict):
            data = {**outer, **inner}
            break

    text = next(
        (data[k] for k in _TEXT_KEYS if isinstance(data.get(k), str) and data[k]), None
    )
    sender = next((h for h in (_handle(data.get(k)) for k in _SENDER_KEYS) if h), None)
    if not text or not sender or _same_agent(sender, agent):
        return None

    mentioned = (
        event_name == "mention"
        or outer.get("type") == "mention"
        or data.get("type") == "mention"
        or _same_agent(_handle(data.get("mentioned_agent")), agent)
        or any(
            _same_agent(_handle(m), agent)
            for m in data.get("mentions") or []
        )
        or f"@{agent.lstrip('@').lower()}" in text.lower()
    )
    if not mentioned:
        return None
    message_id = next(
        (data[k] for k in _ID_KEYS if isinstance(data.get(k), (str, int))), None
    )
    space_id = next(
        (data[k] for k in ("space_id", "space") if isinstance(data.get(k), (str, int))),
        None,
    )
    return {
        "sender": sender.lstrip("@"),
        "text": text,
        "message_id": message_id,
        "space_id": space_id,
    }


# --- guide prompt + per-sender sessions ---------------------------------------


def build_guide_prompt(sender: str, text: str) -> str:
    """Tell the guide which channel this is and who is asking."""
    return f"[aX message from @{sender.lstrip('@')}] {text}"


def session_key(sender: str) -> str:
    """A stable, serve_shelf-safe map key for one aX sender."""
    slug = re.sub(r"[^a-z0-9]+", "-", sender.lstrip("@").lower()).strip("-")
    return f"ax-{slug or 'agent'}"


# --- backoff -------------------------------------------------------------------


def backoff_delays(base: float = 1.0, cap: float = 60.0):
    """1, 2, 4, ... capped — the SSE reconnect schedule."""
    delay = base
    while True:
        yield min(delay, cap)
        delay = min(delay * 2, cap)


# --- reply extraction from the guide's streamed chat bytes ----------------------


def extract_reply(status: int, body: bytes) -> str:
    """The full reply text out of a (fully read) /api/chat response.

    serve_shelf streams raw text fragments on success and returns JSON
    {"error": ...} with a 4xx/5xx before the stream starts. 404 means the
    session id is unknown (SessionNotFound — the caller retries "new").
    """
    text = body.decode("utf-8", "replace")
    if status >= 400:
        try:
            message = json.loads(text).get("error") or text
        except json.JSONDecodeError:
            message = text.strip() or f"guide returned HTTP {status}"
        if status == 404:
            raise SessionNotFound(message)
        raise GuideError(message)
    if not text.strip():
        raise GuideError("the guide returned an empty reply")
    return text.strip()


# --- aX message-send tool discovery ---------------------------------------------

_MESSAGE_TOKENS = frozenset({"message", "messages", "msg"})
_SEND_TOKENS = frozenset({"send", "post", "reply", "create", "write"})
_CONTENT_KEYS = ("content", "text", "message", "body")
_REPLY_KEYS = (
    "reply_to",
    "reply_to_message_id",
    "in_reply_to",
    "thread_id",
    "parent_id",
    "message_id",
)
_SPACE_KEYS = ("space_id", "space")


def pick_send_tool(names: list[str]) -> str | None:
    """The aX tool that sends a chat message, out of a tools/list.

    aX doesn't document the name, so we discover it: a name qualifies
    when its tokens include both a message word and a send word
    (messages_send, send_message, post_message, messages.send, ...).
    """
    for name in names:
        tokens = set(re.split(r"[^a-z0-9]+", name.lower()))
        if tokens & _MESSAGE_TOKENS and tokens & _SEND_TOKENS:
            return name
    return None


def build_send_args(schema: dict, reply: str, mention: dict) -> dict:
    """Arguments for the discovered send tool, fitted to its inputSchema.

    The reply lands in the first content-ish property; the mention's
    message_id/space_id ride along when the schema has somewhere to put
    them. Raises ValueError when the schema has no content-ish property
    at all (then it isn't the send tool we thought it was).
    """
    properties = schema.get("properties") or {}
    content_key = next((k for k in _CONTENT_KEYS if k in properties), None)
    if content_key is None:
        raise ValueError(f"no content field in send-tool schema: {sorted(properties)}")
    args = {content_key: reply}
    if mention.get("message_id"):
        reply_key = next((k for k in _REPLY_KEYS if k in properties), None)
        if reply_key:
            args[reply_key] = mention["message_id"]
    if mention.get("space_id"):
        space_key = next((k for k in _SPACE_KEYS if k in properties), None)
        if space_key:
            args[space_key] = mention["space_id"]
    return args


# ================= runtime (network from here down; lazy imports) ==============


def check_library_ignored() -> None:
    """Tokens live under library/ — refuse to proceed if it isn't ignored."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "library/"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "library/ is not gitignored — refusing to store tokens there. "
            "Fix .gitignore first."
        )


def current_access_token(base_url: str, path: Path = TOKENS_PATH) -> str:
    """A live access token, refreshing transparently when it's stale."""
    tokens = load_tokens(path)
    if not tokens.get("access_token") and not tokens.get("refresh_token"):
        raise SystemExit("No aX tokens found — run `uv run tools/ax_presence.py auth` first.")
    if token_expired(tokens):
        log("access token expired — refreshing")
        tokens = refresh_tokens(base_url, path)
    return tokens["access_token"]


def load_json(path: Path) -> dict:
    return load_tokens(path)  # same tolerant reader


# --- auth -----------------------------------------------------------------------


def cmd_auth(args) -> int:
    import httpx

    check_library_ignored()
    base = args.base_url.rstrip("/")
    tokens = load_tokens(TOKENS_PATH)
    with httpx.Client(timeout=30) as client:
        client_id = tokens.get("client_id")
        if not client_id:
            log("registering OAuth client (dynamic registration)")
            response = client.post(
                base + "/oauth/register",
                json={
                    "client_name": f"{args.agent} MCP host",
                    "redirect_uris": [],
                    "grant_types": [DEVICE_GRANT, "refresh_token"],
                    "token_endpoint_auth_method": "none",
                    "scope": OAUTH_SCOPE,
                },
            )
            response.raise_for_status()
            client_id = response.json()["client_id"]
            tokens = save_tokens(TOKENS_PATH, {**tokens, "client_id": client_id})
            log(f"client registered: {client_id}")
        else:
            log(f"reusing registered client: {client_id}")

        response = client.post(
            base + "/oauth/device/code",
            data={
                "client_id": client_id,
                "resource": f"{base}/mcp/agents/{args.agent}",
                "scope": OAUTH_SCOPE,
            },
        )
        response.raise_for_status()
        device = response.json()
        url = device.get("verification_uri_complete") or device.get("verification_uri")
        print()
        print("=" * 64)
        print("  APPROVE THIS AGENT — open the link as the sponsoring human:")
        print(f"  >>> {url}")
        print(f"  user code: {device.get('user_code')}")
        print("=" * 64)
        print()

        interval = int(device.get("interval") or 5)
        deadline = time.time() + args.poll_timeout
        while time.time() < deadline:
            time.sleep(interval)
            response = client.post(
                base + "/oauth/token",
                data={
                    "grant_type": DEVICE_GRANT,
                    "device_code": device["device_code"],
                    "client_id": client_id,
                },
            )
            try:
                body = response.json()
            except json.JSONDecodeError:
                body = {}
            if response.status_code == 200 and body.get("access_token"):
                save_tokens(TOKENS_PATH, {**tokens, **body})
                log(f"authorized — tokens saved to {TOKENS_PATH}")
                return 0
            error = body.get("error", f"http {response.status_code}")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            log(f"device flow failed: {error} {body.get('error_description', '')}")
            return 1
    log(f"gave up after {args.poll_timeout}s — approval never arrived. Re-run auth.")
    return 1


# --- MCP plumbing ------------------------------------------------------------


async def _mcp_session(base_url: str, agent: str, token: str, work):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = f"{base_url.rstrip('/')}/mcp/agents/{agent}"
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            return await work(session, init)


def _looks_like_auth_failure(error: BaseException) -> bool:
    text = repr(error)
    if isinstance(error, BaseExceptionGroup):  # anyio task groups wrap the cause
        text += " ".join(repr(e) for e in error.exceptions)
    return "401" in text or "Unauthorized" in text or "unauthorized" in text


def run_mcp(base_url: str, agent: str, work):
    """asyncio.run an MCP call, refreshing tokens once on a 401-ish failure."""
    import asyncio

    token = current_access_token(base_url)
    try:
        return asyncio.run(_mcp_session(base_url, agent, token, work))
    except BaseException as error:  # noqa: BLE001 — inspect, refresh, retry once
        if isinstance(error, KeyboardInterrupt) or not _looks_like_auth_failure(error):
            raise
        log("aX MCP call got a 401 — refreshing token and retrying once")
        tokens = refresh_tokens(base_url, TOKENS_PATH)
        return asyncio.run(_mcp_session(base_url, agent, tokens["access_token"], work))


def cmd_whoami(args) -> int:
    async def work(session, init):
        server = getattr(init, "serverInfo", None)
        if server:
            print(f"server: {getattr(server, 'name', '?')} {getattr(server, 'version', '')}")
        listing = await session.list_tools()
        names = [tool.name for tool in listing.tools]
        print(f"agent endpoint: {args.base_url.rstrip('/')}/mcp/agents/{args.agent}")
        print(f"tools ({len(names)}):")
        for tool in listing.tools:
            summary = (tool.description or "").strip().splitlines()
            print(f"  - {tool.name}" + (f": {summary[0][:90]}" if summary else ""))
        send_tool = pick_send_tool(names)
        print(f"message-send tool (discovered): {send_tool or 'NOT FOUND'}")
        whoami = next((n for n in names if "whoami" in n.lower()), None)
        if whoami:
            result = await session.call_tool(whoami, {})
            for block in result.content:
                if getattr(block, "type", "") == "text":
                    print(f"whoami: {block.text}")
        return 0

    return run_mcp(args.base_url, args.agent, work)


# --- the guide (local serve_shelf) -----------------------------------------


def ask_guide(
    guide_url: str, prompt: str, session: str | None, brain: str | None = None
) -> tuple[str, str | None]:
    """One question to the local guide; returns (full reply, session id).

    The reply streams as raw text chunks; we read it to the end. `session`
    None means "new" — never the bare default, which would hijack the
    user's own current shelf conversation.
    """
    import httpx

    body: dict = {
        "messages": [{"role": "user", "content": prompt}],
        "session": session or "new",
    }
    if brain:
        body["brain"] = brain
    timeout = httpx.Timeout(30.0, read=GUIDE_TIMEOUT)
    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", guide_url, json=body) as response:
            raw = response.read()
            return extract_reply(response.status_code, raw), response.headers.get(
                "X-Session"
            )


def guide_reply_for(mention: dict, guide_url: str, brain: str | None) -> str:
    """Route one mention through the guide, keeping a per-sender session."""
    prompt = build_guide_prompt(mention["sender"], mention["text"])
    sessions = load_json(SESSIONS_PATH)
    key = session_key(mention["sender"])
    known = sessions.get(key)
    try:
        reply, sid = ask_guide(guide_url, prompt, known, brain)
    except SessionNotFound:
        log(f"guide forgot session {known!r} — starting a fresh one for {key}")
        reply, sid = ask_guide(guide_url, prompt, None, brain)
    if sid and sid != known:
        sessions[key] = sid
        save_tokens(SESSIONS_PATH, sessions)  # same 0600 JSON writer
        log(f"session for @{mention['sender']}: {sid}")
    return reply


# --- listen -------------------------------------------------------------------


def send_ax_reply(args, reply: str, mention: dict) -> None:
    async def work(session, _init):
        listing = await session.list_tools()
        names = [tool.name for tool in listing.tools]
        tool_name = pick_send_tool(names)
        if not tool_name:
            log(f"NO message-send tool found — aX tools were: {names}")
            return
        tool = next(t for t in listing.tools if t.name == tool_name)
        send_args = build_send_args(tool.inputSchema or {}, reply, mention)
        log(f"sending via {tool_name} (args: {sorted(send_args)})")
        result = await session.call_tool(tool_name, send_args)
        if getattr(result, "isError", False):
            log(f"aX send reported an error: {result.content}")
        else:
            log("reply delivered to aX")

    run_mcp(args.base_url, args.agent, work)


def handle_mention(args, mention: dict) -> None:
    log(
        f"mention from @{mention['sender']}"
        + (f" (msg {mention['message_id']})" if mention.get("message_id") else "")
        + f": {mention['text'][:120]!r}"
    )
    try:
        reply = guide_reply_for(mention, args.guide_url, args.brain)
    except GuideError as error:
        log(f"guide error — not replying: {error}")
        return
    except OSError as error:
        log(f"guide unreachable at {args.guide_url} — not replying: {error}")
        return
    if args.dry_run:
        log(f"[dry-run] WOULD reply to @{mention['sender']}: {reply[:300]!r}")
        return
    try:
        send_ax_reply(args, reply, mention)
    except Exception as error:  # noqa: BLE001 — one failed send must not kill the loop
        log(f"failed to deliver reply to aX: {error!r}")


def cmd_listen(args) -> int:
    import httpx

    check_library_ignored()
    base = args.base_url.rstrip("/")
    sse_url = base + "/api/sse/messages"
    log(f"agent @{args.agent} listening on {sse_url}")
    log(f"guide at {args.guide_url}" + (" [dry-run]" if args.dry_run else ""))
    log("privacy: replies to explicit mentions only; nothing is sent proactively")
    delays = backoff_delays()
    try:
        while True:
            try:
                token = current_access_token(base)
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "text/event-stream",
                }
                timeout = httpx.Timeout(30.0, read=None)  # SSE reads block forever
                with httpx.Client(timeout=timeout) as client:
                    with client.stream("GET", sse_url, headers=headers) as response:
                        if response.status_code == 401:
                            log("SSE got 401 — refreshing token")
                            refresh_tokens(base, TOKENS_PATH)
                            continue
                        if response.status_code >= 400:
                            log(f"SSE connect failed: HTTP {response.status_code}")
                            raise httpx.HTTPStatusError(
                                "sse", request=response.request, response=response
                            )
                        log("SSE connected — waiting for mentions")
                        delays = backoff_delays()  # healthy again: reset backoff
                        for event in sse_events(response.iter_lines()):
                            data = decode_event_data(event["data"])
                            log(
                                f"event {event['event']!r} "
                                f"keys={sorted(data)} "  # log real shapes we see
                                f"type={data.get('type')!r}"
                            )
                            mention = extract_mention(event["event"], data, args.agent)
                            if mention:
                                handle_mention(args, mention)
                log("SSE stream ended")
            except (httpx.HTTPError, OSError, GuideError) as error:
                log(f"SSE connection problem: {error!r}")
            delay = next(delays)
            log(f"reconnecting in {delay:.0f}s")
            time.sleep(delay)
    except KeyboardInterrupt:
        print()
        log("stopped (Ctrl-C) — goodbye")
        return 0


# --- CLI -----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge the Second Arrow guide onto the aX agent network."
    )
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="aX agent name")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="aX base URL")
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="device-code OAuth (one-time, human approves)")
    auth.add_argument(
        "--poll-timeout",
        type=int,
        default=POLL_TIMEOUT,
        help="seconds to wait for the human to approve",
    )

    sub.add_parser("whoami", help="validate the token; list the aX MCP tools")

    listen = sub.add_parser("listen", help="answer aX mentions via the local guide")
    listen.add_argument("--guide-url", default=DEFAULT_GUIDE_URL)
    listen.add_argument("--brain", default=None, help="forwarded to /api/chat (claude|ollama)")
    listen.add_argument(
        "--dry-run",
        action="store_true",
        help="log events and intended replies without posting to aX",
    )

    args = parser.parse_args()
    command = {"auth": cmd_auth, "whoami": cmd_whoami, "listen": cmd_listen}[args.command]
    try:
        return command(args)
    except KeyboardInterrupt:
        print()
        log("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
