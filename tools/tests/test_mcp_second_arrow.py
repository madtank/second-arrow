"""Tests for tools/mcp_second_arrow.py — the scoped MCP server for Hermes.

Only the pure/offline parts are tested here: the tool table (exactly the
three reviewed tools), and handler behavior with a stubbed runner. The
security wall itself is serve_shelf.validate_tool_call, tested in
test_serve_shelf.py — these tests only assert that every handler routes
through it (same argv, same rejections). The MCP wire protocol is
exercised by the standalone smoke script, not here (the `mcp` package is
deliberately NOT a test dependency: the module must import without it).
"""

import importlib.util
import inspect
import sys
from pathlib import Path

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


# --- the tool table: exactly the three reviewed tools, no more -------------


def test_exactly_three_tools_are_exposed():
    assert set(mod.TOOL_HANDLERS) == {"fetch_talk", "rebuild_shelf", "speak"}
    assert len(mod.TOOL_HANDLERS) == 3
    # search_history exists in serve_shelf's ollama toolset but is NOT
    # exposed to Hermes — the bridge brain gets hands, not memory access.
    assert "search_history" not in mod.TOOL_HANDLERS


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
