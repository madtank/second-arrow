import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "serve_shelf.py"
SPEC = importlib.util.spec_from_file_location("serve_shelf", MODULE_PATH)
serve_shelf = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(serve_shelf)

DEMON_TEXT = (
    "There was once an anger eating demon who came to the palace. "
    "The demon grows bigger and uglier on anger and angry words, "
    "and shrinks away on kindness and gentle speech. "
) * 30

PATIENCE_TEXT = (
    "Patience is not grim endurance. You do not wear the burden all the time. "
    "The carpenter checks the adze handle and sees the wearing away slowly. "
) * 30

TRANSCRIPTS = {
    "Anger Eating Demons": DEMON_TEXT,
    "Patience": PATIENCE_TEXT,
}


# --- chunk_transcript ---------------------------------------------------


def test_chunk_transcript_sizes_and_no_empty_chunks():
    chunks = serve_shelf.chunk_transcript(DEMON_TEXT, size=1200)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    # Chunks stay near the target size (words are never split).
    assert all(len(chunk) <= 1200 + 80 for chunk in chunks)
    # Nothing is lost.
    assert " ".join(chunks).split() == DEMON_TEXT.split()


def test_chunk_transcript_short_text_is_one_chunk():
    assert serve_shelf.chunk_transcript("a few small words", size=1200) == [
        "a few small words"
    ]


def test_chunk_transcript_empty_text_gives_no_chunks():
    assert serve_shelf.chunk_transcript("", size=1200) == []


# --- pick_chunks --------------------------------------------------------


def test_pick_chunks_ranks_the_right_talk_first():
    picked = serve_shelf.pick_chunks(
        "What does the anger eating demon grow on?", TRANSCRIPTS, k=4
    )
    assert picked, "expected at least one retrieved chunk"
    title, chunk = picked[0]
    assert title == "Anger Eating Demons"
    assert "demon" in chunk


def test_pick_chunks_respects_k():
    picked = serve_shelf.pick_chunks("anger demon kindness", TRANSCRIPTS, k=2)
    assert len(picked) <= 2
    picked = serve_shelf.pick_chunks("anger demon kindness", TRANSCRIPTS, k=1)
    assert len(picked) == 1


def test_pick_chunks_no_overlap_returns_empty():
    picked = serve_shelf.pick_chunks("quantum blockchain synergy", TRANSCRIPTS, k=4)
    assert picked == []


# --- build_ollama_payload -----------------------------------------------


def test_build_ollama_payload_grounds_the_system_prompt():
    messages = [
        {"role": "user", "content": "hello guide"},
        {"role": "assistant", "content": "hello friend"},
        {"role": "user", "content": "what does the demon grow on?"},
    ]
    chunks = [("Anger Eating Demons", "the demon grows on anger and angry words")]
    payload = serve_shelf.build_ollama_payload(
        messages,
        model="qwen3",
        study="## Studied\n- Patience",
        index="## anger-eating-demons",
        chunks=chunks,
    )
    assert payload["model"] == "qwen3"
    assert payload["stream"] is False
    system = payload["messages"][0]
    assert system["role"] == "system"
    # Persona marker, memory, index, and the retrieved chunk all present.
    assert "guide" in system["content"].lower()
    assert "not scripture, therapy, or medical advice" in system["content"]
    assert "## Studied" in system["content"]
    assert "## anger-eating-demons" in system["content"]
    assert "the demon grows on anger and angry words" in system["content"]
    assert "Anger Eating Demons" in system["content"]
    # User/assistant messages preserved, in order, after the system message.
    assert payload["messages"][1:] == messages


# --- build_claude_cmd ---------------------------------------------------


def test_build_claude_cmd_first_turn_streams_with_scoped_writes():
    cmd = serve_shelf.build_claude_cmd("where am I?")
    assert cmd[:3] == ["claude", "-p", "where am I?"]
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd
    assert "--include-partial-messages" in cmd
    # A global defaultMode like "auto" would auto-accept every write; the
    # chat brain pins "default" so only the explicit allowlist passes.
    assert cmd[cmd.index("--permission-mode") + 1] == "default"
    assert cmd[cmd.index("--allowedTools") + 1] == serve_shelf.chat_allowed_tools()
    assert "--resume" not in cmd


def test_build_claude_cmd_resume_turn():
    cmd = serve_shelf.build_claude_cmd("and then?", session_id="abc-123")
    assert cmd[-2:] == ["--resume", "abc-123"]
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"


def test_chat_allowed_tools_covers_memory_scopes_and_reviewed_tools_only():
    rules = serve_shelf.chat_allowed_tools().split(",")
    write_scopes = (
        "STUDY.md",
        "journal/**",
        "library/**/notes.md",
        "library/INDEX.md",
        "library/**/artifacts/*.html",  # self-contained interactive pages
    )
    expected = {f"{tool}({scope})" for scope in write_scopes for tool in ("Edit", "Write")}
    expected |= {
        "Bash(uv run tools/fetch_talk.py:*)",
        "Bash(uv run tools/speak.py:*)",
        "Bash(uv run tools/build_shelf.py:*)",
        "Bash(uv run tools/search_history.py:*)",
        "Bash(uv run tools/update_session_summary.py:*)",
        "WebSearch",  # read-only: current-world questions (teacher news, links)
        "WebFetch",
    }
    assert set(rules) == expected
    assert len(rules) == len(expected)  # no stray rules
    # No general Bash: every Bash rule is pinned to a reviewed tool command.
    for rule in rules:
        assert rule.split("(")[0] in ("Edit", "Write", "Bash", "WebSearch", "WebFetch")
        if rule.startswith("Bash("):
            assert rule.startswith("Bash(uv run tools/")
            assert rule.endswith(":*)")


# --- trim_history -------------------------------------------------------


def test_trim_history_caps_turns():
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
        for i in range(30)
    ]
    trimmed = serve_shelf.trim_history(messages, max_messages=12)
    assert len(trimmed) == 12
    assert trimmed == messages[-12:]


def test_trim_history_short_history_untouched():
    messages = [{"role": "user", "content": "hi"}]
    assert serve_shelf.trim_history(messages, max_messages=12) == messages


# --- small helpers ------------------------------------------------------


def test_history_prompt_folds_earlier_turns():
    messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
    ]
    prompt = serve_shelf.history_prompt(messages)
    assert "first question" in prompt
    assert "first answer" in prompt
    assert prompt.rstrip().endswith("second question")
    # A single first turn is passed through untouched.
    assert serve_shelf.history_prompt(messages[:1]) == "first question"


def test_parse_claude_output_single_result_object():
    stdout = '{"type": "result", "result": " hi ", "session_id": "s-1"}'
    assert serve_shelf.parse_claude_output(stdout) == ("hi", "s-1")


def test_parse_claude_output_event_list():
    stdout = (
        '[{"type": "system", "session_id": "s-2"},'
        ' {"type": "assistant", "message": {}},'
        ' {"type": "result", "is_error": false, "result": "grows on anger",'
        '  "session_id": "s-2"}]'
    )
    assert serve_shelf.parse_claude_output(stdout) == ("grows on anger", "s-2")


def test_parse_claude_output_error_result_raises():
    import pytest

    with pytest.raises(ValueError):
        serve_shelf.parse_claude_output(
            '{"type": "result", "is_error": true, "result": "boom"}'
        )


def test_strip_think_removes_reasoning_block():
    raw = "<think>let me ponder\nanger...</think>\nIt grows on anger."
    assert serve_shelf.strip_think(raw) == "It grows on anger."
    assert serve_shelf.strip_think("plain reply") == "plain reply"


def test_build_ollama_payload_can_ask_for_streaming():
    payload = serve_shelf.build_ollama_payload(
        [{"role": "user", "content": "hi"}], model="qwen3", stream=True
    )
    assert payload["stream"] is True


# --- parse_stream_line (claude --output-format stream-json) --------------
# Shapes below are captured from a real `claude -p --output-format
# stream-json --verbose --include-partial-messages` run.


def test_parse_stream_line_text_delta():
    line = json.dumps(
        {
            "type": "stream_event",
            "session_id": "57d69c96",
            "event": {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "text_delta", "text": "hello there "},
            },
        }
    )
    assert serve_shelf.parse_stream_line(line) == {
        "text": "hello there ",
        "session_id": "57d69c96",
        "done": False,
        "tools": [],
    }


def test_parse_stream_line_ignores_thinking_and_signature_deltas():
    for delta in (
        {"type": "thinking_delta", "thinking": "let me ponder"},
        {"type": "signature_delta", "signature": "CAIS..."},
    ):
        line = json.dumps(
            {
                "type": "stream_event",
                "session_id": "s-1",
                "event": {"type": "content_block_delta", "index": 0, "delta": delta},
            }
        )
        parsed = serve_shelf.parse_stream_line(line)
        assert parsed["text"] is None
        assert parsed["done"] is False


def test_parse_stream_line_init_event_carries_session_id():
    line = json.dumps(
        {"type": "system", "subtype": "init", "session_id": "s-9", "tools": ["Edit"]}
    )
    assert serve_shelf.parse_stream_line(line) == {
        "text": None,
        "session_id": "s-9",
        "done": False,
        "tools": [],
    }


def test_parse_stream_line_result_event_is_done():
    line = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "hello there friend",
            "session_id": "s-9",
        }
    )
    assert serve_shelf.parse_stream_line(line) == {
        "text": None,
        "session_id": "s-9",
        "done": True,
        "tools": [],
    }


def test_parse_stream_line_error_result_raises():
    line = json.dumps({"type": "result", "is_error": True, "result": "boom"})
    with pytest.raises(ValueError, match="boom"):
        serve_shelf.parse_stream_line(line)


def test_parse_stream_line_blank_line_is_inert():
    assert serve_shelf.parse_stream_line("  \n") == {
        "text": None,
        "session_id": None,
        "done": False,
        "tools": [],
    }


def test_parse_stream_line_garbage_raises_json_error():
    with pytest.raises(json.JSONDecodeError):
        serve_shelf.parse_stream_line("not json at all")


# --- parse_ollama_stream_line ---------------------------------------------


def test_parse_ollama_stream_line_content_chunk():
    line = json.dumps(
        {"model": "qwen3", "message": {"role": "assistant", "content": "gro"}, "done": False}
    )
    assert serve_shelf.parse_ollama_stream_line(line) == {
        "text": "gro", "done": False, "tool_calls": [],
    }


def test_parse_ollama_stream_line_final_chunk_is_done():
    line = json.dumps(
        {"model": "qwen3", "message": {"role": "assistant", "content": ""}, "done": True}
    )
    assert serve_shelf.parse_ollama_stream_line(line) == {
        "text": None, "done": True, "tool_calls": [],
    }


def test_parse_ollama_stream_line_carries_tool_calls():
    # Shape captured from a real streamed gemma4:12b round: the tool call
    # arrives whole in one chunk, content empty.
    calls = [{"id": "call_adu330iq", "function": {"index": 0, "name": "rebuild_shelf", "arguments": {}}}]
    line = json.dumps({"message": {"role": "assistant", "content": "", "tool_calls": calls}, "done": False})
    assert serve_shelf.parse_ollama_stream_line(line) == {
        "text": None, "done": False, "tool_calls": calls,
    }


def test_parse_ollama_stream_line_error_raises():
    with pytest.raises(ValueError, match="model not found"):
        serve_shelf.parse_ollama_stream_line(json.dumps({"error": "model not found"}))


def test_parse_ollama_stream_line_blank_is_inert():
    assert serve_shelf.parse_ollama_stream_line("\n") == {
        "text": None, "done": False, "tool_calls": [],
    }


# --- ThinkFilter (streaming strip_think) ----------------------------------


def test_think_filter_passes_plain_text_through():
    think = serve_shelf.ThinkFilter()
    assert think.feed("It grows ") == "It grows "
    assert think.feed("on anger.") == "on anger."
    assert think.flush() == ""


def test_think_filter_drops_block_within_one_chunk():
    think = serve_shelf.ThinkFilter()
    out = think.feed("<think>ponder ponder</think>\n\nIt grows on anger.")
    assert out + think.flush() == "It grows on anger."


def test_think_filter_drops_block_split_across_chunks():
    think = serve_shelf.ThinkFilter()
    pieces = ["<thi", "nk>let me ", "ponder</th", "ink>\nIt grows", " on anger."]
    out = "".join(think.feed(piece) for piece in pieces) + think.flush()
    assert out == "It grows on anger."


def test_think_filter_flush_releases_a_held_false_alarm():
    think = serve_shelf.ThinkFilter()
    # "<" could be the start of "<think>", so it is held back...
    assert think.feed("2 <") == "2 "
    # ...and released once the stream ends without completing the tag.
    assert think.flush() == "<"


def test_think_filter_unclosed_think_yields_nothing():
    think = serve_shelf.ThinkFilter()
    assert think.feed("<think>still pondering") == ""
    assert think.flush() == ""


# --- resolve_brain (per-request brain switch) -----------------------------


def test_resolve_brain_falls_back_to_default_when_unrequested():
    available = {"claude": True, "ollama": True}
    assert serve_shelf.resolve_brain(None, "claude", available) == "claude"
    assert serve_shelf.resolve_brain("", "ollama", available) == "ollama"


def test_resolve_brain_honours_an_available_request():
    available = {"claude": True, "ollama": True}
    assert serve_shelf.resolve_brain("ollama", "claude", available) == "ollama"
    assert serve_shelf.resolve_brain("claude", "ollama", available) == "claude"


def test_resolve_brain_unknown_name_is_a_400():
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_brain("gpt", "claude", {"claude": True, "ollama": True})
    assert excinfo.value.status == 400
    assert "gpt" in excinfo.value.message


def test_resolve_brain_unavailable_request_is_a_503_with_a_hint():
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_brain("ollama", "claude", {"claude": True, "ollama": False})
    assert excinfo.value.status == 503
    assert "ollama serve" in excinfo.value.message
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_brain("claude", "ollama", {"claude": False, "ollama": True})
    assert excinfo.value.status == 503


def test_resolve_brain_default_skips_the_availability_gate():
    # The server default is not second-guessed: probes can be stale, and
    # the brain itself reports a proper error if it is really down.
    available = {"claude": True, "ollama": False}
    assert serve_shelf.resolve_brain(None, "ollama", available) == "ollama"


# --- resolve_default_brain (hermes is the home harness) ---------------------


def test_resolve_default_brain_seats_hermes_when_wired():
    # The home harness takes the default seat whenever the gate is open.
    assert serve_shelf.resolve_default_brain("claude", True) == "hermes"
    assert serve_shelf.resolve_default_brain("hermes", True) == "hermes"


def test_resolve_default_brain_unwired_falls_back_to_claude():
    assert serve_shelf.resolve_default_brain("claude", False) == "claude"
    assert serve_shelf.resolve_default_brain("hermes", False) == "claude"


def test_resolve_default_brain_an_explicit_ollama_choice_stands():
    # --brain ollama is a deliberate local-only pick, never overridden.
    assert serve_shelf.resolve_default_brain("ollama", True) == "ollama"
    assert serve_shelf.resolve_default_brain("ollama", False) == "ollama"


def test_health_payload_shape_carries_default_brain():
    brains = {
        "claude": True,
        "ollama": False,
        "hermes": {"wired": True, "model": "gpt-5.5", "routes": []},
    }
    payload = serve_shelf.health_payload("claude", brains, ax_ok=False, prep=None)
    assert payload["ok"] is True
    assert payload["brain"] == "claude"  # the configured default, unchanged
    assert payload["default_brain"] == "hermes"  # the request-time truth
    assert payload["brains"] is brains
    assert payload["ax"] == {"wired": False}
    assert payload["prep_cron"] is None


def test_health_payload_default_brain_tracks_the_wired_gate():
    unwired = {"claude": True, "ollama": True, "hermes": {"wired": False}}
    payload = serve_shelf.health_payload(
        "claude", unwired, ax_ok=True, prep={"installed_at": "x", "schedule": None}
    )
    assert payload["default_brain"] == "claude"
    assert payload["ax"] == {"wired": True}
    # A degenerate hermes entry (older probe shape) reads as not wired.
    odd = {"claude": True, "ollama": True, "hermes": False}
    assert serve_shelf.health_payload("claude", odd, False, None)["default_brain"] == "claude"


# --- validate_tool_call (the ollama agency boundary) ------------------------


def test_validate_tool_call_fetch_talk_happy_path():
    argv = serve_shelf.validate_tool_call(
        "fetch_talk",
        {
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Some Talk",
            "teacher": "Ajahn Brahm",
            "themes": "anger, patience",
        },
    )
    assert argv == [
        "uv", "run", "tools/fetch_talk.py", "https://www.youtube.com/watch?v=abc123",
        "--title", "Some Talk", "--teacher", "Ajahn Brahm", "--themes", "anger, patience",
    ]


def test_validate_tool_call_fetch_talk_url_only():
    argv = serve_shelf.validate_tool_call("fetch_talk", {"url": "http://example.org/t"})
    assert argv == ["uv", "run", "tools/fetch_talk.py", "http://example.org/t"]


def test_validate_tool_call_rejects_bad_urls():
    for url in (
        "file:///etc/passwd",
        "ftp://example.org/x",
        "notaurl",
        "https://",  # no hostname
        "--library",  # flag smuggled as url
        None,
        42,
    ):
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("fetch_talk", {"url": url})


def test_validate_tool_call_rejects_flag_smuggling_in_text_fields():
    base = {"url": "https://example.org/t"}
    for field in ("title", "teacher", "themes"):
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("fetch_talk", {**base, field: "--library /tmp"})
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("fetch_talk", {**base, field: "  -x"})
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("fetch_talk", {**base, field: ["a", "list"]})
    # Empty or absent optional fields are simply skipped.
    argv = serve_shelf.validate_tool_call("fetch_talk", {**base, "title": ""})
    assert "--title" not in argv


def test_validate_tool_call_rebuild_shelf():
    assert serve_shelf.validate_tool_call("rebuild_shelf", {}) == [
        "uv", "run", "tools/build_shelf.py",
    ]


def test_validate_tool_call_speak_sanitizes_out_name():
    argv = serve_shelf.validate_tool_call(
        "speak", {"text": "Breathe out slowly.", "out_name": "Morning Reflection"}
    )
    assert argv == [
        "uv", "run", "tools/speak.py", "--text", "Breathe out slowly.",
        "-o", "library/morning-reflection.mp3",
    ]
    # Path traversal and dots collapse to a bare slug pinned under library/.
    argv = serve_shelf.validate_tool_call(
        "speak", {"text": "hi", "out_name": "../../etc/x"}
    )
    assert argv[-1] == "library/etc-x.mp3"
    assert ".." not in argv[-1]
    argv = serve_shelf.validate_tool_call("speak", {"text": "hi", "out_name": "a.b.mp3"})
    assert argv[-1] == "library/a-b-mp3.mp3"


def test_validate_tool_call_speak_rejects_bad_args():
    with pytest.raises(ValueError):  # nothing left after sanitizing
        serve_shelf.validate_tool_call("speak", {"text": "hi", "out_name": "###"})
    with pytest.raises(ValueError):  # dash-led text could smuggle a flag
        serve_shelf.validate_tool_call("speak", {"text": "--engine say", "out_name": "x"})
    with pytest.raises(ValueError):
        serve_shelf.validate_tool_call("speak", {"text": "", "out_name": "x"})
    with pytest.raises(ValueError):
        serve_shelf.validate_tool_call("speak", {"text": "hi", "out_name": 7})


def test_validate_tool_call_rejects_unknown_tools_and_non_dict_args():
    with pytest.raises(ValueError):
        serve_shelf.validate_tool_call("run_bash", {"cmd": "ls"})
    with pytest.raises(ValueError):
        serve_shelf.validate_tool_call("", {})
    for args in ("{}", None, ["url"], 3):
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("rebuild_shelf", args)


# --- parse_tool_calls -------------------------------------------------------


def test_parse_tool_calls_reads_ollama_shape():
    message = {
        "tool_calls": [
            {"id": "call_1", "function": {"index": 0, "name": "rebuild_shelf", "arguments": {}}},
            {"function": {"name": "fetch_talk", "arguments": {"url": "https://e.org"}}},
        ]
    }
    assert serve_shelf.parse_tool_calls(message) == [
        ("rebuild_shelf", {}),
        ("fetch_talk", {"url": "https://e.org"}),
    ]


def test_parse_tool_calls_decodes_json_string_arguments():
    message = {
        "tool_calls": [
            {"function": {"name": "fetch_talk", "arguments": '{"url": "https://e.org"}'}}
        ]
    }
    assert serve_shelf.parse_tool_calls(message) == [
        ("fetch_talk", {"url": "https://e.org"})
    ]


def test_parse_tool_calls_tolerates_junk():
    assert serve_shelf.parse_tool_calls({}) == []
    assert serve_shelf.parse_tool_calls({"tool_calls": None}) == []
    junk = {"tool_calls": [{"function": {"arguments": "not json"}}, {}]}
    # Junk calls survive as ("", {}) so validate_tool_call can reject them.
    assert serve_shelf.parse_tool_calls(junk) == [("", {}), ("", {})]


# --- resolve_agent_model ----------------------------------------------------


def test_resolve_agent_model_keeps_a_configured_match_even_without_tools():
    model, has_tools = serve_shelf.resolve_agent_model(
        "gemma-plain", ["gemma-plain:latest", "qwen3:latest"], ["qwen3:latest"]
    )
    assert model == "gemma-plain:latest"
    assert has_tools is False


def test_resolve_agent_model_fallback_prefers_tools_capable():
    model, has_tools = serve_shelf.resolve_agent_model(
        "missing", ["plain:latest", "capable:latest"], ["capable:latest"]
    )
    assert (model, has_tools) == ("capable:latest", True)


def test_resolve_agent_model_no_capable_model_degrades():
    model, has_tools = serve_shelf.resolve_agent_model(
        "missing", ["plain:latest"], []
    )
    assert (model, has_tools) == ("plain:latest", False)
    assert serve_shelf.resolve_agent_model("qwen3", [], []) == ("qwen3", False)


# --- agency in the payload ---------------------------------------------------


def test_build_ollama_payload_carries_tools_and_agency_note():
    payload = serve_shelf.build_ollama_payload(
        [{"role": "user", "content": "hi"}],
        model="m",
        stream=True,
        tools=serve_shelf.OLLAMA_TOOLS,
        agency="You can act through tools.",
    )
    assert payload["tools"] == serve_shelf.OLLAMA_TOOLS
    assert "You can act through tools." in payload["messages"][0]["content"]
    # Without tools, the key is absent entirely (some models choke on []).
    plain = serve_shelf.build_ollama_payload([{"role": "user", "content": "hi"}], model="m")
    assert "tools" not in plain


# --- ollama_tool_loop (faked responses) --------------------------------------


class _FakeResponse:
    def __init__(self, objs):
        self._lines = [json.dumps(o).encode() for o in objs]

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _no_opener(payload):
    raise AssertionError("no further round expected")


def _no_runner(argv):
    raise AssertionError("no tool run expected")


def test_ollama_tool_loop_plain_reply_streams_untouched():
    response = _FakeResponse([
        {"message": {"content": "It grows "}, "done": False},
        {"message": {"content": "on anger."}, "done": True},
    ])
    transcript = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    before = list(transcript)
    chunks = list(
        serve_shelf.ollama_tool_loop(
            response, transcript, "m", _no_opener, _no_runner,
            tools=serve_shelf.OLLAMA_TOOLS,
        )
    )
    assert "".join(chunks) == "It grows on anger."
    assert transcript == before  # nothing appended on a tool-free turn


def test_ollama_tool_loop_runs_validated_tool_then_streams_answer():
    first = _FakeResponse([
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "rebuild_shelf", "arguments": {}}}]}, "done": False},
        {"message": {"content": ""}, "done": True},
    ])
    opened = []

    def opener(payload):
        opened.append(payload)
        return _FakeResponse([
            {"message": {"content": "Shelf rebuilt — refresh the page."}, "done": True},
        ])

    ran = []

    def runner(argv):
        ran.append(argv)
        return True, "tools/build_shelf.py succeeded"

    transcript = [{"role": "system", "content": "s"}, {"role": "user", "content": "rebuild please"}]
    chunks = list(
        serve_shelf.ollama_tool_loop(
            first, transcript, "m", opener, runner, tools=serve_shelf.OLLAMA_TOOLS
        )
    )
    text = "".join(chunks)
    assert "rebuilding the shelf" in text  # progress marker kept the panel alive
    assert text.endswith("Shelf rebuilt — refresh the page.")
    assert ran == [["uv", "run", "tools/build_shelf.py"]]
    assert opened[0]["tools"] == serve_shelf.OLLAMA_TOOLS  # budget not yet spent
    assert [m["role"] for m in transcript] == ["system", "user", "assistant", "tool"]
    assert "succeeded" in transcript[-1]["content"]


def test_ollama_tool_loop_failure_feeds_back_once_without_tools():
    first = _FakeResponse([
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "fetch_talk", "arguments": {"url": "https://e.org/t"}}}]},
         "done": True},
    ])
    opened = []

    def opener(payload):
        opened.append(payload)
        return _FakeResponse([
            {"message": {"content": "The fetch failed: boom."}, "done": True},
        ])

    def runner(argv):
        return False, "tools/fetch_talk.py failed (exit 1):\nboom"

    transcript = [{"role": "system", "content": "s"}, {"role": "user", "content": "fetch it"}]
    chunks = list(
        serve_shelf.ollama_tool_loop(
            first, transcript, "m", opener, runner, tools=serve_shelf.OLLAMA_TOOLS
        )
    )
    assert "".join(chunks).endswith("The fetch failed: boom.")
    # The explain round gets the error but no tools — it must finish in words.
    assert len(opened) == 1
    assert "tools" not in opened[0]
    assert "failed" in transcript[-1]["content"]


def test_ollama_tool_loop_rejected_call_never_reaches_the_runner():
    first = _FakeResponse([
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "fetch_talk", "arguments": {"url": "file:///etc/passwd"}}}]},
         "done": True},
    ])
    opened = []

    def opener(payload):
        opened.append(payload)
        return _FakeResponse([
            {"message": {"content": "I can't fetch that."}, "done": True},
        ])

    transcript = [{"role": "system", "content": "s"}, {"role": "user", "content": "fetch it"}]
    chunks = list(
        serve_shelf.ollama_tool_loop(
            first, transcript, "m", opener, _no_runner, tools=serve_shelf.OLLAMA_TOOLS
        )
    )
    assert "".join(chunks).endswith("I can't fetch that.")
    assert "rejected" in transcript[-1]["content"]
    assert "tools" not in opened[0]  # a rejection also ends the tool budget


def test_ollama_tool_loop_respects_the_round_budget():
    def calling_round():
        return _FakeResponse([
            {"message": {"content": "", "tool_calls": [
                {"function": {"name": "rebuild_shelf", "arguments": {}}}]}, "done": True},
        ])

    opened = []
    final = _FakeResponse([{"message": {"content": "Done at last."}, "done": True}])

    def opener(payload):
        opened.append(payload)
        if len(opened) < 4:
            return calling_round()
        return final

    transcript = [{"role": "system", "content": "s"}, {"role": "user", "content": "go"}]
    chunks = list(
        serve_shelf.ollama_tool_loop(
            calling_round(), transcript, "m", opener,
            lambda argv: (True, "ok"), tools=serve_shelf.OLLAMA_TOOLS, max_rounds=4,
        )
    )
    assert "".join(chunks).endswith("Done at last.")
    assert len(opened) == 4
    assert all("tools" in p for p in opened[:3])
    assert "tools" not in opened[3]  # budget spent: the last round must talk


# --- persistent chat memory (library/.chat) --------------------------------


def test_append_turn_and_load_history_roundtrip(tmp_path):
    path = tmp_path / ".chat" / "history.jsonl"  # parents are created
    serve_shelf.append_turn(
        path, "user", "hello", "claude", timestamp="2026-07-01T10:00:00+00:00"
    )
    serve_shelf.append_turn(
        path, "assistant", "hi **friend**\nline two", "claude",
        timestamp="2026-07-01T10:00:05+00:00",
    )
    turns = serve_shelf.load_history(path)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0] == {
        "role": "user", "content": "hello", "brain": "claude",
        "ts": "2026-07-01T10:00:00+00:00",
    }
    assert turns[1]["content"] == "hi **friend**\nline two"  # newlines survive


def test_append_turn_default_timestamp_is_parseable_iso(tmp_path):
    from datetime import datetime

    path = tmp_path / "history.jsonl"
    serve_shelf.append_turn(path, "user", "hi", "ollama")
    (turn,) = serve_shelf.load_history(path)
    assert datetime.fromisoformat(turn["ts"]).tzinfo is not None


def test_load_history_trims_to_limit(tmp_path):
    path = tmp_path / "history.jsonl"
    for i in range(60):
        serve_shelf.append_turn(path, "user", f"turn {i}", "claude", timestamp="t")
    turns = serve_shelf.load_history(path, limit=50)
    assert len(turns) == 50
    assert turns[0]["content"] == "turn 10"
    assert turns[-1]["content"] == "turn 59"


def test_load_history_tolerates_corrupt_and_alien_lines(tmp_path):
    path = tmp_path / "history.jsonl"
    serve_shelf.append_turn(path, "user", "before", "claude", timestamp="t")
    with path.open("a") as handle:
        handle.write("{torn write\n")  # crash mid-append
        handle.write('"just a string"\n')  # valid JSON, wrong shape
        handle.write('{"role": 5, "content": "bad types"}\n')
        handle.write("\n")
    serve_shelf.append_turn(path, "assistant", "after", "claude", timestamp="t")
    turns = serve_shelf.load_history(path)
    assert [t["content"] for t in turns] == ["before", "after"]


def test_load_history_missing_file_is_empty(tmp_path):
    assert serve_shelf.load_history(tmp_path / "nope.jsonl") == []


def test_chat_state_roundtrip_and_tolerance(tmp_path):
    path = tmp_path / ".chat" / "state.json"
    assert serve_shelf.load_chat_state(path) == {}  # missing file
    serve_shelf.save_chat_state(path, {"session_id": "s-42"})
    assert serve_shelf.load_chat_state(path) == {"session_id": "s-42"}
    path.write_text("{corrupt")
    assert serve_shelf.load_chat_state(path) == {}


def test_record_stream_persists_completed_turn_and_session_meta(tmp_path):
    turns_path = tmp_path / "sessions" / "s1.jsonl"
    meta_path = tmp_path / "sessions" / "s1.json"
    state = {"session_id": "c-live"}
    chunks = list(
        serve_shelf.record_stream(
            iter(["The demon ", "grows on anger."]),
            "what does it grow on?",
            "claude",
            state,
            turns_path=turns_path,
            meta_path=meta_path,
            view="anger-eating-demons",
        )
    )
    assert chunks == ["The demon ", "grows on anger."]  # passthrough intact
    turns = serve_shelf.load_history(turns_path)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[1]["content"] == "The demon grows on anger."
    assert turns[1]["brain"] == "claude"
    meta = serve_shelf.load_session_meta(meta_path)
    # The claude thread id and the ambient talk both land in the sidecar.
    assert meta["claude_session_id"] == "c-live"
    assert meta["talks"] == ["anger-eating-demons"]
    assert meta["title"] == "what does it grow on?"  # fallback until summarized
    assert meta["updated"]


def test_record_stream_skips_recording_empty_replies(tmp_path):
    turns_path = tmp_path / "sessions" / "s1.jsonl"
    meta_path = tmp_path / "sessions" / "s1.json"
    list(
        serve_shelf.record_stream(
            iter([]), "hello?", "claude", {"session_id": None},
            turns_path=turns_path, meta_path=meta_path,
        )
    )
    assert serve_shelf.load_history(turns_path) == []
    assert serve_shelf.load_session_meta(meta_path) == {}  # no ghost sessions


def test_resolve_ollama_model_prefers_configured_then_falls_back():
    installed = ["llama3.2:latest", "qwen3:latest"]
    assert serve_shelf.resolve_ollama_model("qwen3", installed) == "qwen3:latest"
    assert (
        serve_shelf.resolve_ollama_model("qwen3:latest", installed) == "qwen3:latest"
    )
    assert serve_shelf.resolve_ollama_model("missing", installed) == "llama3.2:latest"
    assert serve_shelf.resolve_ollama_model("qwen3", []) == "qwen3"


# --- sessions (library/.chat/sessions/) -------------------------------------


def _write_session(sessions_dir, sid, turns, meta=None):
    for role, content in turns:
        serve_shelf.append_turn(
            sessions_dir / f"{sid}.jsonl", role, content, "claude", timestamp="t"
        )
    if meta is not None:
        serve_shelf.save_session_meta(sessions_dir / f"{sid}.json", meta)


def test_update_session_meta_creates_then_updates(tmp_path):
    meta_path = tmp_path / "s1.json"
    meta = serve_shelf.update_session_meta(
        meta_path,
        claude_session_id="c-1",
        talk="patience",
        fallback_title_text="  what is\n patience really about, in this talk here today? okay  ",
    )
    assert meta["id"] == "s1"
    assert meta["talks"] == ["patience"]
    assert meta["claude_session_id"] == "c-1"
    assert meta["summary"] == ""
    assert meta["created"] and meta["updated"]
    # Fallback title: whitespace collapsed, capped calmly.
    assert "\n" not in meta["title"]
    assert len(meta["title"]) <= 61
    assert meta["title"].startswith("what is patience")
    again = serve_shelf.update_session_meta(
        meta_path, claude_session_id="c-2", talk="patience",
        fallback_title_text="ignored",
    )
    assert again["title"] == meta["title"]  # the first user line sticks
    assert again["talks"] == ["patience"]  # no duplicates
    assert again["claude_session_id"] == "c-2"
    third = serve_shelf.update_session_meta(meta_path, talk="anger-eating-demons")
    assert third["talks"] == ["patience", "anger-eating-demons"]
    assert third["claude_session_id"] == "c-2"  # absent id never clears it


def test_list_sessions_recency_sorted_with_meta_fallbacks(tmp_path):
    _write_session(
        tmp_path, "old", [("user", "about patience")],
        {"id": "old", "title": "Patience chat", "summary": "Grim endurance, revisited.",
         "updated": "2026-06-01T10:00:00+00:00"},
    )
    _write_session(
        tmp_path, "recent", [("user", "tell me about the demon")],
        {"id": "recent", "title": "Demon story", "summary": "",
         "updated": "2026-07-01T10:00:00+00:00"},
    )
    _write_session(tmp_path, "bare", [("user", "no meta sidecar here")])
    import os
    import time

    old_stamp = time.mktime((2026, 5, 1, 12, 0, 0, 0, 0, 0))
    os.utime(tmp_path / "bare.jsonl", (old_stamp, old_stamp))  # deterministic mtime
    sessions = serve_shelf.list_sessions(tmp_path)
    assert [s["id"] for s in sessions] == ["recent", "old", "bare"]  # newest first
    assert {s["id"] for s in sessions} == {"recent", "old", "bare"}
    bare = next(s for s in sessions if s["id"] == "bare")
    assert bare["title"] == "no meta sidecar here"  # first user line fallback
    assert bare["updated"]  # mtime fallback, still sortable
    for s in sessions:
        assert set(s) == {"id", "title", "summary", "updated"}
    assert serve_shelf.list_sessions(tmp_path / "missing") == []


def test_migrate_history_folds_legacy_thread_into_first_session(tmp_path):
    chat = tmp_path / ".chat"
    serve_shelf.append_turn(chat / "history.jsonl", "user", "hello", "claude", timestamp="t")
    serve_shelf.append_turn(chat / "history.jsonl", "assistant", "hi friend", "claude", timestamp="t")
    serve_shelf.save_chat_state(chat / "state.json", {"session_id": "c-9"})
    sid = serve_shelf.migrate_history(chat)
    assert sid == "earlier-conversation"
    assert not (chat / "history.jsonl").exists()  # moved, not copied
    turns = serve_shelf.load_history(chat / "sessions" / f"{sid}.jsonl")
    assert [t["content"] for t in turns] == ["hello", "hi friend"]
    meta = serve_shelf.load_session_meta(chat / "sessions" / f"{sid}.json")
    assert meta["title"] == "Earlier conversation"
    assert meta["claude_session_id"] == "c-9"  # the thread continues
    # Idempotent: nothing left to migrate the second time.
    assert serve_shelf.migrate_history(chat) is None


def test_resolve_session_defaults_and_new(tmp_path):
    _write_session(tmp_path, "abc", [("user", "hi")], {"id": "abc", "updated": "2026-07-01T00:00:00+00:00"})
    # The server's current session is trusted as-is.
    assert serve_shelf.resolve_session(None, "cur-1", tmp_path) == "cur-1"
    # No current: fall back to the most recent stored session.
    assert serve_shelf.resolve_session(None, None, tmp_path) == "abc"
    assert serve_shelf.resolve_session("", None, tmp_path) == "abc"
    # An explicitly named, existing session is honoured.
    assert serve_shelf.resolve_session("abc", "cur-1", tmp_path) == "abc"
    # "new" mints a fresh id (safe charset, no collision with stored ones).
    fresh = serve_shelf.resolve_session("new", "cur-1", tmp_path)
    assert fresh != "abc" and fresh != "cur-1"
    assert serve_shelf.SESSION_ID_RE.fullmatch(fresh)
    # Nothing stored, no current: a first session is minted too.
    empty = tmp_path / "empty"
    empty.mkdir()
    assert serve_shelf.SESSION_ID_RE.fullmatch(serve_shelf.resolve_session(None, None, empty))


def test_resolve_session_rejects_bad_ids(tmp_path):
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_session("no-such-session", None, tmp_path)
    assert excinfo.value.status == 404
    for evil in ("../evil", ".hidden", "a/b", "a b", "..", ""):
        if evil == "":
            continue  # empty means "default", tested above
        with pytest.raises(serve_shelf.BrainError) as excinfo:
            serve_shelf.resolve_session(evil, None, tmp_path)
        assert excinfo.value.status == 400
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_session(42, None, tmp_path)
    assert excinfo.value.status == 400


# --- episodes: rollover is an invisible seam ----------------------------------


def test_should_rollover_only_after_the_idle_window():
    from datetime import datetime, timezone

    now = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
    assert serve_shelf.ROLLOVER_IDLE == 6 * 3600
    # Fresh episode: continue.
    assert not serve_shelf.should_rollover("2026-07-02T11:00:00+00:00", now)
    # Just inside the window: continue; just past it: roll.
    assert not serve_shelf.should_rollover("2026-07-02T06:00:01+00:00", now)
    assert serve_shelf.should_rollover("2026-07-02T05:59:59+00:00", now)
    assert serve_shelf.should_rollover("2026-06-30T12:00:00+00:00", now)
    # A naive stamp is read as UTC rather than crashing.
    assert serve_shelf.should_rollover("2026-07-01T00:00:00", now)
    # Missing or garbled stamps never force a boundary.
    assert not serve_shelf.should_rollover(None, now)
    assert not serve_shelf.should_rollover("", now)
    assert not serve_shelf.should_rollover("not-a-date", now)


def test_resolve_session_with_rollover_rolls_only_default_continuation(tmp_path):
    from datetime import datetime, timezone

    now = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
    _write_session(
        tmp_path, "fresh", [("user", "hi")],
        {"id": "fresh", "updated": "2026-07-02T11:30:00+00:00"},
    )
    _write_session(
        tmp_path, "stale", [("user", "hi")],
        {"id": "stale", "updated": "2026-07-01T08:00:00+00:00"},
    )
    resolve = serve_shelf.resolve_session_with_rollover
    # A fresh current episode simply continues.
    assert resolve(None, "fresh", tmp_path, now=now) == "fresh"
    # A stale one quietly closes: a new id comes back (the caller's
    # existing leave-summary trigger then fires for the old episode).
    rolled = resolve(None, "stale", tmp_path, now=now)
    assert rolled != "stale"
    assert serve_shelf.SESSION_ID_RE.fullmatch(rolled)
    # An EXPLICIT session request is honored even when stale — the aX
    # bridge pins per-sender episodes and must never be rolled from
    # under it.
    assert resolve("stale", "fresh", tmp_path, now=now) == "stale"
    # Explicit "new" still mints, as before.
    assert resolve("new", "fresh", tmp_path, now=now) not in ("fresh", "stale")
    # No current: the most recent stored episode is checked the same way
    # (a restart after days away starts clean instead of resuming June).
    assert resolve(None, None, tmp_path, now=now) == "fresh"
    (tmp_path / "fresh.jsonl").unlink()
    (tmp_path / "fresh.json").unlink()
    assert resolve(None, None, tmp_path, now=now) != "stale"


# --- session summaries -------------------------------------------------------


def test_summarize_prompt_shapes_the_ask():
    turns = [
        {"role": "user", "content": "what did the demon grow on?"},
        {"role": "assistant", "content": "It grows on anger and shrinks on kindness."},
    ]
    prompt = serve_shelf.summarize_prompt(turns)
    assert "Title:" in prompt and "Summary:" in prompt
    assert "Student: what did the demon grow on?" in prompt
    assert "Guide: It grows on anger" in prompt


def test_parse_summary_reads_title_and_summary_lines():
    text = "Title: The demon and kindness\nSummary: We walked through the anger-eating demon story.\nExtra chatter."
    assert serve_shelf.parse_summary(text) == (
        "The demon and kindness",
        "We walked through the anger-eating demon story.",
    )
    # Tolerant of case and light markdown dressing.
    title, summary = serve_shelf.parse_summary("**title:** Demons\n**summary:** Short one.")
    assert title == "Demons"
    assert summary == "Short one."
    assert serve_shelf.parse_summary("no structure at all") == (None, None)


def test_summarize_session_writes_meta_and_tolerates_failure(tmp_path):
    _write_session(
        tmp_path, "s1", [("user", "demon story please"), ("assistant", "It grows on anger.")],
        {"id": "s1", "title": "demon story please", "summary": ""},
    )
    asked = []

    def ask(prompt):
        asked.append(prompt)
        return "Title: The anger-eating demon\nSummary: The story, told plainly."

    serve_shelf.summarize_session("s1", tmp_path, ask=ask)
    meta = serve_shelf.load_session_meta(tmp_path / "s1.json")
    assert meta["title"] == "The anger-eating demon"
    assert meta["summary"] == "The story, told plainly."
    assert len(asked) == 1
    # Already summarized: not asked again.
    serve_shelf.summarize_session("s1", tmp_path, ask=ask)
    assert len(asked) == 1
    # A failing brain leaves the fallback title untouched.
    _write_session(tmp_path, "s2", [("user", "hello")], {"id": "s2", "title": "hello", "summary": ""})

    def boom(prompt):
        raise RuntimeError("no brain")

    serve_shelf.summarize_session("s2", tmp_path, ask=boom)
    assert serve_shelf.load_session_meta(tmp_path / "s2.json")["title"] == "hello"
    # An empty session is simply skipped.
    serve_shelf.summarize_session("nothing-there", tmp_path, ask=ask)
    assert len(asked) == 1


# --- search_sessions (recall) -----------------------------------------------


def _recall_fixture(tmp_path):
    _write_session(
        tmp_path, "demons",
        [("user", "tell me the story about the maggots on the dog"),
         ("assistant", "Ajahn Brahm tells of maggots and the kindness that followed.")],
        {"id": "demons", "title": "Maggots and kindness",
         "summary": "The maggot story, and meeting disgust with care.",
         "updated": "2026-06-20T10:00:00+00:00"},
    )
    _write_session(
        tmp_path, "patience",
        [("user", "patience feels like grim endurance"),
         ("assistant", "The adze handle wears slowly; progress is invisible.")],
        {"id": "patience", "title": "Patience, not endurance",
         "summary": "Patience as not wearing the burden all the time.",
         "updated": "2026-06-25T10:00:00+00:00"},
    )
    return tmp_path


def test_search_sessions_ranks_matching_session_first(tmp_path):
    sessions_dir = _recall_fixture(tmp_path)
    results = serve_shelf.search_sessions("what did we discuss about maggots?", sessions_dir)
    assert results, "expected a hit"
    top = results[0]
    assert top["session_id"] == "demons"
    assert set(top) == {"session_id", "title", "snippet", "when"}
    assert "maggot" in top["snippet"].lower()
    assert top["when"] == "2026-06-20T10:00:00+00:00"


def test_search_sessions_matches_summaries_too(tmp_path):
    sessions_dir = _recall_fixture(tmp_path)
    # "disgust" appears only in the stored summary, not in any turn.
    results = serve_shelf.search_sessions("meeting disgust", sessions_dir)
    assert results and results[0]["session_id"] == "demons"


def test_search_sessions_empty_and_no_match(tmp_path):
    sessions_dir = _recall_fixture(tmp_path)
    assert serve_shelf.search_sessions("", sessions_dir) == []
    assert serve_shelf.search_sessions("the and of", sessions_dir) == []  # stopwords only
    assert serve_shelf.search_sessions("quantum blockchain", sessions_dir) == []
    assert serve_shelf.search_sessions("maggots", tmp_path / "missing") == []


def test_search_history_cli_round_trip(tmp_path):
    sessions_dir = _recall_fixture(tmp_path)
    script = MODULE_PATH.parent / "search_history.py"
    out = subprocess.run(
        [sys.executable, str(script), "--sessions-dir", str(sessions_dir), "maggots", "story"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "Maggots and kindness" in out
    assert "demons" in out  # the session id is printed for follow-up
    empty = subprocess.run(
        [sys.executable, str(script), "--sessions-dir", str(sessions_dir), "zzzunknownzzz"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "No past conversation" in empty


# --- ambient context ----------------------------------------------------------


def test_ambient_prefix_names_the_open_talk():
    titles = {"patience": "Patience", "anger-eating-demons": "Anger Eating Demons"}
    line = serve_shelf.ambient_prefix("patience", titles)
    assert line.startswith("[") and line.endswith("]")
    assert '"Patience"' in line
    assert "library/patience/transcript.md" in line
    assert "ambient context" in line
    assert serve_shelf.ambient_prefix(None, titles) == ""
    assert serve_shelf.ambient_prefix("not-a-talk", titles) == ""
    assert serve_shelf.ambient_prefix("patience", {}) == ""


def test_pick_chunks_for_view_leads_with_the_open_talk():
    # The question points at the demon talk, but Patience is open on the
    # shelf — its chunks must lead anyway.
    picked = serve_shelf.pick_chunks_for_view(
        "what does the anger eating demon grow on?", TRANSCRIPTS, "Patience", k=4
    )
    assert picked[0][0] == "Patience"
    titles = [title for title, _ in picked]
    assert "Anger Eating Demons" in titles  # general retrieval still follows


def test_pick_chunks_for_view_no_overlap_still_grounds_the_open_talk():
    picked = serve_shelf.pick_chunks_for_view(
        "quantum blockchain synergy", TRANSCRIPTS, "Patience", k=4
    )
    assert picked and picked[0][0] == "Patience"  # opening chunk as ambient


def test_pick_chunks_for_view_without_view_matches_plain_pick():
    question = "what does the anger eating demon grow on?"
    assert serve_shelf.pick_chunks_for_view(question, TRANSCRIPTS, None, k=4) == (
        serve_shelf.pick_chunks(question, TRANSCRIPTS, k=4)
    )
    assert serve_shelf.pick_chunks_for_view(question, TRANSCRIPTS, "Unknown Talk", k=4) == (
        serve_shelf.pick_chunks(question, TRANSCRIPTS, k=4)
    )


# --- search_history as an ollama tool -----------------------------------------


def test_validate_tool_call_search_history():
    argv = serve_shelf.validate_tool_call("search_history", {"q": "maggots story"})
    assert argv == ["uv", "run", "tools/search_history.py", "maggots story"]
    for bad in ("", "   ", "--sessions-dir /etc", None, 7):
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("search_history", {"q": bad})


def test_ollama_tools_cover_the_seven_reviewed_hands():
    names = {tool["function"]["name"] for tool in serve_shelf.OLLAMA_TOOLS}
    assert names == {
        "fetch_talk", "rebuild_shelf", "speak", "search_history",
        "write_artifact", "update_session_summary", "get_curriculum",
    }
    for name in ("search_history", "write_artifact", "update_session_summary",
                 "get_curriculum"):
        assert name in serve_shelf.TOOL_PROGRESS
        assert name in serve_shelf.AGENCY_TOOLS_NOTE


def test_validate_tool_call_get_curriculum_marker():
    # No arguments; in-process like write_artifact.
    assert serve_shelf.validate_tool_call("get_curriculum", {}) == ["get_curriculum"]
    assert serve_shelf.validate_tool_call("get_curriculum", {"junk": 1}) == ["get_curriculum"]


# --- update_session_summary: freshness as a tool ------------------------------


def test_update_session_summary_writes_meta_preserving_fields(tmp_path):
    _write_session(
        tmp_path, "s1", [("user", "hi")],
        {"id": "s1", "title": "old", "summary": "", "talks": ["patience"],
         "claude_session_id": "c-1", "created": "2026-07-01T00:00:00+00:00",
         "updated": "2026-07-01T00:00:00+00:00"},
    )
    meta = serve_shelf.update_session_summary(
        tmp_path, "s1", "  Bricks and walls  ",
        " Seeing whole people, not two bad bricks. ",
    )
    assert meta["title"] == "Bricks and walls"
    assert meta["summary"] == "Seeing whole people, not two bad bricks."
    # Everything else in the sidecar survives; only `updated` moves.
    assert meta["talks"] == ["patience"]
    assert meta["claude_session_id"] == "c-1"
    assert meta["created"] == "2026-07-01T00:00:00+00:00"
    assert meta["updated"] != "2026-07-01T00:00:00+00:00"
    on_disk = serve_shelf.load_session_meta(tmp_path / "s1.json")
    assert on_disk["title"] == "Bricks and walls"


def test_update_session_summary_validation_matrix(tmp_path):
    _write_session(tmp_path, "s1", [("user", "hi")], {"id": "s1"})
    update = serve_shelf.update_session_summary
    with pytest.raises(ValueError, match="invalid session id"):
        update(tmp_path, "../evil", "t", "s")
    with pytest.raises(ValueError, match="invalid session id"):
        update(tmp_path, 42, "t", "s")
    with pytest.raises(ValueError, match="no session"):
        update(tmp_path, "missing", "t", "s")
    for bad_title in ("", "   ", "x" * 81, 7):
        with pytest.raises(ValueError):
            update(tmp_path, "s1", bad_title, "s")
    for bad_summary in ("", "   ", "x" * 301, None):
        with pytest.raises(ValueError):
            update(tmp_path, "s1", "t", bad_summary)
    # Exactly at the caps is fine.
    meta = update(tmp_path, "s1", "x" * 80, "y" * 300)
    assert len(meta["title"]) == 80 and len(meta["summary"]) == 300


def test_validate_tool_call_update_session_summary_marker():
    argv = serve_shelf.validate_tool_call(
        "update_session_summary",
        {"session_id": "abc-1", "title": "Bricks", "summary": "Whole people."},
    )
    # In-process like write_artifact: execution goes through the full
    # update_session_summary validation again (existence included).
    assert argv == ["update_session_summary", "abc-1", "Bricks", "Whole people."]
    base = {"session_id": "abc-1", "title": "T", "summary": "S"}
    for field, bad in (
        ("session_id", "../x"),
        ("session_id", 5),
        ("title", ""),
        ("title", "x" * 81),
        ("summary", ""),
        ("summary", "x" * 301),
    ):
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("update_session_summary", {**base, field: bad})


def test_update_session_summary_cli_round_trip(tmp_path):
    _write_session(tmp_path, "s1", [("user", "hi")], {"id": "s1", "claude_session_id": "c-1"})
    script = MODULE_PATH.parent / "update_session_summary.py"
    subprocess.run(
        [sys.executable, str(script), "--sessions-dir", str(tmp_path),
         "s1", "Bricks and walls", "Seeing whole people."],
        check=True, capture_output=True, text=True,
    )
    meta = serve_shelf.load_session_meta(tmp_path / "s1.json")
    assert meta["title"] == "Bricks and walls"
    assert meta["summary"] == "Seeing whole people."
    assert meta["claude_session_id"] == "c-1"  # preserved through the CLI
    # A rejection exits nonzero with the reason on stderr.
    bad = subprocess.run(
        [sys.executable, str(script), "--sessions-dir", str(tmp_path),
         "no-such-session", "t", "s"],
        capture_output=True, text=True,
    )
    assert bad.returncode != 0
    assert "no session" in bad.stderr.lower()


def test_ambient_prefix_carries_the_session_id():
    titles = {"patience": "Patience"}
    both = serve_shelf.ambient_prefix("patience", titles, session_id="abc-1")
    assert "[session: abc-1]" in both
    assert '"Patience"' in both
    # The session line rides even without an open talk...
    assert serve_shelf.ambient_prefix(None, titles, session_id="abc-1") == "[session: abc-1]"
    # ...and its absence keeps the old behavior byte-for-byte.
    assert serve_shelf.ambient_prefix(None, titles) == ""
    assert serve_shelf.ambient_prefix("patience", titles) == (
        serve_shelf.ambient_prefix("patience", titles, session_id=None)
    )


# --- the model picker (/api/models + per-request "model") --------------------


def test_describe_models_maps_capability_and_size():
    models = [
        {"name": "gemma4:12b", "size": 7_556_508_396},
        {"name": "qwen3.5:2b-mlx", "size": 3_117_471_137},
        {"name": "tiny:latest"},  # no size reported
        {"size": 42},  # nameless junk is skipped
        {"name": ""},  # so is an empty name
    ]
    described = serve_shelf.describe_models(models, {"gemma4:12b"})
    assert described == [
        {"name": "gemma4:12b", "tools": True, "size_gb": 7.6},
        {"name": "qwen3.5:2b-mlx", "tools": False, "size_gb": 3.1},
        {"name": "tiny:latest", "tools": False, "size_gb": 0.0},
    ]
    assert serve_shelf.describe_models([], set()) == []


def test_resolve_request_model_matches_installed_names():
    installed = ["gemma4:12b", "gemma4:latest", "qwen3:latest"]
    # No request: no override.
    assert serve_shelf.resolve_request_model(None, installed) is None
    assert serve_shelf.resolve_request_model("", installed) is None
    # Exact and tag-insensitive matches resolve to the installed name.
    assert serve_shelf.resolve_request_model("gemma4:12b", installed) == "gemma4:12b"
    assert serve_shelf.resolve_request_model("qwen3", installed) == "qwen3:latest"


def test_resolve_request_model_unknown_or_bad_is_a_400():
    installed = ["gemma4:12b"]
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_request_model("mystery:7b", installed)
    assert excinfo.value.status == 400
    assert "mystery:7b" in excinfo.value.message
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.resolve_request_model(42, installed)
    assert excinfo.value.status == 400


# --- artifacts: the write wall + the CSP wall ---------------------------------


def _artifact_library(tmp_path):
    library = tmp_path / "library"
    (library / "patience").mkdir(parents=True)
    return library


def test_artifact_path_accepts_a_clean_slug_and_name(tmp_path):
    library = _artifact_library(tmp_path)
    path = serve_shelf.artifact_path(library, "patience", "breath-timer.html")
    assert path == library / "patience" / "artifacts" / "breath-timer.html"
    # Underscores and digits are fine too.
    assert serve_shelf.artifact_path(library, "patience", "day_2.html")


def test_artifact_path_rejects_traversal_and_junk(tmp_path):
    library = _artifact_library(tmp_path)
    bad_names = (
        "../escape.html",  # traversal
        "..%2Fescape.html",  # encoded traversal junk
        "/etc/x.html",  # absolute
        "a/b.html",  # nested
        "escape.htm",  # wrong extension
        "escape.html.txt",  # double extension
        "Escape.HTML",  # not lowercase slug chars
        ".hidden.html",  # dot-file
        "",  # empty
        42,  # not a string
    )
    for name in bad_names:
        with pytest.raises(ValueError):
            serve_shelf.artifact_path(library, "patience", name)
    bad_slugs = ("../library", "..", "a/b", "Patience", ".chat", "", None)
    for slug in bad_slugs:
        with pytest.raises(ValueError):
            serve_shelf.artifact_path(library, slug, "ok.html")
    # A well-formed slug that is not an existing talk dir is refused too.
    with pytest.raises(ValueError, match="no talk"):
        serve_shelf.artifact_path(library, "not-a-talk", "ok.html")


def test_write_artifact_writes_under_the_talk_folder(tmp_path):
    library = _artifact_library(tmp_path)
    html = "<!DOCTYPE html><html><body><h1>Pause</h1></body></html>"
    path = serve_shelf.write_artifact(library, "patience", "pause.html", html)
    assert path == library / "patience" / "artifacts" / "pause.html"
    assert path.read_text() == html


def test_write_artifact_enforces_the_size_cap(tmp_path):
    library = _artifact_library(tmp_path)
    cap = serve_shelf.ARTIFACT_MAX_BYTES
    assert cap == 256 * 1024
    # Exactly at the cap is fine; one byte over is refused.
    serve_shelf.write_artifact(library, "patience", "big.html", "x" * cap)
    with pytest.raises(ValueError, match="cap"):
        serve_shelf.write_artifact(library, "patience", "big.html", "x" * (cap + 1))
    for empty in ("", "   ", None, 42):
        with pytest.raises(ValueError):
            serve_shelf.write_artifact(library, "patience", "big.html", empty)


def test_validate_tool_call_write_artifact_marker_argv():
    argv = serve_shelf.validate_tool_call(
        "write_artifact",
        {"slug": "patience", "name": "pause.html", "html": "<html>hi</html>"},
    )
    # Not a subprocess: the marker argv is dispatched to an in-process
    # write (still behind artifact_path/write_artifact validation).
    assert argv == ["write_artifact", "patience", "pause.html", "<html>hi</html>"]
    base = {"slug": "patience", "name": "pause.html", "html": "<html>hi</html>"}
    for field, bad in (
        ("slug", "../library"),
        ("slug", ""),
        ("name", "../escape.html"),
        ("name", "x.txt"),
        ("html", ""),
        ("html", 7),
        ("html", "x" * (serve_shelf.ARTIFACT_MAX_BYTES + 1)),
    ):
        with pytest.raises(ValueError):
            serve_shelf.validate_tool_call("write_artifact", {**base, field: bad})


def test_artifact_csp_walls_off_the_network():
    csp = serve_shelf.ARTIFACT_CSP
    # Nothing loads by default; inline style/script are the only powers.
    assert "default-src 'none'" in csp
    assert "style-src 'unsafe-inline'" in csp
    assert "script-src 'unsafe-inline'" in csp
    # Media and images only from our own origin (plus data: images).
    assert "img-src 'self' data:" in csp
    assert "media-src 'self'" in csp
    assert "frame-ancestors 'self'" in csp
    # No form exfiltration, no <base> games; connect-src falls back to
    # default-src 'none', so fetch/XHR/WebSocket are all blocked.
    assert "form-action 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "connect-src" not in csp  # inherited 'none' — do not loosen it
    assert serve_shelf.ARTIFACT_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert serve_shelf.ARTIFACT_HEADERS["Content-Security-Policy"] == csp


def test_pick_ollama_model_remembers_the_choice():
    state: dict = {}
    installed = ["gemma4:12b", "qwen3:latest"]
    # An explicit pick wins and is remembered in the state dict.
    assert serve_shelf.pick_ollama_model("gemma4:12b", state, "qwen3", installed) == "gemma4:12b"
    assert state["ollama_model"] == "gemma4:12b"
    # Later unpicked turns keep using the remembered model...
    assert serve_shelf.pick_ollama_model(None, state, "qwen3", installed) == "gemma4:12b"
    # ...and an unset state falls back to the configured default (the
    # existing tools-capable resolution then applies downstream).
    assert serve_shelf.pick_ollama_model(None, {}, "qwen3", installed) == "qwen3"
    # A bad pick raises and leaves the remembered model untouched.
    with pytest.raises(serve_shelf.BrainError):
        serve_shelf.pick_ollama_model("mystery", state, "qwen3", installed)
    assert state["ollama_model"] == "gemma4:12b"


# --- listened: the shelf remembers what finished -------------------------------


def _listening_library(tmp_path):
    library = tmp_path / "library"
    (library / "patience").mkdir(parents=True)
    return library


def test_record_listened_appends_log_and_notes(tmp_path):
    library = _listening_library(tmp_path)
    ok = serve_shelf.record_listened(library, "patience", at="2026-07-02T06:00:00+00:00")
    assert ok is True
    entries = serve_shelf.load_listening(library / ".listening.jsonl")
    assert entries == [
        {"slug": "patience", "at": "2026-07-02T06:00:00+00:00", "retract": False}
    ]
    notes = (library / "patience" / "notes.md").read_text()
    assert "## Listening" in notes
    assert "- listened to the end — 2026-07-02" in notes


def test_record_listened_dedupes_within_the_hour(tmp_path):
    library = _listening_library(tmp_path)
    assert serve_shelf.record_listened(library, "patience", at="2026-07-02T06:00:00+00:00")
    # Same talk again within the hour: ignored (refresh loops, double events).
    assert serve_shelf.record_listened(library, "patience", at="2026-07-02T06:40:00+00:00") is False
    assert len(serve_shelf.load_listening(library / ".listening.jsonl")) == 1
    # A later listen is a real second listen.
    assert serve_shelf.record_listened(library, "patience", at="2026-07-02T08:30:00+00:00") is True
    entries = serve_shelf.load_listening(library / ".listening.jsonl")
    assert len(entries) == 2
    # The notes heading is created once; each real listen adds one line.
    notes = (library / "patience" / "notes.md").read_text()
    assert notes.count("## Listening") == 1
    assert notes.count("- listened to the end") == 2


def test_record_listened_rejects_bad_slugs(tmp_path):
    library = _listening_library(tmp_path)
    for bad in ("../evil", "no-such-talk", "", None, 42, ".chat"):
        with pytest.raises(ValueError):
            serve_shelf.record_listened(library, bad)
    assert not (library / ".listening.jsonl").exists()


def test_record_listened_keeps_existing_notes_content(tmp_path):
    library = _listening_library(tmp_path)
    notes_path = library / "patience" / "notes.md"
    notes_path.write_text("# Notes\n\n## My takeaways\n\n- patience is not grim.\n")
    serve_shelf.record_listened(library, "patience", at="2026-07-02T06:00:00+00:00")
    notes = notes_path.read_text()
    assert "- patience is not grim." in notes  # nothing clobbered
    assert notes.index("My takeaways") < notes.index("## Listening")


def _markable_library(tmp_path):
    """A library mark_listened can rebuild: INDEX.md plus the talk dir."""
    library = tmp_path / "library"
    (library / "patience").mkdir(parents=True)
    (library / "INDEX.md").write_text(
        "# Library Index\n\n## patience\n"
        "- **Title:** Patience\n"
        "- **Teacher:** Thanissaro Bhikkhu\n"
        "- **Source:** https://example.org/patience.html\n"
        "- **Themes:** patience\n"
        "- **Path:** library/patience/\n"
    )
    return library


def test_mark_listened_records_rebuilds_and_returns_state(tmp_path):
    # The ONE write path behind POST /api/listened — the player's
    # automatic report and the manual "mark as heard" button both land
    # here: log + notes via record_listened, then a shelf rebuild so the
    # next fetch already carries the heard mark.
    library = _markable_library(tmp_path)
    state = serve_shelf.mark_listened(
        library, "patience", at="2026-07-02T06:00:00+00:00"
    )
    assert state["ok"] is True
    assert state["recorded"] is True
    assert state["last"] == "2026-07-02T06:00:00+00:00"
    assert state["shelf_mtime"] == serve_shelf.shelf_mtime(library)
    # Exactly the automatic path's side effects — shared, not mirrored.
    entries = serve_shelf.load_listening(library / ".listening.jsonl")
    assert entries == [
        {"slug": "patience", "at": "2026-07-02T06:00:00+00:00", "retract": False}
    ]
    assert "## Listening" in (library / "patience" / "notes.md").read_text()
    # The rebuilt page already carries the completed listen on the card.
    shelf = (library / "shelf.html").read_text()
    assert "listened ✓ 2026-07-02" in shelf
    assert 'class="mark-heard"' not in shelf  # the manual door closed


def test_mark_listened_already_listened_is_idempotent(tmp_path):
    library = _markable_library(tmp_path)
    serve_shelf.mark_listened(library, "patience", at="2026-07-02T06:00:00+00:00")
    mtime = serve_shelf.shelf_mtime(library)
    # Within the dedupe window: ok, nothing re-recorded, no rebuild churn.
    state = serve_shelf.mark_listened(
        library, "patience", at="2026-07-02T06:20:00+00:00"
    )
    assert state["ok"] is True
    assert state["recorded"] is False
    assert state["last"] == "2026-07-02T06:00:00+00:00"  # the real state
    assert serve_shelf.shelf_mtime(library) == mtime
    assert len(serve_shelf.load_listening(library / ".listening.jsonl")) == 1


def test_mark_listened_rejects_bad_slugs(tmp_path):
    library = _markable_library(tmp_path)
    for bad in ("../evil", "no-such-talk", "", None):
        with pytest.raises(ValueError):
            serve_shelf.mark_listened(library, bad)
    assert not (library / ".listening.jsonl").exists()
    assert not (library / "shelf.html").exists()  # no rebuild on a miss


def test_load_listening_tolerates_garbage(tmp_path):
    path = tmp_path / ".listening.jsonl"
    path.write_text(
        '{"slug": "patience", "at": "2026-07-02T06:00:00+00:00"}\n'
        "{torn line\n"
        '"just a string"\n'
        '{"slug": 5, "at": "x"}\n'
        '{"slug": "demons", "at": "2026-07-01T10:00:00+00:00"}\n'
    )
    entries = serve_shelf.load_listening(path)
    assert [e["slug"] for e in entries] == ["patience", "demons"]
    assert serve_shelf.load_listening(tmp_path / "missing.jsonl") == []


def test_last_listened_picks_the_most_recent(tmp_path):
    entries = [
        {"slug": "patience", "at": "2026-07-01T10:00:00+00:00"},
        {"slug": "patience", "at": "2026-07-02T06:00:00+00:00"},
        {"slug": "demons", "at": "2026-06-30T10:00:00+00:00"},
    ]
    assert serve_shelf.last_listened(entries, "patience") == "2026-07-02T06:00:00+00:00"
    assert serve_shelf.last_listened(entries, "demons") == "2026-06-30T10:00:00+00:00"
    assert serve_shelf.last_listened(entries, "unheard") is None
    assert serve_shelf.last_listened([], "patience") is None


def test_ambient_prefix_carries_listened_completion():
    titles = {"patience": "Patience"}
    line = serve_shelf.ambient_prefix(
        "patience", titles, session_id="s-1",
        listened_last="2026-07-02T06:00:00+00:00",
    )
    assert "[session: s-1]" in line
    assert '"Patience"' in line
    assert "listened to this talk to the end" in line
    assert "2026-07-02" in line
    # Without a completion, the prefix is unchanged byte-for-byte.
    assert serve_shelf.ambient_prefix("patience", titles, session_id="s-1") == (
        serve_shelf.ambient_prefix("patience", titles, session_id="s-1", listened_last=None)
    )
    assert "listened" not in serve_shelf.ambient_prefix("patience", titles)


# --- brain parity: the offline pack sees what the persona assumes -------------


def _curriculum_dir(tmp_path):
    cur = tmp_path / "curriculum"
    cur.mkdir()
    (cur / "01-anger.md").write_text(
        "# Cluster 1\n\n- **Anger Issues** — https://www.dhammatalks.org/a.html\n"
    )
    (cur / "02-later.md").write_text("# Cluster 2\n\n- later things.\n")
    (cur / "README.md").write_text("machine notes, not for the pack\n")
    return cur


def test_load_curriculum_concatenates_and_skips_readme(tmp_path):
    text = serve_shelf.load_curriculum(_curriculum_dir(tmp_path))
    assert "--- 01-anger.md ---" in text
    assert "--- 02-later.md ---" in text
    assert text.index("01-anger") < text.index("02-later")
    assert "https://www.dhammatalks.org/a.html" in text
    assert "machine notes" not in text
    assert serve_shelf.load_curriculum(tmp_path / "missing") == ""


def test_load_curriculum_truncates_only_when_oversized(tmp_path):
    cur = tmp_path / "curriculum"
    cur.mkdir()
    (cur / "01-big.md").write_text("x" * 9000)
    (cur / "02-big.md").write_text("y" * 9000)
    text = serve_shelf.load_curriculum(cur, cap=8192)
    assert len(text) < 10000
    assert text.count("truncated") == 2
    # Small curricula pass through whole.
    small_dir = tmp_path / "small"
    small_dir.mkdir()
    small = serve_shelf.load_curriculum(_curriculum_dir(small_dir), cap=8192)
    assert "truncated" not in small


def test_ollama_pack_carries_curriculum_and_open_talk_notes():
    payload = serve_shelf.build_ollama_payload(
        [{"role": "user", "content": "what next?"}],
        model="m",
        study="## Studied",
        index="## idx",
        chunks=[("Patience", "chunk text")],
        curriculum="--- 01-anger.md ---\n- **Anger Issues** — https://real.url",
        view_notes="## My takeaways\n- it landed.",
    )
    system = payload["messages"][0]["content"]
    # Knowledge parity: what the claude brain reads itself, the offline
    # brain gets packed in.
    assert "## Curriculum" in system
    assert "https://real.url" in system
    assert "never invent" in system.lower() or "real urls" in system.lower()
    assert "## Notes for the open talk" in system
    assert "- it landed." in system
    # Absent inputs add no empty sections.
    bare = serve_shelf.build_ollama_payload(
        [{"role": "user", "content": "hi"}], model="m"
    )["messages"][0]["content"]
    assert "## Curriculum" not in bare
    assert "## Notes for the open talk" not in bare


# --- watch the guide work: tool events become a narrative ---------------------


def test_parse_stream_line_surfaces_tool_use_blocks():
    line = json.dumps({
        "type": "assistant",
        "session_id": "s-1",
        "message": {"content": [
            {"type": "text", "text": "on it"},
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "uv run tools/fetch_talk.py https://x"}},
        ]},
    })
    parsed = serve_shelf.parse_stream_line(line)
    assert parsed["tools"] == [
        {"name": "Bash", "input": {"command": "uv run tools/fetch_talk.py https://x"}}
    ]
    assert parsed["done"] is False
    # Ordinary events carry an empty list, junk-tolerantly.
    text_line = json.dumps({
        "type": "stream_event", "session_id": "s",
        "event": {"type": "content_block_delta",
                  "delta": {"type": "text_delta", "text": "hi"}},
    })
    assert serve_shelf.parse_stream_line(text_line)["tools"] == []
    junk = json.dumps({"type": "assistant", "message": {"content": "not-a-list"}})
    assert serve_shelf.parse_stream_line(junk)["tools"] == []


def test_tool_progress_line_mapping_matrix():
    line = serve_shelf.tool_progress_line
    assert line("Bash", {"command": "uv run tools/fetch_talk.py https://youtu.be/x"}) == (
        "— fetching the talk… —"
    )
    # Page/mp3 fetches transcribe locally: warn about the wait.
    assert "few minutes" in line(
        "Bash", {"command": "uv run tools/fetch_talk.py https://www.dhammatalks.org/x.html"}
    )
    assert "few minutes" in line(
        "Bash", {"command": "uv run tools/transcribe_talk.py audio.mp3"}
    )
    assert line("Bash", {"command": "uv run tools/speak.py --text hi"}) == (
        "— speaking the primer… —"
    )
    assert line("Bash", {"command": "uv run tools/build_shelf.py"}) == (
        "— rebuilding the shelf… —"
    )
    assert line("Bash", {"command": "uv run tools/search_history.py x"}) == (
        "— searching past conversations… —"
    )
    assert line("Bash", {"command": "ls -la"}) == "— working… —"
    assert line("Write", {"file_path": "library/x/primer.md"}) == "— writing the primer… —"
    assert line("Edit", {"file_path": "library/x/notes.md"}) == "— taking notes… —"
    assert line("Write", {"file_path": "STUDY.md"}) == "— updating the path… —"
    assert line("Write", {"file_path": "library/x/artifacts/t.html"}) == (
        "— building an interactive… —"
    )
    assert line("Write", {"file_path": "journal/2026-07-02.md"}) == (
        "— writing the journal… —"
    )
    assert line("WebSearch", {"query": "x"}) == "— searching the web… —"
    assert line("WebFetch", {"url": "https://x"}) == "— reading a page… —"
    # Reads are noise, not narrative.
    assert line("Read", {"file_path": "x"}) == ""
    assert line("Grep", {"pattern": "x"}) == ""
    # Unknown action-looking tools degrade to the generic line.
    assert line("SomethingNew", {}) == "— working… —"


def test_api_version_reports_shelf_mtime(tmp_path):
    # Pure helper level: the endpoint just wraps this stat.
    shelf = tmp_path / "shelf.html"
    assert serve_shelf.shelf_mtime(tmp_path) == 0
    shelf.write_text("<html>")
    assert serve_shelf.shelf_mtime(tmp_path) == shelf.stat().st_mtime



# --- the hermes brain -----------------------------------------------------
#
# Everything runs against tmp_path files and a fake gateway on an
# EPHEMERAL scratch port (never 8765, never 8642) — the real ~/.hermes is
# never read: every call passes explicit paths/keys or monkeypatches the
# module constants.

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FAKE_SSE = (
    "event: hermes.tool.progress\n"
    'data: {"tool": "mcp_second_arrow_rebuild_shelf"}\n'
    "\n"
    'data: {"choices": [{"delta": {"content": "Hello "}}]}\n'
    "\n"
    'data: {"choices": [{"delta": {"content": "friend."}}]}\n'
    "\n"
    "data: [DONE]\n"
    "\n"
)


def _start_fake_gateway(config):
    """A tiny scriptable hermes gateway: (server, base_url, captured).

    config keys: toolsets (payload), toolsets_status, models (payload),
    sse (str body), chat_statuses (list, consumed one per POST until one
    remains), jobs (the /api/jobs payload). captured["chat"] records each
    chat POST's parsed body + headers; captured["runs"]/"patches" record
    the narrow jobs-API writes the prep proxy is allowed to make.
    """
    captured = {"chat": [], "runs": [], "patches": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: N802 — quiet test server
            pass

        def _json(self, obj, status=200):
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._json({"status": "ok"})
            elif self.path == "/v1/toolsets":
                status = config.get("toolsets_status", 200)
                if status != 200:
                    self.send_error(status)
                    return
                self._json(config.get("toolsets", []))
            elif self.path == "/v1/models":
                self._json(config.get("models", {"data": []}))
            elif self.path == "/api/jobs":
                self._json(config.get("jobs", []))
            else:
                self.send_error(404)

        def do_POST(self):  # noqa: N802
            if self.path.startswith("/api/jobs/") and self.path.endswith("/run"):
                captured["runs"].append(self.path.split("/")[3])
                self._json({})
                return
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            captured["chat"].append({"body": body, "headers": dict(self.headers)})
            statuses = config.setdefault("chat_statuses", [200])
            status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
            if status != 200:
                self.send_error(status)
                return
            payload = config.get("sse", FAKE_SSE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_PATCH(self):  # noqa: N802
            if not self.path.startswith("/api/jobs/"):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            captured["patches"].append(
                {"id": self.path.rsplit("/", 1)[-1], "body": body}
            )
            self._json({})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}", captured


@pytest.fixture
def fake_gateway():
    servers = []

    def start(**config):
        server, base, captured = _start_fake_gateway(config)
        servers.append(server)
        return base, captured

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_parse_env_api_key_reads_only_the_key_line():
    text = "# comment\nAPI_SERVER_ENABLED=true\nAPI_SERVER_KEY=s3cret\nAPI_SERVER_PORT=8642\n"
    assert serve_shelf.parse_env_api_key(text) == "s3cret"
    assert serve_shelf.parse_env_api_key("API_SERVER_ENABLED=true\n") == ""
    assert serve_shelf.parse_env_api_key("") == ""


def test_hermes_api_key_env_wins_then_profile_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("API_SERVER_KEY=from-file\n")
    monkeypatch.setenv("HERMES_API_KEY", "from-env")
    assert serve_shelf.hermes_api_key(env_path=env_file) == "from-env"
    monkeypatch.delenv("HERMES_API_KEY")
    assert serve_shelf.hermes_api_key(env_path=env_file) == "from-file"
    # A missing file is "" — never an exception, never a write.
    assert serve_shelf.hermes_api_key(env_path=tmp_path / "absent.env") == ""


def test_parse_model_default_shapes():
    mapping = "plugins: {}\nmodel:\n  default: gpt-5.5\n  provider: openai-codex\n"
    assert serve_shelf.parse_model_default(mapping) == "gpt-5.5"
    quoted = 'model:\n  default: "gemma4:12b"\n'
    assert serve_shelf.parse_model_default(quoted) == "gemma4:12b"
    # The fresh-install sentinel and plain absence both read as unset.
    assert serve_shelf.parse_model_default('model: ""\n') is None
    assert serve_shelf.parse_model_default("agent:\n  x: 1\n") is None
    assert serve_shelf.parse_model_default("") is None


def test_hermes_default_model_reads_the_given_path_only(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("model:\n  default: gpt-5.5\n  provider: openai-codex\n")
    assert serve_shelf.hermes_default_model(config_path=config) == "gpt-5.5"
    assert serve_shelf.hermes_default_model(config_path=tmp_path / "nope.yaml") is None


def test_parse_hermes_routes_reads_root_and_degrades():
    payload = {
        "data": [
            {"id": "second-arrow", "object": "model"},  # the profile entry
            {"id": "deep", "root": "gpt-5.5"},
            {"id": "local", "root": "gemma4:12b"},
            {"id": "junk"},  # no root: not a route
            "garbage",
        ]
    }
    assert serve_shelf.parse_hermes_routes(payload, profile="second-arrow") == [
        {"alias": "deep", "model": "gpt-5.5"},
        {"alias": "local", "model": "gemma4:12b"},
    ]
    # No routes configured / older gateway / alien shapes: empty, quietly.
    assert serve_shelf.parse_hermes_routes({"data": [{"id": "second-arrow"}]}) == []
    assert serve_shelf.parse_hermes_routes({"unexpected": 1}) == []
    assert serve_shelf.parse_hermes_routes(None) == []


def test_iter_sse_events_frames_and_unterminated_tail():
    lines = [
        b"event: hermes.tool.progress",
        b'data: {"tool": "x"}',
        b"",
        b"data: part one",
        b"data: part two",
        b"",
        b"data: [DONE]",  # no trailing blank line: still yielded
    ]
    events = list(serve_shelf.iter_sse_events(lines))
    assert events == [
        {"event": "hermes.tool.progress", "data": '{"tool": "x"}'},
        {"event": "message", "data": "part one\npart two"},
        {"event": "message", "data": "[DONE]"},
    ]


def test_parse_hermes_sse_event_text_tool_done_and_errors():
    parse = serve_shelf.parse_hermes_sse_event
    text = parse(
        {"event": "message", "data": '{"choices": [{"delta": {"content": "hi"}}]}'}
    )
    assert text == {"text": "hi", "tool": None, "done": False}
    done = parse({"event": "message", "data": "[DONE]"})
    assert done["done"] is True and done["text"] is None
    finish = parse(
        {"event": "message", "data": '{"choices": [{"delta": {}, "finish_reason": "stop"}]}'}
    )
    assert finish["done"] is True
    # The custom tool event, in its tolerated spellings.
    for spelling in (
        '{"tool": "mcp_second_arrow_speak"}',
        '{"tool_name": "mcp_second_arrow_speak"}',
        '{"name": "mcp_second_arrow_speak"}',
        '{"tool": {"name": "mcp_second_arrow_speak"}}',
    ):
        event = parse({"event": "hermes.tool.progress", "data": spelling})
        assert event["tool"] == "mcp_second_arrow_speak", spelling
    # Unknown shapes parse to nothing; garbled JSON is skipped, not fatal.
    assert parse({"event": "hermes.tool.progress", "data": '{"x": 1}'})["tool"] is None
    assert parse({"event": "message", "data": "{not json"}) == {
        "text": None,
        "tool": None,
        "done": False,
    }
    with pytest.raises(ValueError):
        parse({"event": "message", "data": '{"error": {"message": "boom"}}'})


def test_hermes_tool_progress_line_maps_our_mcp_tools():
    line = serve_shelf.hermes_tool_progress_line
    assert line("mcp_second_arrow_fetch_talk") == "— fetching the talk… —"
    assert line("mcp_second_arrow_rebuild_shelf") == "— rebuilding the shelf… —"
    assert line("mcp_second_arrow_update_path") == "— updating the path… —"
    assert line("mcp_second_arrow_update_notes") == "— taking notes… —"
    assert line("mcp_second_arrow_append_journal") == "— writing the journal… —"
    # Reads are noise, not narrative — and clarify speaks for itself.
    assert line("mcp_second_arrow_read_transcript") == ""
    assert line("mcp_second_arrow_get_library_index") == ""
    assert line("clarify") == ""
    # Unknown tools degrade to the generic line.
    assert line("mcp_second_arrow_mystery") == "— working… —"


WIRED_PROFILE_CONFIG = (
    "mcp_servers:\n  second_arrow:\n    command: uv\n"
    "platform_toolsets:\n  api_server:\n    - mcp-second_arrow\n    - clarify\n"
)


@pytest.fixture
def wired_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(WIRED_PROFILE_CONFIG)
    return config


def test_check_hermes_wired_gate_open_with_routes(fake_gateway, wired_config):
    base, _ = fake_gateway(
        toolsets=[{"name": "clarify"}],
        models={"data": [{"id": "second-arrow"}, {"id": "deep", "root": "gpt-5.5"}]},
    )
    wired, reason, routes = serve_shelf.check_hermes_wired(
        base=base, api_key="k", config_path=wired_config
    )
    assert wired is True and reason is None
    assert routes == [{"alias": "deep", "model": "gpt-5.5"}]


def test_check_hermes_wired_ignores_disabled_toolsets(fake_gateway, wired_config):
    # The gateway lists every built-in toolset with enabled flags; a
    # locked-down profile shows them all disabled. Only enabled ones
    # count against the gate — and mcp-second_arrow NEVER appears in
    # /v1/toolsets (built-ins/plugins only), so its absence is fine.
    base, _ = fake_gateway(
        toolsets={
            "object": "list",
            "data": [
                {"name": "web", "enabled": False},
                {"name": "terminal", "enabled": False},
                {"name": "browser", "enabled": False},
                {"name": "clarify", "enabled": True},
            ],
        },
    )
    wired, reason, _ = serve_shelf.check_hermes_wired(
        base=base, api_key="k", config_path=wired_config
    )
    assert wired is True and reason is None


def test_check_hermes_wired_requires_mcp_wiring_in_the_profile_config(
    fake_gateway, tmp_path
):
    # /v1/toolsets can't attest MCP presence, so the gate reads the
    # profile config: server registered + toolset pinned. Anything less
    # means the guide would have no hands — refuse and name the fix.
    base, _ = fake_gateway(toolsets={"data": [{"name": "clarify", "enabled": True}]})
    unwired = tmp_path / "config.yaml"
    unwired.write_text("model:\n  default: gpt-5.5\n")
    wired, reason, routes = serve_shelf.check_hermes_wired(
        base=base, api_key="k", config_path=unwired
    )
    assert wired is False
    assert "mcp" in reason.lower() and "wire_hermes_profile" in reason
    assert routes == []
    # A missing config file reads the same way.
    wired, reason, _ = serve_shelf.check_hermes_wired(
        base=base, api_key="k", config_path=tmp_path / "absent.yaml"
    )
    assert wired is False and "wire_hermes_profile" in reason


def test_check_hermes_wired_refuses_an_over_provisioned_gateway(
    fake_gateway, wired_config
):
    base, _ = fake_gateway(
        toolsets=[{"name": "terminal"}, {"name": "web"}, {"name": "clarify"}],
    )
    wired, reason, routes = serve_shelf.check_hermes_wired(
        base=base, api_key="k", config_path=wired_config
    )
    assert wired is False
    assert "over-provisioned" in reason
    assert "terminal" in reason and "web" in reason
    assert routes == []


def test_check_hermes_wired_unreachable_and_bad_key(fake_gateway):
    # Unreachable: a port nothing listens on (bound then closed).
    import socket

    probe_socket = socket.socket()
    probe_socket.bind(("127.0.0.1", 0))
    dead_port = probe_socket.getsockname()[1]
    probe_socket.close()
    wired, reason, _ = serve_shelf.check_hermes_wired(
        base=f"http://127.0.0.1:{dead_port}", api_key="k"
    )
    assert wired is False and "unreachable" in reason
    # A refused key names the fix, not just the failure.
    base, _ = fake_gateway(toolsets_status=401)
    wired, reason, _ = serve_shelf.check_hermes_wired(base=base, api_key="bad")
    assert wired is False and "HERMES_API_KEY" in reason


def test_hermes_status_shape_and_cache(monkeypatch):
    calls = {"n": 0}

    def fake_check(base=None, api_key=None):
        calls["n"] += 1
        return True, None, [{"alias": "deep", "model": "gpt-5.5"}]

    monkeypatch.setattr(serve_shelf, "check_hermes_wired", fake_check)
    monkeypatch.setattr(serve_shelf, "hermes_default_model", lambda config_path=None: "gpt-5.5")
    monkeypatch.setitem(serve_shelf._HERMES_STATUS_CACHE, "value", None)
    status = serve_shelf.hermes_status(force=True)
    assert status == {
        "wired": True,
        "reason": None,
        "profile": "second-arrow",
        "model": "gpt-5.5",
        "routes": [{"alias": "deep", "model": "gpt-5.5"}],
    }
    # Within the TTL the verdict is cached; force re-checks now.
    assert serve_shelf.hermes_status() is status
    assert calls["n"] == 1
    serve_shelf.hermes_status(force=True)
    assert calls["n"] == 2


def test_resolve_brain_hermes_unavailable_names_the_ritual():
    available = {"claude": True, "ollama": True, "hermes": False}
    with pytest.raises(serve_shelf.BrainError) as error:
        serve_shelf.resolve_brain("hermes", "claude", available)
    assert error.value.status == 503
    message = error.value.message
    assert "wire_hermes_profile.py" in message
    assert "gateway restart" in message
    assert "hermes_probe.py" in message


def test_stream_hermes_sends_only_the_new_message_with_session_header(fake_gateway):
    base, captured = fake_gateway()
    messages = [
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "what did he say about the eggs?"},
    ]
    stream = serve_shelf.stream_hermes(
        messages, "ep-1", prefix="[session: ep-1]", base=base, api_key="k"
    )
    reply = "".join(stream)
    # The narrative line and the streamed text, through our chunked protocol.
    assert "— rebuilding the shelf… —" in reply
    assert "Hello friend." in reply.replace("\n", "")
    request = captured["chat"][0]
    # Continuity is the gateway's: ONLY the new message travels (body
    # history is ignored server-side when the session header is present).
    assert request["body"]["messages"] == [
        {"role": "user", "content": "[session: ep-1]\n\nwhat did he say about the eggs?"}
    ]
    assert request["body"]["stream"] is True
    assert "model" not in request["body"]  # no alias picked: omitted
    assert request["headers"].get("X-Hermes-Session-Id") == "shelf-ep-1"
    assert request["headers"].get("Authorization") == "Bearer k"


def test_stream_hermes_carries_the_route_alias_as_model(fake_gateway):
    base, captured = fake_gateway()
    stream = serve_shelf.stream_hermes(
        [{"role": "user", "content": "hi"}],
        "ep-2",
        model_alias="deep",
        base=base,
        api_key="k",
    )
    "".join(stream)
    assert captured["chat"][0]["body"]["model"] == "deep"


def test_stream_hermes_retries_a_429_with_backoff(fake_gateway, monkeypatch):
    monkeypatch.setattr(serve_shelf, "HERMES_BACKOFF", 0.01)
    base, captured = fake_gateway(chat_statuses=[429, 429, 200])
    stream = serve_shelf.stream_hermes(
        [{"role": "user", "content": "hi"}], "ep-3", base=base, api_key="k"
    )
    reply = "".join(stream)
    assert "Hello" in reply
    assert len(captured["chat"]) == 3  # two 429s, then the served turn


def test_stream_hermes_gives_up_after_persistent_429(fake_gateway, monkeypatch):
    monkeypatch.setattr(serve_shelf, "HERMES_BACKOFF", 0.01)
    base, _ = fake_gateway(chat_statuses=[429])
    with pytest.raises(serve_shelf.BrainError) as error:
        serve_shelf.stream_hermes(
            [{"role": "user", "content": "hi"}], "ep-4", base=base, api_key="k"
        )
    assert error.value.status == 503
    assert "capacity" in error.value.message


def test_stream_hermes_error_stream_keeps_calm_and_apologises(fake_gateway):
    base, _ = fake_gateway(
        sse='data: {"error": {"message": "boom"}}\n\n'
    )
    stream = serve_shelf.stream_hermes(
        [{"role": "user", "content": "hi"}], "ep-5", base=base, api_key="k"
    )
    reply = "".join(stream)
    assert "out of reach" in reply


def test_stream_hermes_without_a_key_is_a_clean_503(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setattr(serve_shelf, "HERMES_PROFILE_DIR", tmp_path)  # no .env
    with pytest.raises(serve_shelf.BrainError) as error:
        serve_shelf.stream_hermes([{"role": "user", "content": "hi"}], "ep-6")
    assert error.value.status == 503
    assert "HERMES_API_KEY" in error.value.message


def test_stream_hermes_serializes_turns_within_one_episode():
    # The per-episode lock is the serialization: same id, same lock.
    lock_a = serve_shelf._hermes_turn_lock("ep-same")
    lock_b = serve_shelf._hermes_turn_lock("ep-same")
    lock_c = serve_shelf._hermes_turn_lock("ep-other")
    assert lock_a is lock_b
    assert lock_a is not lock_c


def test_ax_wired_is_presence_only(tmp_path):
    assert serve_shelf.ax_wired(tmp_path) is False
    (tmp_path / ".ax").mkdir()
    (tmp_path / ".ax" / "tokens.json").write_text('{"token": "SECRET"}')
    assert serve_shelf.ax_wired(tmp_path) is True  # a boolean, never the tokens


def test_load_prep_marker_reads_the_cron_setup_marker(tmp_path):
    assert serve_shelf.load_prep_marker(tmp_path) is None
    (tmp_path / ".prep-cron.json").write_text(
        '{"installed_at": "2026-07-02T03:00:00+00:00", "schedule": "23 3 * * *"}'
    )
    assert serve_shelf.load_prep_marker(tmp_path) == {
        "installed_at": "2026-07-02T03:00:00+00:00",
        "schedule": "23 3 * * *",
    }
    (tmp_path / ".prep-cron.json").write_text("not json")
    assert serve_shelf.load_prep_marker(tmp_path) is None


# --- the nightly-prep proxy: ONE named job, three narrow actions -----------


PREP_JOB = {
    "name": "nightly-prep",
    "id": "j1",
    "schedule": "23 3 * * *",
    "model": "gpt-5.5",
    "provider": "openai-codex",
    "enabled": True,
    "prompt": "the whole prompt never reaches the page",
}


def test_find_prep_job_tolerates_wrapper_shapes():
    jobs = [{"name": "Nightly-Prep", "id": 7, "schedule": "23 3 * * *"}]
    assert serve_shelf.find_prep_job(jobs)["id"] == "7"
    assert serve_shelf.find_prep_job({"jobs": jobs})["id"] == "7"
    assert serve_shelf.find_prep_job({"data": jobs})["id"] == "7"
    assert serve_shelf.find_prep_job([{"name": "other", "id": 1}]) is None
    assert serve_shelf.find_prep_job("garbage") is None


def test_prep_job_view_is_a_narrow_slice():
    # The page sees schedule/model/provider/enabled — never the prompt.
    assert serve_shelf.prep_job_view(PREP_JOB) == {
        "name": "nightly-prep",
        "schedule": "23 3 * * *",
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "enabled": True,
    }
    assert serve_shelf.prep_job_view({"enabled": False})["enabled"] is False
    assert serve_shelf.prep_job_view({})["enabled"] is True  # absent = on


def test_prep_status_unwired_and_missing(fake_gateway):
    assert serve_shelf.prep_status(False) == {"wired": False, "found": False}
    base, _ = fake_gateway(jobs=[])
    assert serve_shelf.prep_status(True, base=base, api_key="k") == {
        "wired": True,
        "found": False,
    }


def test_prep_status_reads_the_one_job(fake_gateway):
    base, _ = fake_gateway(jobs=[PREP_JOB])
    status = serve_shelf.prep_status(True, base=base, api_key="k")
    assert status["wired"] and status["found"] and status["id"] == "j1"
    assert status["job"]["model"] == "gpt-5.5"
    assert "prompt" not in status["job"]


def test_prep_actions_round_trip_against_the_gateway(fake_gateway):
    base, captured = fake_gateway(jobs=[PREP_JOB])
    result = serve_shelf.run_prep_action("run", True, base=base, api_key="k")
    assert result == {"ok": True, "action": "run", "id": "j1"}
    assert captured["runs"] == ["j1"]
    pause = serve_shelf.run_prep_action("pause", True, base=base, api_key="k")
    assert pause["enabled"] is False
    resume = serve_shelf.run_prep_action("resume", True, base=base, api_key="k")
    assert resume["enabled"] is True
    assert captured["patches"] == [
        {"id": "j1", "body": {"enabled": False}},
        {"id": "j1", "body": {"enabled": True}},
    ]


def test_prep_action_unwired_is_a_503_unknown_a_400():
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.run_prep_action("run", False)
    assert excinfo.value.status == 503
    assert "wire" in excinfo.value.message
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.run_prep_action("erase-everything", True)
    assert excinfo.value.status == 400


def test_prep_action_missing_job_is_a_404_naming_the_setup(fake_gateway):
    base, _ = fake_gateway(jobs=[])
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.run_prep_action("run", True, base=base, api_key="k")
    assert excinfo.value.status == 404
    assert "hermes_cron_setup" in excinfo.value.message


def test_prep_action_without_a_key_is_a_clean_503(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setattr(serve_shelf, "HERMES_PROFILE_DIR", tmp_path)  # no .env
    with pytest.raises(serve_shelf.BrainError) as excinfo:
        serve_shelf.run_prep_action("run", True, base="http://127.0.0.1:1")
    assert excinfo.value.status == 503
    assert "key" in excinfo.value.message.lower()


# --- env overrides: the whole surface can point at a scratch copy ----------


def _load_fresh_module(monkeypatch, **env):
    """A fresh serve_shelf instance with env set BEFORE the module loads —
    the constants under test are read at import time."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("serve_shelf_fresh", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_second_arrow_root_env_points_every_path_at_the_override(
    tmp_path, monkeypatch
):
    module = _load_fresh_module(monkeypatch, SECOND_ARROW_ROOT=str(tmp_path))
    root = tmp_path.resolve()
    assert module.REPO_ROOT == root
    assert module.LIBRARY == root / "library"
    assert module.CHAT_DIR == root / "library" / ".chat"
    assert module.SESSIONS_DIR == root / "library" / ".chat" / "sessions"
    assert module.STATE_PATH == root / "library" / ".chat" / "state.json"
    assert module.LISTENING_PATH == root / "library" / ".listening.jsonl"


def test_without_the_root_env_the_repo_itself_is_the_root(monkeypatch):
    monkeypatch.delenv("SECOND_ARROW_ROOT", raising=False)
    module = _load_fresh_module(monkeypatch)
    assert module.REPO_ROOT == MODULE_PATH.parents[1]
    assert module.LIBRARY == MODULE_PATH.parents[1] / "library"


def test_ollama_url_env_override_and_default(monkeypatch):
    module = _load_fresh_module(monkeypatch, OLLAMA_URL="http://127.0.0.1:1")
    assert module.OLLAMA_URL == "http://127.0.0.1:1"
    monkeypatch.delenv("OLLAMA_URL")
    module = _load_fresh_module(monkeypatch)
    assert module.OLLAMA_URL == "http://localhost:11434"


# --- unheard: an append-only retraction, latest entry wins --------------------


def test_last_listened_latest_entry_wins_across_retractions():
    entries = [
        {"slug": "patience", "at": "2026-07-01T10:00:00+00:00", "retract": False},
        {"slug": "patience", "at": "2026-07-02T10:00:00+00:00", "retract": True},
    ]
    # The newest word is a retraction: not heard.
    assert serve_shelf.last_listened(entries, "patience") is None
    # A listen after the retraction counts again.
    entries.append(
        {"slug": "patience", "at": "2026-07-03T10:00:00+00:00", "retract": False}
    )
    assert (
        serve_shelf.last_listened(entries, "patience") == "2026-07-03T10:00:00+00:00"
    )


def test_record_unheard_appends_retraction_and_notes(tmp_path):
    library = _listening_library(tmp_path)
    serve_shelf.record_listened(library, "patience", at="2026-07-01T10:00:00+00:00")
    ok = serve_shelf.record_unheard(library, "patience", at="2026-07-02T10:00:00+00:00")
    assert ok is True
    entries = serve_shelf.load_listening(library / ".listening.jsonl")
    # Append-only: the listen stays, the retraction rides after it.
    assert entries == [
        {"slug": "patience", "at": "2026-07-01T10:00:00+00:00", "retract": False},
        {"slug": "patience", "at": "2026-07-02T10:00:00+00:00", "retract": True},
    ]
    assert serve_shelf.last_listened(entries, "patience") is None
    notes = (library / "patience" / "notes.md").read_text()
    assert "- flagged to revisit — 2026-07-02" in notes
    # The heard state can come BACK: a later listen records fresh (the
    # dedupe window keys off the retracted state, which reads not-heard).
    assert serve_shelf.record_listened(
        library, "patience", at="2026-07-02T10:30:00+00:00"
    )


def test_record_unheard_without_a_listen_is_a_no_op(tmp_path):
    library = _listening_library(tmp_path)
    assert serve_shelf.record_unheard(library, "patience") is False
    assert not (library / ".listening.jsonl").exists()
    with pytest.raises(ValueError):
        serve_shelf.record_unheard(library, "../evil")
    with pytest.raises(ValueError):
        serve_shelf.record_unheard(library, "not-a-talk")


def test_mark_unheard_rebuilds_and_returns_state(tmp_path):
    library = _markable_library(tmp_path)
    serve_shelf.mark_listened(library, "patience", at="2026-07-01T10:00:00+00:00")
    assert "listened ✓" in (library / "shelf.html").read_text()
    state = serve_shelf.mark_unheard(
        library, "patience", at="2026-07-02T10:00:00+00:00"
    )
    assert state["ok"] is True
    assert state["retracted"] is True
    assert state["last"] is None
    assert state["shelf_mtime"] == serve_shelf.shelf_mtime(library)
    # The rebuilt card reads not-heard again: the manual door is back.
    shelf = (library / "shelf.html").read_text()
    assert "listened ✓" not in shelf
    assert 'class="mark-heard"' in shelf
    # Idempotent: retracting an already-not-heard talk changes nothing.
    again = serve_shelf.mark_unheard(library, "patience")
    assert again["ok"] is True and again["retracted"] is False


# --- done / reopen: the server moves the path itself ---------------------------

DONE_PATH_STUDY = """# Study Memory

## Where we are
- Root cluster.

## Studied
- **Old Talk** — what landed: kindness.

## Queued
- **Patience (Thanissaro Bhikkhu)** — next up,
  a wrapped continuation line.
- **Far Talk** — after that.

## Open questions
- What is the second arrow?
"""


def test_mark_done_on_path_moves_queued_to_studied():
    new_text, changed = serve_shelf.mark_done_on_path(DONE_PATH_STUDY, "Patience")
    assert changed is True
    # The wrapped item left the queue whole...
    assert "next up" not in new_text
    assert "wrapped continuation" not in new_text
    # ...and landed in Studied with the not-yet-discussed note, after
    # the items already there.
    studied = new_text.split("## Studied")[1].split("## Queued")[0]
    assert "- **Patience** — (done for now — not yet discussed)" in studied
    assert studied.index("Old Talk") < studied.index("Patience")
    # The four-section shape survives, other content untouched.
    for heading in ("## Where we are", "## Studied", "## Queued", "## Open questions"):
        assert heading in new_text
    assert "- **Far Talk** — after that." in new_text
    assert "What is the second arrow?" in new_text


def test_mark_done_on_path_is_idempotent_and_tolerant():
    once, _ = serve_shelf.mark_done_on_path(DONE_PATH_STUDY, "Patience")
    twice, changed = serve_shelf.mark_done_on_path(once, "Patience")
    assert changed is False and twice == once
    # Matching is normalize_title's: the STUDY.md spelling with the
    # teacher parenthetical meets the INDEX.md display title.
    _, changed = serve_shelf.mark_done_on_path(once, "Patience | Thanissaro Bhikkhu")
    assert changed is False
    # A talk on neither list is appended to Studied — done is done.
    text, changed = serve_shelf.mark_done_on_path(DONE_PATH_STUDY, "Surprise Talk")
    assert changed is True
    assert "- **Surprise Talk** — (done for now — not yet discussed)" in (
        text.split("## Studied")[1].split("## Queued")[0]
    )
    # Empty text starts from the four-section skeleton.
    text, changed = serve_shelf.mark_done_on_path("", "Patience")
    assert changed is True
    for heading in ("## Where we are", "## Studied", "## Queued", "## Open questions"):
        assert heading in text


def test_mark_reopened_on_path_is_the_exact_inverse():
    done_text, _ = serve_shelf.mark_done_on_path(DONE_PATH_STUDY, "Patience")
    reopened, changed = serve_shelf.mark_reopened_on_path(
        done_text, "Patience", date_str="2026-07-02"
    )
    assert changed is True
    queued = reopened.split("## Queued")[1].split("## Open questions")[0]
    assert "- **Patience** — (reopened 2026-07-02)" in queued
    assert "Patience" not in reopened.split("## Studied")[1].split("## Queued")[0]
    # Idempotent: already queued is unchanged.
    again, changed = serve_shelf.mark_reopened_on_path(reopened, "Patience")
    assert changed is False and again == reopened
    # Reopening a talk that isn't done is a clean no-op — nothing to move.
    same, changed = serve_shelf.mark_reopened_on_path(DONE_PATH_STUDY, "Mystery")
    assert changed is False and same == DONE_PATH_STUDY


def test_mark_done_records_moves_and_rebuilds(tmp_path):
    library = _markable_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(DONE_PATH_STUDY)
    state = serve_shelf.mark_done(library, "patience")
    assert state["ok"] is True
    assert state["recorded"] is True  # no listen existed: one recorded
    assert state["moved"] is True
    assert state["last"] is not None
    assert state["shelf_mtime"] == serve_shelf.shelf_mtime(library)
    study = (tmp_path / "STUDY.md").read_text()
    assert "- **Patience** — (done for now — not yet discussed)" in study
    assert "next up" not in study
    # The rebuilt shelf already shows the ✓ (no guide involved anywhere).
    shelf = (library / "shelf.html").read_text()
    assert '<span class="nav-state nav-done">✓</span>' in shelf
    assert "listened ✓" in shelf


def test_mark_done_is_idempotent_and_respects_existing_listens(tmp_path):
    library = _markable_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(DONE_PATH_STUDY)
    serve_shelf.mark_listened(library, "patience", at="2026-07-01T10:00:00+00:00")
    state = serve_shelf.mark_done(library, "patience")
    # Heard already: the listen is NOT re-recorded, only the path moves.
    assert state["recorded"] is False and state["moved"] is True
    assert state["last"] == "2026-07-01T10:00:00+00:00"
    entries = serve_shelf.load_listening(library / ".listening.jsonl")
    assert len(entries) == 1
    study_after_first = (tmp_path / "STUDY.md").read_text()
    # Second click: nothing changes anywhere, the answer stays ok.
    again = serve_shelf.mark_done(library, "patience")
    assert again["ok"] is True
    assert again["recorded"] is False and again["moved"] is False
    assert (tmp_path / "STUDY.md").read_text() == study_after_first
    with pytest.raises(ValueError):
        serve_shelf.mark_done(library, "no-such-talk")


def test_mark_reopen_moves_studied_back_to_queued(tmp_path):
    library = _markable_library(tmp_path)
    (tmp_path / "STUDY.md").write_text(DONE_PATH_STUDY)
    serve_shelf.mark_done(library, "patience")
    state = serve_shelf.mark_reopen(library, "patience")
    assert state["ok"] is True and state["moved"] is True
    assert state["shelf_mtime"] == serve_shelf.shelf_mtime(library)
    study = (tmp_path / "STUDY.md").read_text()
    queued = study.split("## Queued")[1].split("## Open questions")[0]
    assert re.search(r"- \*\*Patience\*\* — \(reopened \d{4}-\d{2}-\d{2}\)", queued)
    # The rebuilt sidebar reads → again for it, and the listen survives —
    # reopening questions the path, not the hearing.
    shelf = (library / "shelf.html").read_text()
    assert '<span class="nav-state nav-next">→</span>' in shelf
    assert serve_shelf.last_listened(
        serve_shelf.load_listening(library / ".listening.jsonl"), "patience"
    )
    # Idempotent / not-done: clean no-ops.
    again = serve_shelf.mark_reopen(library, "patience")
    assert again["ok"] is True and again["moved"] is False
    with pytest.raises(ValueError):
        serve_shelf.mark_reopen(library, "../evil")


# --- stopping a turn: the kill switch --------------------------------------


def test_turn_handle_runs_closers_once_and_late_attaches_immediately():
    handle = serve_shelf.TurnHandle()
    killed = []
    handle.attach(lambda: killed.append("first"))
    assert handle.stopped is False
    assert handle.stop() is True
    assert killed == ["first"]
    # Stop is one-shot...
    assert handle.stop() is False
    assert killed == ["first"]
    # ...and a transport opened AFTER the stop dies immediately (the
    # ollama tool loop opens a new stream per round).
    handle.attach(lambda: killed.append("late"))
    assert killed == ["first", "late"]


def test_turn_handle_tolerates_broken_closers():
    handle = serve_shelf.TurnHandle()
    ran = []

    def boom():
        raise OSError("already gone")

    handle.attach(boom)
    handle.attach(lambda: ran.append("ok"))
    assert handle.stop() is True  # one dead transport never blocks the rest
    assert ran == ["ok"]


def test_turn_registry_stops_only_the_live_handle():
    sid = "stop-test-session"
    assert serve_shelf.stop_turn(sid) is False  # nothing in flight
    handle = serve_shelf.register_turn(sid)
    assert serve_shelf.stop_turn(sid) is True
    assert handle.stopped is True
    assert serve_shelf.stop_turn(sid) is False  # already stopped
    serve_shelf.release_turn(sid, handle)
    assert serve_shelf.stop_turn(sid) is False
    # Releasing a superseded handle never evicts the newer one.
    first = serve_shelf.register_turn(sid)
    second = serve_shelf.register_turn(sid)
    serve_shelf.release_turn(sid, first)
    assert serve_shelf.stop_turn(sid) is True and second.stopped
    serve_shelf.release_turn(sid, second)
    assert serve_shelf.stop_turn(sid) is False


def test_stop_turn_rejects_junk_sessions():
    assert serve_shelf.stop_turn(None) is False
    assert serve_shelf.stop_turn("") is False
    assert serve_shelf.stop_turn(123) is False
