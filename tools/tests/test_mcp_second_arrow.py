"""Tests for tools/mcp_second_arrow.py — the guide's entire world for Hermes.

Only the pure/offline parts are tested here: the tool table (exactly the
expected set — three actions, six reads, three scoped writes), handler
behavior with a stubbed runner, path guards, pagination, and the write
allowlist. The action wall itself is serve_shelf.validate_tool_call,
tested in test_serve_shelf.py — these tests only assert that every action
handler routes through it (same argv, same rejections). The MCP wire
protocol is exercised by the standalone smoke script, not here (the `mcp`
package is deliberately NOT a test dependency: the module must import
without it). Reads/writes run against a temp study space via the
SECOND_ARROW_ROOT override — the real repo is never touched.
"""

import importlib.util
import inspect
import json
import sys
from datetime import date
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "mcp_second_arrow.py"
SPEC = importlib.util.spec_from_file_location("mcp_second_arrow", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mod)

SERVE_SHELF_PATH = Path(__file__).resolve().parents[1] / "serve_shelf.py"
_SS_SPEC = importlib.util.spec_from_file_location("serve_shelf_ref", SERVE_SHELF_PATH)
serve_shelf = importlib.util.module_from_spec(_SS_SPEC)
assert _SS_SPEC and _SS_SPEC.loader
_SS_SPEC.loader.exec_module(serve_shelf)


EXPECTED_TOOLS = {
    # actions (through serve_shelf.validate_tool_call, unchanged)
    "fetch_talk", "rebuild_shelf", "speak",
    # reads (pinned inside the study space)
    "get_path", "get_library_index", "read_transcript", "read_notes",
    "get_curriculum", "search_history",
    # scoped writes (the claude chat brain's allowlist, mirrored)
    "update_path", "update_notes", "append_journal",
}


@pytest.fixture
def space(tmp_path, monkeypatch):
    """A throwaway study space; SECOND_ARROW_ROOT points the module at it."""
    monkeypatch.setenv("SECOND_ARROW_ROOT", str(tmp_path))
    (tmp_path / "library" / "anger-eating-demons").mkdir(parents=True)
    (tmp_path / "library" / "INDEX.md").write_text(
        "## anger-eating-demons\n- teacher: Ajahn Brahm\n"
    )
    (tmp_path / "STUDY.md").write_text("# Study\n\n## Where we are\n\nStarting.\n")
    (tmp_path / "curriculum").mkdir()
    return tmp_path


# --- the tool table: exactly the expected set, no more ----------------------


def test_the_tool_table_is_exactly_the_expected_set():
    assert set(mod.TOOL_HANDLERS) == EXPECTED_TOOLS
    assert len(mod.TOOL_HANDLERS) == len(EXPECTED_TOOLS)
    # The journal is write-only by design: hosted models see what tools
    # return, so no tool reads journal/ back.
    assert not any("journal" in name and name != "append_journal"
                   for name in mod.TOOL_HANDLERS)


def test_root_override_is_read_per_call(tmp_path, monkeypatch):
    monkeypatch.delenv("SECOND_ARROW_ROOT", raising=False)
    default_root = mod.repo_root()
    assert default_root == MODULE_PATH.resolve().parents[1]  # the real repo
    monkeypatch.setenv("SECOND_ARROW_ROOT", str(tmp_path))
    assert mod.repo_root() == tmp_path.resolve()
    monkeypatch.delenv("SECOND_ARROW_ROOT")
    assert mod.repo_root() == default_root


def test_handler_names_match_their_functions():
    for name, handler in mod.TOOL_HANDLERS.items():
        # FastMCP derives the wire tool name from __name__ — keep them honest.
        assert handler.__name__ == name
        assert handler.__doc__, f"{name} needs a docstring (it becomes the schema description)"


def test_handler_signatures_carry_the_expected_parameters():
    fetch = inspect.signature(mod.TOOL_HANDLERS["fetch_talk"])
    assert list(fetch.parameters) == ["url", "title", "teacher", "themes"]
    assert fetch.parameters["url"].default is inspect.Parameter.empty  # required
    for optional in ("title", "teacher", "themes"):
        assert fetch.parameters[optional].default == ""

    rebuild = inspect.signature(mod.TOOL_HANDLERS["rebuild_shelf"])
    assert list(rebuild.parameters) == []

    speak = inspect.signature(mod.TOOL_HANDLERS["speak"])
    assert list(speak.parameters) == ["text", "out_name"]
    assert all(
        p.default is inspect.Parameter.empty for p in speak.parameters.values()
    )


# --- the wall stays serve_shelf's: same argv, same rejections --------------


def _record_runner(ran):
    def runner(argv):
        ran.append(argv)
        return True, f"{argv[2]} succeeded:\nok"

    return runner


def test_fetch_talk_builds_the_same_argv_serve_shelf_would(monkeypatch):
    ran = []
    monkeypatch.setattr(mod, "run_tool", _record_runner(ran))
    args = {
        "url": "https://www.youtube.com/watch?v=abc123",
        "title": "Some Talk",
        "teacher": "Ajahn Brahm",
        "themes": "anger, patience",
    }
    result = mod.TOOL_HANDLERS["fetch_talk"](**args)
    assert ran == [serve_shelf.validate_tool_call("fetch_talk", args)]
    assert "succeeded" in result


def test_fetch_talk_optional_fields_default_to_skipped(monkeypatch):
    ran = []
    monkeypatch.setattr(mod, "run_tool", _record_runner(ran))
    mod.TOOL_HANDLERS["fetch_talk"](url="https://example.org/t")
    assert ran == [["uv", "run", "tools/fetch_talk.py", "https://example.org/t"]]
    assert "--title" not in ran[0]


def test_rebuild_shelf_builds_the_same_argv(monkeypatch):
    ran = []
    monkeypatch.setattr(mod, "run_tool", _record_runner(ran))
    mod.TOOL_HANDLERS["rebuild_shelf"]()
    assert ran == [serve_shelf.validate_tool_call("rebuild_shelf", {})]


def test_speak_builds_the_same_argv(monkeypatch):
    ran = []
    monkeypatch.setattr(mod, "run_tool", _record_runner(ran))
    mod.TOOL_HANDLERS["speak"](text="Breathe out slowly.", out_name="Morning Reflection")
    assert ran == [
        serve_shelf.validate_tool_call(
            "speak", {"text": "Breathe out slowly.", "out_name": "Morning Reflection"}
        )
    ]
    assert ran[0][-1] == "library/morning-reflection.mp3"


def test_validation_errors_come_back_as_messages_not_exceptions(monkeypatch):
    def no_runner(argv):
        raise AssertionError("a rejected call must never reach the runner")

    monkeypatch.setattr(mod, "run_tool", no_runner)
    result = mod.TOOL_HANDLERS["fetch_talk"](url="file:///etc/passwd")
    assert result.startswith("Tool call rejected:")
    result = mod.TOOL_HANDLERS["speak"](text="--engine say", out_name="x")
    assert result.startswith("Tool call rejected:")
    result = mod.TOOL_HANDLERS["speak"](text="hi", out_name="###")
    assert result.startswith("Tool call rejected:")


def test_runner_failure_is_reported_as_text(monkeypatch):
    monkeypatch.setattr(
        mod, "run_tool", lambda argv: (False, "tools/build_shelf.py failed (exit 1):\nboom")
    )
    result = mod.TOOL_HANDLERS["rebuild_shelf"]()
    assert "failed" in result and "boom" in result


# --- run_tool: subprocess, no shell, bounded ---------------------------------


def test_run_tool_success_returns_stdout_tail():
    ok, summary = mod.run_tool([sys.executable, "-c", "print('shelf ready')"])
    assert ok is True
    assert "shelf ready" in summary


def test_run_tool_failure_reports_exit_code_and_stderr():
    ok, summary = mod.run_tool(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]
    )
    assert ok is False
    assert "exit 3" in summary and "boom" in summary


def test_run_tool_timeout_is_bounded():
    ok, summary = mod.run_tool(
        [sys.executable, "-c", "import time; time.sleep(5)"], timeout=1
    )
    assert ok is False
    assert "timed out" in summary


def test_default_timeout_is_600_seconds():
    assert mod.TOOL_TIMEOUT == 600


# --- serve_shelf loads lazily, read-only, by path ----------------------------


def test_load_serve_shelf_exposes_the_wall_and_caches():
    first = mod.load_serve_shelf()
    assert callable(first.validate_tool_call)
    assert mod.load_serve_shelf() is first  # cached: one import per process


# --- reads: pinned inside the study space, messages not exceptions -----------


def test_get_path_and_get_library_index_return_content(space):
    assert "## Where we are" in mod.TOOL_HANDLERS["get_path"]()
    assert "anger-eating-demons" in mod.TOOL_HANDLERS["get_library_index"]()


def test_reads_missing_files_return_not_found_messages(space):
    (space / "STUDY.md").unlink()
    (space / "library" / "INDEX.md").unlink()
    assert "not found" in mod.TOOL_HANDLERS["get_path"]().lower()
    assert "not found" in mod.TOOL_HANDLERS["get_library_index"]().lower()
    assert "no transcript" in mod.TOOL_HANDLERS["read_transcript"]("patience").lower()
    assert "no notes" in mod.TOOL_HANDLERS["read_notes"]("anger-eating-demons").lower()
    assert "no curriculum" in mod.TOOL_HANDLERS["get_curriculum"]().lower()


def test_read_transcript_rejects_bad_slugs_as_messages(space):
    for evil in ("../evil", "UPPER", "a/b", "a b", ".hidden", "", "-lead", "a_b"):
        result = mod.TOOL_HANDLERS["read_transcript"](evil)
        assert "not a valid talk slug" in result, evil
    assert "not a valid talk slug" in mod.TOOL_HANDLERS["read_notes"]("../x")


def test_read_transcript_paginates_with_an_offset_tail(space):
    text = "word " * 4000  # 20,000 chars
    (space / "library" / "anger-eating-demons" / "transcript.md").write_text(text)
    first = mod.TOOL_HANDLERS["read_transcript"]("anger-eating-demons")
    assert first.startswith(text[: mod.PAGE_CHARS])
    assert f"call again with offset={mod.PAGE_CHARS}" in first
    second = mod.TOOL_HANDLERS["read_transcript"](
        "anger-eating-demons", offset=mod.PAGE_CHARS
    )
    assert second.startswith(text[mod.PAGE_CHARS : 2 * mod.PAGE_CHARS])
    assert f"call again with offset={2 * mod.PAGE_CHARS}" in second
    last = mod.TOOL_HANDLERS["read_transcript"](
        "anger-eating-demons", offset=2 * mod.PAGE_CHARS
    )
    assert "call again" not in last  # final page carries no tail
    assert last.rstrip().endswith("word")


def test_read_transcript_offset_bounds_and_limit_cap(space):
    text = "x" * 100
    (space / "library" / "anger-eating-demons" / "transcript.md").write_text(text)
    beyond = mod.TOOL_HANDLERS["read_transcript"]("anger-eating-demons", offset=500)
    assert "past the end" in beyond and "100" in beyond
    clamped = mod.TOOL_HANDLERS["read_transcript"]("anger-eating-demons", offset=-5)
    assert clamped == text  # negative offsets clamp to the start
    # limit can shrink a page but never exceed the cap
    small = mod.TOOL_HANDLERS["read_transcript"]("anger-eating-demons", limit=10)
    assert small.startswith("x" * 10) and "offset=10" in small


def test_get_curriculum_concatenates_sorted_files(space):
    (space / "curriculum" / "02-patience.md").write_text("# Patience next\n")
    (space / "curriculum" / "01-anger.md").write_text("# Anger first\n")
    result = mod.TOOL_HANDLERS["get_curriculum"]()
    assert result.index("Anger first") < result.index("Patience next")
    assert "01-anger.md" in result and "02-patience.md" in result


def test_read_notes_round_trips_with_update_notes(space):
    assert "no notes" in mod.TOOL_HANDLERS["read_notes"]("anger-eating-demons").lower()
    mod.TOOL_HANDLERS["update_notes"]("anger-eating-demons", "## My takeaways\n\n- ok\n")
    assert "My takeaways" in mod.TOOL_HANDLERS["read_notes"]("anger-eating-demons")


# --- search_history: recall over stored sessions ------------------------------


def _write_session(space, sid, title, content):
    sessions = space / "library" / ".chat" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{sid}.jsonl").write_text(
        json.dumps({"role": "user", "content": content, "brain": "claude", "ts": "t"})
        + "\n"
    )
    (sessions / f"{sid}.json").write_text(
        json.dumps({"id": sid, "title": title, "summary": "", "updated": "2026-06-20T10:00:00+00:00"})
    )


def test_search_history_finds_stored_sessions(space):
    _write_session(space, "demons", "Maggots and kindness",
                   "tell me the story about the maggots on the dog")
    result = mod.TOOL_HANDLERS["search_history"]("maggots story")
    assert "Maggots and kindness" in result
    assert "demons" in result


def test_search_history_no_match_and_bad_query(space):
    _write_session(space, "demons", "Maggots and kindness", "maggot story")
    assert "no past conversation" in mod.TOOL_HANDLERS["search_history"]("zzzunknownzzz").lower()
    assert "no past conversation" in mod.TOOL_HANDLERS["search_history"]("").lower()


# --- scoped writes: STUDY.md, journal/**, library/**/notes.md — nothing else --


def test_update_path_replaces_study_md_and_reports(space):
    result = mod.TOOL_HANDLERS["update_path"]("# Study\n\n## Studied\n\n- Demons\n")
    assert "STUDY.md" in result
    assert (space / "STUDY.md").read_text() == "# Study\n\n## Studied\n\n- Demons\n"


def test_update_notes_writes_under_the_talk_dir_only(space):
    result = mod.TOOL_HANDLERS["update_notes"]("anger-eating-demons", "- landed\n")
    assert "notes.md" in result
    written = space / "library" / "anger-eating-demons" / "notes.md"
    assert written.read_text() == "- landed\n"
    # Unknown talk: a message, not a stray directory.
    result = mod.TOOL_HANDLERS["update_notes"]("patience", "- x\n")
    assert "no talk" in result.lower()
    assert not (space / "library" / "patience").exists()
    # Bad slug never touches the filesystem.
    assert "not a valid talk slug" in mod.TOOL_HANDLERS["update_notes"]("../../etc", "x")


def test_append_journal_creates_dated_entry_then_appends(space):
    today = date.today().isoformat()
    first = mod.TOOL_HANDLERS["append_journal"]("Sat with the anger this morning.")
    assert today in first
    entry = space / "journal" / f"{today}.md"
    text = entry.read_text()
    assert text.startswith(f"# {today}\n")
    assert "Sat with the anger" in text
    mod.TOOL_HANDLERS["append_journal"]("Evening: calmer.")
    text = entry.read_text()
    assert text.count(f"# {today}") == 1  # heading only once
    assert text.index("Sat with the anger") < text.index("Evening: calmer.")


def test_writes_land_only_on_the_allowlisted_paths(space):
    today = date.today().isoformat()
    before = {p for p in space.rglob("*") if p.is_file()}
    mod.TOOL_HANDLERS["update_path"]("new study\n")
    mod.TOOL_HANDLERS["update_notes"]("anger-eating-demons", "notes\n")
    mod.TOOL_HANDLERS["append_journal"]("entry\n")
    created_or_touched = {
        str(p.relative_to(space)) for p in space.rglob("*") if p.is_file()
    } - {str(p.relative_to(space)) for p in before if p.exists()}
    assert created_or_touched == {
        f"journal/{today}.md",
        "library/anger-eating-demons/notes.md",
    }  # STUDY.md already existed; nothing else appeared


def test_writes_are_size_capped(space):
    too_big = "x" * (mod.MAX_WRITE_CHARS + 1)
    for call in (
        lambda: mod.TOOL_HANDLERS["update_path"](too_big),
        lambda: mod.TOOL_HANDLERS["update_notes"]("anger-eating-demons", too_big),
        lambda: mod.TOOL_HANDLERS["append_journal"](too_big),
    ):
        result = call()
        assert "rejected" in result.lower() and str(mod.MAX_WRITE_CHARS) in result
    # And nothing was written by the rejected calls.
    assert "x" * 1000 not in (space / "STUDY.md").read_text()


def test_writes_require_plain_strings(space):
    assert "rejected" in mod.TOOL_HANDLERS["update_path"]("").lower()
    assert "rejected" in mod.TOOL_HANDLERS["append_journal"]("   ").lower()


def test_path_guard_refuses_escapes():
    root = Path("/tmp/space")
    assert mod.inside_root(root / "STUDY.md", root)
    assert mod.inside_root(root / "library" / "x" / "notes.md", root)
    assert not mod.inside_root(root / ".." / "evil.md", root)
    assert not mod.inside_root(Path("/etc/passwd"), root)
