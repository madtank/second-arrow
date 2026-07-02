"""Tests for tools/wire_hermes_profile.py — the user-run profile wiring.

Everything runs against a temp profile dir (main(profile=...) or the
SECOND_ARROW_HERMES_PROFILE env override) — the real ~/.hermes is never
touched.
"""

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "wire_hermes_profile.py"


def _load():
    spec = importlib.util.spec_from_file_location("wire_hermes_profile", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


wire = _load()

# A fresh clone's config, condensed to the blocks the script touches.
FRESH_CONFIG = """toolsets:
  - hermes-cli
  - web
plugins:
  disabled: []
  enabled:
    - ax-platform
agent:
  disabled_toolsets: []
model:
  api_key: ollama
  base_url: http://127.0.0.1:11434/v1
  default: gemma4:12b
  provider: ollama-launch

# ── Fallback Model
fallback: {}
"""

# A config wired by the PRE-hardening script: MCP registered, toolsets
# pinned for api_server/cli — but no sampling, no cron row, no routes.
LEGACY_WIRED = """toolsets:
  - mcp-second_arrow
  - clarify
plugins:
  disabled:
    - ax-platform
  enabled: []
agent:
  disabled_toolsets:
    - terminal
    - file
model:
  default: gpt-5.5
  provider: openai-codex

mcp_servers:
  second_arrow:
    command: "uv"
    args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]
    tools:
      include:
        - fetch_talk
      prompts: false
      resources: false

platform_toolsets:
  api_server:
    - mcp-second_arrow
    - clarify
  cli:
    - mcp-second_arrow
    - clarify
"""


def _profile(tmp_path, config_text):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "config.yaml").write_text(config_text)
    return profile


def test_fresh_wiring_includes_the_hardening(tmp_path, capsys):
    profile = _profile(tmp_path, FRESH_CONFIG)
    wire.main(profile=profile)
    text = (profile / "config.yaml").read_text()
    # The original steps still land.
    assert "toolsets:\n  - mcp-second_arrow\n  - clarify\n" in text
    assert "disabled:\n    - ax-platform" in text
    assert "model:\n  default: gpt-5.5\n  provider: openai-codex\n" in text
    assert "mcp_servers:" in text
    # The hardening: sampling off, cron pinned, routes defined.
    assert "sampling:\n      enabled: false" in text
    assert "cron:\n    - mcp-second_arrow" in text
    assert "model_routes:" in text
    assert "deep:\n          model: gpt-5.5\n          provider: openai-codex" in text
    assert (
        "local:\n          model: gemma4:12b\n          provider: custom\n"
        "          base_url: http://localhost:11434/v1" in text
    )
    # The API server .env, keyed and locked down.
    env_text = (profile / ".env").read_text()
    assert "API_SERVER_ENABLED=true" in env_text
    assert "API_SERVER_PORT=8642" in env_text
    assert "API_SERVER_HOST=127.0.0.1" in env_text
    assert (profile / ".env").stat().st_mode & 0o777 == 0o600
    # A timestamped backup of the config was left behind.
    assert list(profile.glob("config.yaml.bak-*")) or list(
        profile.glob("*.yaml.bak-*")
    )


def test_wiring_is_idempotent(tmp_path, capsys):
    profile = _profile(tmp_path, FRESH_CONFIG)
    wire.main(profile=profile)
    first = (profile / "config.yaml").read_text()
    first_env = (profile / ".env").read_text()
    capsys.readouterr()
    wire.main(profile=profile)
    out = capsys.readouterr().out
    assert "config.yaml already wired — no changes" in out
    assert ".env already has API_SERVER_ENABLED — untouched" in out
    assert (profile / "config.yaml").read_text() == first
    assert (profile / ".env").read_text() == first_env


def test_legacy_wired_config_gains_only_the_hardening(tmp_path):
    profile = _profile(tmp_path, LEGACY_WIRED)
    (profile / ".env").write_text("API_SERVER_ENABLED=true\nAPI_SERVER_KEY=old\n")
    wire.main(profile=profile)
    text = (profile / "config.yaml").read_text()
    # sampling lands right under the second_arrow args line.
    assert (
        'args: ["run", "/Users/jacob/Git/second-arrow/tools/mcp_second_arrow.py"]\n'
        "    sampling:\n      enabled: false\n" in text
    )
    # cron joins the existing platform_toolsets block, once.
    assert text.count("cron:\n    - mcp-second_arrow") == 1
    assert "platform_toolsets:\n  cron:\n    - mcp-second_arrow\n  api_server:" in text
    # routes appended once; the untouched .env kept its key.
    assert text.count("model_routes:") == 1
    assert (profile / ".env").read_text().count("API_SERVER_KEY") == 1
    # And a second run changes nothing further.
    wire.main(profile=profile)
    assert (profile / "config.yaml").read_text() == text


def test_existing_platforms_block_is_not_clobbered(tmp_path, capsys):
    config = LEGACY_WIRED + "\nplatforms:\n  api_server:\n    extra: {}\n"
    profile = _profile(tmp_path, config)
    (profile / ".env").write_text("API_SERVER_ENABLED=true\n")
    wire.main(profile=profile)
    text = (profile / "config.yaml").read_text()
    # Never a duplicate top-level platforms: key — hand-merge instead.
    assert text.count("\nplatforms:") == 1
    assert "model_routes:" not in text
    assert "merge the" in capsys.readouterr().err


def test_missing_profile_is_a_clear_exit(tmp_path):
    with pytest.raises(SystemExit) as error:
        wire.main(profile=tmp_path / "nope")
    assert "Profile config not found" in str(error.value)


def test_profile_env_override_is_honored(tmp_path, monkeypatch):
    profile = _profile(tmp_path, FRESH_CONFIG)
    monkeypatch.setenv("SECOND_ARROW_HERMES_PROFILE", str(profile))
    fresh = _load()  # PROFILE is resolved at import
    assert fresh.PROFILE == profile
    fresh.main()  # no explicit profile: the env override carries it
    assert "model_routes:" in (profile / "config.yaml").read_text()


def test_helpers_are_no_ops_on_already_hardened_text():
    text = wire.MCP_BLOCK + wire.ROUTES_BLOCK
    for helper in (wire.add_sampling_off, wire.add_cron_pinning, wire.add_model_routes):
        new, did = helper(text)
        assert did is False
        assert new == text
