"""Tests for tools/hermes_probe.py — the bridge brain's startup gate.

Pure parts only: parsing the /v1/toolsets payload shapes and the
set-comparison verdict. The live GETs are exercised by running the probe
against a real Hermes gateway, not here.
"""

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "hermes_probe.py"
SPEC = importlib.util.spec_from_file_location("hermes_probe", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(probe)


# --- parse_toolsets: tolerate the payload shapes the docs leave open ---------


def test_parse_toolsets_plain_list_of_strings():
    assert probe.parse_toolsets(["mcp-second_arrow", "clarify"]) == {
        "mcp-second_arrow",
        "clarify",
    }


def test_parse_toolsets_wrapped_in_a_toolsets_key():
    payload = {"toolsets": ["mcp-second_arrow", "terminal"]}
    assert probe.parse_toolsets(payload) == {"mcp-second_arrow", "terminal"}


def test_parse_toolsets_object_items_use_name_or_id():
    payload = {
        "toolsets": [
            {"name": "mcp-second_arrow", "tools": ["fetch_talk"]},
            {"id": "clarify"},
        ]
    }
    assert probe.parse_toolsets(payload) == {"mcp-second_arrow", "clarify"}


def test_parse_toolsets_data_wrapper_and_junk_items():
    payload = {"data": ["web", {"name": "file"}, 42, {"nope": "x"}, ""]}
    assert probe.parse_toolsets(payload) == {"web", "file"}
    assert probe.parse_toolsets({"unexpected": True}) == set()
    assert probe.parse_toolsets(None) == set()


# --- excess_toolsets: the actual gate ----------------------------------------


def test_excess_toolsets_subset_is_empty():
    allowed = {"mcp-second_arrow", "clarify"}
    assert probe.excess_toolsets({"mcp-second_arrow"}, allowed) == []
    assert probe.excess_toolsets(set(), allowed) == []
    assert probe.excess_toolsets(allowed, allowed) == []


def test_excess_toolsets_lists_the_excess_sorted():
    allowed = {"mcp-second_arrow", "clarify"}
    exposed = {"terminal", "mcp-second_arrow", "file", "web"}
    assert probe.excess_toolsets(exposed, allowed) == ["file", "terminal", "web"]


def test_allowed_set_is_our_mcp_toolset_plus_clarify_only():
    # mcp-second_arrow: the toolset Hermes derives from our MCP server
    # (docs: "Each configured MCP server generates a mcp-<server> toolset").
    # clarify: asks the user questions, touches nothing (docs: "performs
    # user inquiries without resource consumption"). Nothing else.
    assert probe.ALLOWED_TOOLSETS == frozenset({"mcp-second_arrow", "clarify"})
