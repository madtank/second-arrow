"""Tests for the pure functions in tools/ax_presence.py — no network.

Covers: the token store (round-trip, 0600 perms, expiry math, refresh
merge), the shape-tolerant SSE/mention parsing, the guide-prompt prefix,
the reconnect backoff sequence, reply extraction from streamed chat
bytes, and the aX message-send tool discovery heuristics.
"""

import importlib.util
import json
import stat
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ax_presence.py"
SPEC = importlib.util.spec_from_file_location("ax_presence", MODULE_PATH)
ax = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(ax)


# --- token store ----------------------------------------------------------


def test_tokens_round_trip_and_0600(tmp_path):
    path = tmp_path / ".ax" / "tokens.json"
    tokens = {"access_token": "abc", "refresh_token": "def", "client_id": "cid"}
    ax.save_tokens(path, tokens)
    assert ax.load_tokens(path) == tokens
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_save_tokens_computes_expires_at(tmp_path):
    path = tmp_path / "tokens.json"
    ax.save_tokens(path, {"access_token": "a", "expires_in": 900}, now=1000.0)
    stored = ax.load_tokens(path)
    assert stored["expires_at"] == 1900


def test_save_tokens_keeps_explicit_expires_at(tmp_path):
    path = tmp_path / "tokens.json"
    ax.save_tokens(
        path, {"access_token": "a", "expires_in": 900, "expires_at": 42}, now=1000.0
    )
    assert ax.load_tokens(path)["expires_at"] == 42


def test_load_tokens_missing_or_corrupt(tmp_path):
    assert ax.load_tokens(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert ax.load_tokens(bad) == {}


def test_token_expired():
    assert ax.token_expired({}, now=100)  # no token at all
    assert ax.token_expired({"access_token": "a", "expires_at": 90}, now=100)
    # inside the skew window counts as expired
    assert ax.token_expired({"access_token": "a", "expires_at": 130}, now=100, skew=60)
    assert not ax.token_expired({"access_token": "a", "expires_at": 500}, now=100, skew=60)
    # no expires_at: trust the token, let a 401 trigger the refresh
    assert not ax.token_expired({"access_token": "a"}, now=100)


def test_refresh_merge_rotates_and_persists(tmp_path):
    path = tmp_path / "tokens.json"
    ax.save_tokens(
        path,
        {"access_token": "old", "refresh_token": "r1", "client_id": "cid"},
    )

    calls = {}

    def fake_post(url, data):
        calls["url"] = url
        calls["data"] = data
        return {"access_token": "new", "refresh_token": "r2", "expires_in": 900}

    tokens = ax.refresh_tokens("https://paxai.app", path, post=fake_post)
    assert calls["url"] == "https://paxai.app/oauth/token"
    assert calls["data"]["grant_type"] == "refresh_token"
    assert calls["data"]["refresh_token"] == "r1"
    assert calls["data"]["client_id"] == "cid"
    stored = ax.load_tokens(path)
    assert stored["access_token"] == "new"
    assert stored["refresh_token"] == "r2"  # rotated token persisted
    assert stored["client_id"] == "cid"  # merge keeps registration
    assert tokens == stored


# --- SSE parsing ----------------------------------------------------------


def test_sse_events_basic_dispatch():
    lines = [
        ": keepalive comment",
        "event: mention",
        'data: {"sender": "alice"}',
        "",
        'data: {"plain": true}',
        "",
    ]
    events = list(ax.sse_events(lines))
    assert events == [
        {"event": "mention", "data": '{"sender": "alice"}'},
        {"event": "message", "data": '{"plain": true}'},
    ]


def test_sse_events_multiline_data_and_crlf():
    lines = ["event: message\r", "data: line one", "data: line two", "", ""]
    events = list(ax.sse_events(lines))
    assert events == [{"event": "message", "data": "line one\nline two"}]


def test_sse_events_ignores_empty_and_comment_only_blocks():
    assert list(ax.sse_events([": ping", "", "", ": ping", ""])) == []


def test_decode_event_data_json_and_raw():
    assert ax.decode_event_data('{"a": 1}') == {"a": 1}
    assert ax.decode_event_data("not json") == {"text": "not json"}
    assert ax.decode_event_data('["list"]') == {"text": '["list"]'}


# --- mention extraction (shape-tolerant) ------------------------------------


AGENT = "second-arrow"


def test_mention_flat_shape():
    data = {"sender": "alice", "content": "hi @second-arrow, what is metta?", "id": "m1"}
    got = ax.extract_mention("mention", data, AGENT)
    assert got["sender"] == "alice"
    assert got["text"] == "hi @second-arrow, what is metta?"
    assert got["message_id"] == "m1"


def test_mention_nested_message_shape():
    data = {
        "type": "mention",
        "space_id": "s1",
        "message": {
            "message_id": "m2",
            "author": {"name": "bob"},
            "body": "@second-arrow ping",
        },
    }
    got = ax.extract_mention("message", data, AGENT)
    assert got == {
        "sender": "bob",
        "text": "@second-arrow ping",
        "message_id": "m2",
        "space_id": "s1",
    }


def test_mention_via_mentioned_agent_field():
    data = {"from": "carol", "text": "no at-sign here", "mentioned_agent": "second-arrow"}
    got = ax.extract_mention("message", data, AGENT)
    assert got["sender"] == "carol"
    assert got["text"] == "no at-sign here"


def test_mention_via_mentions_list():
    data = {"sender": "dave", "content": "hey", "mentions": ["@second-arrow", "@other"]}
    assert ax.extract_mention("message", data, AGENT)["sender"] == "dave"


def test_plain_message_not_mentioning_us_is_ignored():
    data = {"sender": "alice", "content": "talking to @someone-else"}
    assert ax.extract_mention("message", data, AGENT) is None


def test_mention_event_type_is_trusted_without_at_sign():
    data = {"sender": "alice", "content": "just a question"}
    assert ax.extract_mention("mention", data, AGENT) is not None


def test_own_messages_are_ignored():
    data = {"sender": "second-arrow", "content": "@second-arrow echo"}
    assert ax.extract_mention("mention", data, AGENT) is None
    data = {"sender": "@second-arrow", "content": "@second-arrow echo"}
    assert ax.extract_mention("mention", data, AGENT) is None


def test_housekeeping_events_are_ignored():
    # connected/bootstrap/identity_bootstrap/ping are the shapes observed
    # live on paxai.app; bootstrap carries historical posts and MUST be
    # ignored or reconnects would replay old conversations.
    for name in ("connected", "keepalive", "ping", "heartbeat", "bootstrap", "identity_bootstrap"):
        assert ax.extract_mention(name, {"sender": "x", "content": "@second-arrow"}, AGENT) is None


def test_mention_without_text_or_sender_is_ignored():
    assert ax.extract_mention("mention", {"sender": "alice"}, AGENT) is None
    assert ax.extract_mention("mention", {"content": "@second-arrow hi"}, AGENT) is None


# --- guide prompt + sessions -------------------------------------------------


def test_build_guide_prompt():
    assert (
        ax.build_guide_prompt("alice", "what is the second arrow?")
        == "[aX message from @alice] what is the second arrow?"
    )
    # a leading @ on the sender is not doubled
    assert ax.build_guide_prompt("@bob", "hi").startswith("[aX message from @bob] ")


def test_session_key_is_safe_and_stable():
    assert ax.session_key("alice") == "ax-alice"
    assert ax.session_key("@Alice") == "ax-alice"
    assert ax.session_key("weird name!!") == "ax-weird-name"
    # never empty, never dot-leading (serve_shelf's SESSION_ID_RE)
    assert ax.session_key("...") == "ax-agent"


# --- backoff -----------------------------------------------------------------


def test_backoff_sequence_doubles_to_cap():
    gen = ax.backoff_delays(base=1, cap=60)
    assert [next(gen) for _ in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]


# --- reply extraction from streamed chat bytes -------------------------------


def test_extract_reply_plain_stream():
    body = "The second arrow is the one ".encode() + "we shoot ourselves.".encode()
    assert (
        ax.extract_reply(200, body)
        == "The second arrow is the one we shoot ourselves."
    )


def test_extract_reply_error_json():
    body = json.dumps({"error": "Unknown brain 'x'"}).encode()
    with pytest.raises(ax.GuideError) as err:
        ax.extract_reply(400, body)
    assert "Unknown brain" in str(err.value)


def test_extract_reply_error_non_json():
    with pytest.raises(ax.GuideError):
        ax.extract_reply(500, b"Internal Server Error")


def test_extract_reply_empty_stream_raises():
    with pytest.raises(ax.GuideError):
        ax.extract_reply(200, b"   ")


def test_extract_reply_session_not_found_is_distinct():
    body = json.dumps({"error": "no session 'ax-alice'"}).encode()
    with pytest.raises(ax.SessionNotFound):
        ax.extract_reply(404, body)


# --- aX message-send tool discovery ------------------------------------------

# Trimmed from the REAL inputSchema of the consolidated `messages` tool on
# "aX Platform MCP v3 3.3.1" (tools/list, observed live 2026-07). Sending
# lives behind the action discriminator; message_id targets edit/delete,
# reply_to is the threading field.
AX_V3_MESSAGES_SCHEMA = {
    "additionalProperties": False,
    "type": "object",
    "required": ["action"],
    "properties": {
        "action": {
            "type": "string",
            "enum": ["check", "send", "ask_ax", "draft", "react", "edit", "delete"],
        },
        "content": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        "message_id": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        "reply_to": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        "limit": {"type": "integer", "default": 10},
        "wait": {"type": "boolean", "default": False},
        "bypass": {"type": "boolean", "default": False},
        "reason": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
    },
}

AX_V3_TOOL_NAMES = ["whoami", "messages", "tasks", "agents", "spaces", "context", "search"]


def test_pick_send_tool_prefers_consolidated_messages_tool():
    # the live aX v3 surface: send lives inside `messages`
    assert ax.pick_send_tool(AX_V3_TOOL_NAMES) == "messages"
    # exact match wins even when a legacy-shaped name is also present
    assert ax.pick_send_tool(["messages_send", "messages"]) == "messages"


def test_build_send_args_consolidated_v3_reply():
    mention = {"sender": "alice", "message_id": "m1", "space_id": "s1", "text": "hi"}
    args = ax.build_send_args(AX_V3_MESSAGES_SCHEMA, "the reply", mention)
    # action=send + content, threaded via reply_to; nothing else sprayed in
    assert args == {"action": "send", "content": "the reply", "reply_to": "m1"}


def test_build_send_args_consolidated_v3_without_message_id():
    args = ax.build_send_args(AX_V3_MESSAGES_SCHEMA, "hello", {"sender": "bob"})
    assert args == {"action": "send", "content": "hello"}


def test_pick_send_tool_prefers_message_send_names():
    assert ax.pick_send_tool(["whoami", "messages_send", "tasks_create"]) == "messages_send"
    assert ax.pick_send_tool(["send_message"]) == "send_message"
    assert ax.pick_send_tool(["messages.send", "whoami"]) == "messages.send"
    assert ax.pick_send_tool(["post_message", "whoami"]) == "post_message"


def test_pick_send_tool_avoids_non_message_tools():
    assert ax.pick_send_tool(["tasks_create", "whoami", "search"]) is None
    assert ax.pick_send_tool([]) is None
    # a task-send is not a message-send
    assert ax.pick_send_tool(["send_task"]) is None


def test_build_send_args_maps_content_and_reply_fields():
    schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "reply_to": {"type": "string"},
            "space_id": {"type": "string"},
        },
    }
    mention = {"sender": "alice", "message_id": "m1", "space_id": "s1", "text": "hi"}
    args = ax.build_send_args(schema, "the reply", mention)
    assert args == {"content": "the reply", "reply_to": "m1", "space_id": "s1"}


def test_build_send_args_alternate_field_names():
    schema = {"properties": {"text": {"type": "string"}, "thread_id": {}}}
    args = ax.build_send_args(schema, "r", {"message_id": "m9"})
    assert args == {"text": "r", "thread_id": "m9"}


def test_build_send_args_no_content_field_raises():
    with pytest.raises(ValueError):
        ax.build_send_args({"properties": {"count": {}}}, "r", {})


def test_build_send_args_omits_missing_mention_fields():
    schema = {"properties": {"message": {"type": "string"}, "reply_to": {}}}
    assert ax.build_send_args(schema, "r", {}) == {"message": "r"}
