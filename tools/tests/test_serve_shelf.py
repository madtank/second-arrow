import importlib.util
from pathlib import Path

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


def test_build_claude_cmd_first_turn():
    cmd = serve_shelf.build_claude_cmd("where am I?")
    assert cmd == ["claude", "-p", "where am I?", "--output-format", "json"]


def test_build_claude_cmd_resume_turn():
    cmd = serve_shelf.build_claude_cmd("and then?", session_id="abc-123")
    assert cmd[:5] == ["claude", "-p", "and then?", "--output-format", "json"]
    assert cmd[5:] == ["--resume", "abc-123"]


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


def test_resolve_ollama_model_prefers_configured_then_falls_back():
    installed = ["llama3.2:latest", "qwen3:latest"]
    assert serve_shelf.resolve_ollama_model("qwen3", installed) == "qwen3:latest"
    assert (
        serve_shelf.resolve_ollama_model("qwen3:latest", installed) == "qwen3:latest"
    )
    assert serve_shelf.resolve_ollama_model("missing", installed) == "llama3.2:latest"
    assert serve_shelf.resolve_ollama_model("qwen3", []) == "qwen3"
