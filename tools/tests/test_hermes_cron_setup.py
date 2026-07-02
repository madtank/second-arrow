"""Tests for tools/hermes_cron_setup.py — the durable nightly-prep job.

The gateway is a fake on an EPHEMERAL scratch port (never 8642, never
8765); the marker path is monkeypatched to tmp_path; the real ~/.hermes
is never read (HERMES_API_KEY is always set or the env_path is explicit).
"""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "hermes_cron_setup.py"
SPEC = importlib.util.spec_from_file_location("hermes_cron_setup", MODULE_PATH)
cron_setup = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(cron_setup)


# --- the job itself -----------------------------------------------------


def test_build_job_is_pinned_scoped_and_silent():
    job = cron_setup.build_job()
    assert job["name"] == "nightly-prep"
    assert job["schedule"] == "23 3 * * *"  # 03:23 daily, 5-field cron
    # Pinned to the deep route's pair — an unpinned job fails closed when
    # the profile default changes (v0.18); never rely on the snapshot.
    assert job["provider"] == "openai-codex"
    assert job["model"] == "gpt-5.5"
    # Exactly our MCP toolset, nothing else, delivered to local files.
    assert job["enabled_toolsets"] == ["mcp-second_arrow"]
    assert job["deliver"] == "local"
    # The prompt keeps the constraints: no unrequested ingests, no
    # overnight artifacts, Queued-only STUDY.md edits, silent delivery.
    prompt = job["prompt"]
    assert "NEVER ingest" in prompt
    assert "single-item" in prompt
    assert "No games, no artifacts" in prompt
    assert "ONLY the Queued" in prompt
    assert prompt.rstrip().endswith("[SILENT].")
    # A talk's basics are primer, notes, AND moments — the per-talk step
    # names all three, with the grounding rule spelled out.
    assert '"## Moments"' in prompt
    assert "3-6 anchored moments" in prompt
    assert '"- mm:ss — why"' in prompt
    assert "grounded in transcript.json" in prompt


def test_find_job_tolerates_the_open_body_shapes():
    find = cron_setup.find_job
    assert find([{"name": "nightly-prep", "id": "abc"}]) == {
        "id": "abc",
        "job": {"name": "nightly-prep", "id": "abc"},
    }
    # Wrappers, alternate id spelling, case-insensitive names.
    assert find({"jobs": [{"name": "Nightly-Prep", "job_id": 7}]})["id"] == "7"
    assert find({"data": [{"name": "other", "id": "x"}]}) is None
    assert find({"unexpected": True}) is None
    assert find(None) is None
    assert find([{"name": "nightly-prep"}]) is None  # no id: not addressable


def test_read_api_key_env_then_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("API_SERVER_KEY=file-key\n")
    monkeypatch.setenv("HERMES_API_KEY", "env-key")
    assert cron_setup.read_api_key(env_path=env_file) == "env-key"
    monkeypatch.delenv("HERMES_API_KEY")
    assert cron_setup.read_api_key(env_path=env_file) == "file-key"
    assert cron_setup.read_api_key(env_path=tmp_path / "absent") == ""


def test_marker_content_shape():
    marker = cron_setup.marker_content(now="2026-07-02T03:00:00+00:00")
    assert marker == {
        "installed_at": "2026-07-02T03:00:00+00:00",
        "schedule": "23 3 * * *",
    }


# --- main: dry-run and the gateway round-trip -----------------------------


def test_dry_run_prints_the_job_json_and_touches_nothing(
    tmp_path, monkeypatch, capsys
):
    marker = tmp_path / ".prep-cron.json"
    monkeypatch.setattr(cron_setup, "MARKER_PATH", marker)
    # A dead URL proves no network happens on --dry-run.
    monkeypatch.setenv("HERMES_URL", "http://127.0.0.1:1")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    assert cron_setup.main(["--dry-run"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == cron_setup.build_job()
    assert not marker.exists()


def _start_fake_jobs_gateway(state):
    """A tiny gateway speaking /health and the /api/jobs family."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: N802
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
            elif self.path == "/api/jobs":
                self._json({"jobs": state["jobs"]})
            else:
                self.send_error(404)

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length)) if length else {}

        def do_POST(self):  # noqa: N802
            if self.path != "/api/jobs":
                self.send_error(404)
                return
            job = self._body()
            state["posts"].append(dict(job))
            # Faithful to the real gateway: POST /api/jobs silently drops
            # provider/model/enabled_toolsets (verified in gateway source).
            for dropped in ("provider", "model", "enabled_toolsets"):
                job.pop(dropped, None)
            job["id"] = f"job-{len(state['jobs']) + 1}"
            state["jobs"].append(job)
            self._json(job)

        def do_PATCH(self):  # noqa: N802
            if not self.path.startswith("/api/jobs/"):
                self.send_error(404)
                return
            job_id = self.path.rsplit("/", 1)[1]
            state["patches"].append({"id": job_id, "body": self._body()})
            self._json({"id": job_id})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def jobs_gateway():
    state = {"jobs": [], "posts": [], "patches": []}
    server, base = _start_fake_jobs_gateway(state)
    yield base, state
    server.shutdown()
    server.server_close()


def test_main_creates_then_updates_one_job_and_marks_it(
    tmp_path, monkeypatch, jobs_gateway, capsys
):
    base, state = jobs_gateway
    marker = tmp_path / ".prep-cron.json"
    monkeypatch.setattr(cron_setup, "MARKER_PATH", marker)
    monkeypatch.setenv("HERMES_URL", base)
    monkeypatch.setenv("HERMES_API_KEY", "k")
    pins = []

    def fake_pin(job_id):
        pins.append(job_id)
        return {**cron_setup.build_job(), "id": job_id}

    monkeypatch.setattr(cron_setup, "_run_pin", fake_pin)
    # First run: no job stored — created, then pinned via the engine
    # (the gateway's REST layer drops the pin fields).
    assert cron_setup.main([]) == 0
    assert len(state["posts"]) == 1
    assert state["posts"][0]["name"] == "nightly-prep"
    assert state["patches"] == []
    assert pins == ["job-1"]
    saved = json.loads(marker.read_text())
    assert saved["schedule"] == "23 3 * * *"
    assert saved["installed_at"]
    # Second run: the job exists — updated in place, never duplicated.
    assert cron_setup.main([]) == 0
    assert len(state["posts"]) == 1
    assert len(state["patches"]) == 1
    assert state["patches"][0]["id"] == "job-1"
    assert state["patches"][0]["body"]["provider"] == "openai-codex"
    assert pins == ["job-1", "job-1"]
    out = capsys.readouterr().out
    assert "created job" in out and "updated job" in out
    assert "pinned" in out


def test_job_is_pinned_truth_table():
    pinned = {
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "enabled_toolsets": ["mcp-second_arrow"],
    }
    assert cron_setup.job_is_pinned(pinned) is True
    assert cron_setup.job_is_pinned({**pinned, "model": None}) is False
    assert cron_setup.job_is_pinned({**pinned, "enabled_toolsets": []}) is False
    assert cron_setup.job_is_pinned({}) is False


def test_pin_argv_targets_the_hermes_engine():
    argv = cron_setup.pin_argv("job-9")
    assert argv[0].endswith("venv/bin/python3")
    assert "update_job" in argv[2]
    assert argv[3] == "job-9"
    updates = json.loads(argv[4])
    assert updates == {
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "enabled_toolsets": ["mcp-second_arrow"],
    }


def test_main_fails_loudly_when_the_pin_does_not_take(
    tmp_path, monkeypatch, jobs_gateway, capsys
):
    base, _ = jobs_gateway
    monkeypatch.setattr(cron_setup, "MARKER_PATH", tmp_path / ".prep-cron.json")
    monkeypatch.setenv("HERMES_URL", base)
    monkeypatch.setenv("HERMES_API_KEY", "k")
    monkeypatch.setattr(cron_setup, "_run_pin", lambda job_id: {"id": job_id})
    assert cron_setup.main([]) == 1
    err = capsys.readouterr().err
    assert "pin" in err.lower()


def test_main_requires_a_key_and_a_gateway(tmp_path, monkeypatch, capsys):
    marker = tmp_path / ".prep-cron.json"
    monkeypatch.setattr(cron_setup, "MARKER_PATH", marker)
    # No key anywhere: a clear failure naming the fix.
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setattr(cron_setup, "PROFILE_ENV", tmp_path / "absent.env")
    assert cron_setup.main([]) == 1
    assert "HERMES_API_KEY" in capsys.readouterr().err
    # A key but no gateway: a clear failure naming the start command.
    monkeypatch.setenv("HERMES_API_KEY", "k")
    monkeypatch.setenv("HERMES_URL", "http://127.0.0.1:1")
    assert cron_setup.main([]) == 1
    assert "gateway start" in capsys.readouterr().err
    assert not marker.exists()
