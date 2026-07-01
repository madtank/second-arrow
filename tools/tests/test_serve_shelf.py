import importlib.util
import json
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


def test_chat_allowed_tools_covers_exactly_the_memory_scopes():
    rules = serve_shelf.chat_allowed_tools().split(",")
    scopes = ("STUDY.md", "journal/**", "library/**/notes.md", "library/INDEX.md")
    expected = {f"{tool}({scope})" for scope in scopes for tool in ("Edit", "Write")}
    assert set(rules) == expected
    assert len(rules) == len(expected)  # no stray rules
    # Nothing grants Bash or unscoped tools.
    assert all("(" in rule and rule.split("(")[0] in ("Edit", "Write") for rule in rules)


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
    assert serve_shelf.parse_ollama_stream_line(line) == {"text": "gro", "done": False}


def test_parse_ollama_stream_line_final_chunk_is_done():
    line = json.dumps(
        {"model": "qwen3", "message": {"role": "assistant", "content": ""}, "done": True}
    )
    assert serve_shelf.parse_ollama_stream_line(line) == {"text": None, "done": True}


def test_parse_ollama_stream_line_error_raises():
    with pytest.raises(ValueError, match="model not found"):
        serve_shelf.parse_ollama_stream_line(json.dumps({"error": "model not found"}))


def test_parse_ollama_stream_line_blank_is_inert():
    assert serve_shelf.parse_ollama_stream_line("\n") == {"text": None, "done": False}


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


def test_resolve_ollama_model_prefers_configured_then_falls_back():
    installed = ["llama3.2:latest", "qwen3:latest"]
    assert serve_shelf.resolve_ollama_model("qwen3", installed) == "qwen3:latest"
    assert (
        serve_shelf.resolve_ollama_model("qwen3:latest", installed) == "qwen3:latest"
    )
    assert serve_shelf.resolve_ollama_model("missing", installed) == "llama3.2:latest"
    assert serve_shelf.resolve_ollama_model("qwen3", []) == "qwen3"
