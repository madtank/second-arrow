import importlib.util
import json
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


def test_ollama_tools_cover_the_six_reviewed_hands():
    names = {tool["function"]["name"] for tool in serve_shelf.OLLAMA_TOOLS}
    assert names == {
        "fetch_talk", "rebuild_shelf", "speak", "search_history",
        "write_artifact", "update_session_summary",
    }
    for name in ("search_history", "write_artifact", "update_session_summary"):
        assert name in serve_shelf.TOOL_PROGRESS
        assert name in serve_shelf.AGENCY_TOOLS_NOTE


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
