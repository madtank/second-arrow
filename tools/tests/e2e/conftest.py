"""Fixtures for the browser-level e2e suite.

Everything here runs against a SCRATCH study space (a temp dir shaped by
tools/tests/shelf_fixtures.py plus e2e extras), a real serve_shelf FastAPI
app on an EPHEMERAL 127.0.0.1 port, and fake brains:

    claude  — a stub `claude` CLI on PATH that emits canned stream-json
    ollama  — a tiny HTTP fake answering /api/tags, /api/show, /api/chat
    hermes  — a tiny gateway answering /health, /v1/toolsets, /v1/models,
              /v1/chat/completions (canned SSE, same marker phrases as
              the stub claude — hermes is the default brain when wired),
              and the narrow jobs API (ONE nightly-prep job, runs and
              patches captured)

Hard rules (see README.md here): ephemeral ports only — never 8765 or
8642; never the real library/, STUDY.md, journal/, or ~/.hermes. The
server module is loaded FRESH with SECOND_ARROW_ROOT/OLLAMA_URL/
HERMES_URL/HERMES_PROFILE_DIR pointed at the scratch copies, so nothing
real is even reachable.

Playwright is imported lazily inside fixtures so the default (unit) run
can collect this directory without playwright installed.
"""

import importlib.util
import json
import os
import socket
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
TESTS_DIR = E2E_DIR.parent
TOOLS_DIR = TESTS_DIR.parent


def pytest_collection_modifyitems(items):
    """Everything under tools/tests/e2e/ carries the e2e marker — the
    default run (addopts -m "not e2e") deselects it automatically."""
    for item in items:
        if E2E_DIR in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)


def _load_module(name: str, path: Path):
    """The house importlib-by-path pattern (unique name per load)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


shelf_fixtures = _load_module("shelf_fixtures", TESTS_DIR / "shelf_fixtures.py")
build_shelf = _load_module("build_shelf_e2e", TOOLS_DIR / "build_shelf.py")


# --- the scratch study space -------------------------------------------------

STUDY_MD = """# Study Memory

## Where we are
- Root cluster: anger, aversion, patience.

## Studied
- **Quiet Mind & <Friends>** (Ajahn Test): what landed — kindness wins.

## Queued
- **Far Talk (Ajahn Test)** — next up.
- **Anger Issues (Thanissaro Bhikkhu, 2019)** — not in the library yet.
- **The Arrow (Sallatha Sutta, SN 36:6)** — read alongside.

## Open questions
- What does the second arrow feel like in the body?
"""

CURRICULUM_MD = """# Cluster 1: Anger & the Second Arrow

## Talks

- **Quiet Mind & <Friends> — Ajahn Test** — https://example.org/quiet-mind.html
  Already in the library. Reach for it when the mind is loud.

- **Demon Story — Ajahn Brahm (2011, 56 min)** — https://www.youtube.com/watch?v=me7Wm5LOpx0
  The classic story-rich Brahm talk. Reach for it when you want the
  teaching carried by a story instead of an argument.

- **Anger Issues — Thanissaro Bhikkhu (2019-05-31, morning talk)** — https://www.dhammatalks.org/audio/morning/2019/190531-anger-issues.html
  A short, direct look at working with anger as it arises.
  Reach for it when anger feels righteous.

## The source teaching

- **The Arrow (Sallatha Sutta, SN 36:6) — trans. Thanissaro Bhikkhu** — https://www.dhammatalks.org/suttas/SN/SN36_6.html
  The original two-arrows text. Short. Read it once early, return often.
"""

# The storage-guard artifact: CLAUDE.md's authoring contract in fixture
# form. Inside the sandboxed inline view (allow-scripts, never
# allow-same-origin) any storage access throws SecurityError — a guarded
# store with an in-memory fallback keeps the script alive, and the test
# asserts the content really renders inline.
GUARDED_STORAGE_ARTIFACT = """<!DOCTYPE html>
<html><body>
<h1 id="state">waiting</h1>
<script>
var store = null;
try { store = window.localStorage; } catch (e) { store = null; }
document.getElementById("state").textContent =
  store ? "storage ready" : "guarded: memory only";
</script>
</body></html>
"""

# The anchored-listening artifact: the exact contract CLAUDE.md gives tool
# authors — a "listen from" button posting second-arrow:seek up to the
# shelf, degrading to static text with no parent listening.
SEEK_ARTIFACT = """<!DOCTYPE html>
<html><body>
<h1>Anchored listening</h1>
<button id="listen" type="button">listen from 0:04 — hear it settle</button>
<script>
document.getElementById("listen").addEventListener("click", function () {
  if (window.parent && window.parent !== window) {
    parent.postMessage({type: "second-arrow:seek", start: 4.5,
      label: "hear it settle"}, "*");
  } else {
    document.getElementById("listen").textContent = "0:04 — hear it settle";
  }
});
</script>
</body></html>
"""


def write_silent_wav(path: Path, seconds: float = 10.0) -> None:
    """A real, playable audio file (silence) — Chromium actually decodes
    it, so play/seek/timeupdate behave like a genuine talk recording."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * int(8000 * seconds))


def build_scratch_root(root: Path) -> Path:
    """A realistic throwaway study space around the shared library shape:
    STUDY.md, curriculum/, real (silent) audio, the seek artifact."""
    root.mkdir(parents=True, exist_ok=True)
    library = shelf_fixtures.make_library(root)
    # The unit fixture's 1-byte audio.mp3 can't decode; the browser needs
    # real audio. Same talk, same probe result, playable bytes.
    (library / "quiet-mind" / "audio.mp3").unlink()
    write_silent_wav(library / "quiet-mind" / "audio.wav", seconds=10.0)
    (library / "quiet-mind" / "artifacts" / "anchored-listen.html").write_text(
        SEEK_ARTIFACT
    )
    (library / "quiet-mind" / "artifacts" / "guarded-notes.html").write_text(
        GUARDED_STORAGE_ARTIFACT
    )
    # A SPOKEN reading with its timing map (speak.py's contract:
    # reading.mp3 + reading.segments.json): its text is the seek surface.
    # far-talk must stay text-only — the reading-room tests depend on it.
    (library / "INDEX.md").write_text(
        (library / "INDEX.md").read_text()
        + """
## spoken-reading
- **Title:** Spoken Reading
- **Teacher:** Ajahn Test
- **Source:** https://example.org/spoken-reading.html
- **Themes:** patience
- **Path:** library/spoken-reading/
"""
    )
    spoken = library / "spoken-reading"
    spoken.mkdir(exist_ok=True)
    (spoken / "transcript.md").write_text(
        "# Spoken Reading\n\nQuiet begins. It settles at three.\n"
    )
    # Real wav bytes under the .mp3 name: Chromium's demuxer sniffs the
    # container from content, so the reading player decodes and seeks.
    write_silent_wav(spoken / "reading.mp3", seconds=10.0)
    (spoken / "reading.segments.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "text": "Quiet begins."},
                    {"start": 3.0, "text": "It settles at three."},
                ]
            }
        )
    )
    (root / "STUDY.md").write_text(STUDY_MD)
    (root / "curriculum").mkdir(exist_ok=True)
    (root / "curriculum" / "01-anger.md").write_text(CURRICULUM_MD)
    (root / "journal").mkdir(exist_ok=True)
    return root


def rebuild_scratch_shelf(root: Path) -> Path:
    """Regenerate shelf.html in the scratch library — what a guide-side
    `uv run tools/build_shelf.py` would do, in-process."""
    library = root / "library"
    reach = build_shelf.collect_reach(root / "curriculum")
    output = library / "shelf.html"
    output.write_text(build_shelf.render_shelf(library, reach))
    return output


@pytest.fixture(scope="session")
def scratch_library(tmp_path_factory):
    """The scratch study-space ROOT (root/"library" is the library)."""
    return build_scratch_root(tmp_path_factory.mktemp("second-arrow-root"))


# --- the stub claude CLI -------------------------------------------------

STUB_CLAUDE = '''#!/usr/bin/env python3
"""A canned `claude` CLI for e2e tests: speaks stream-json like the real
one (init event with a session_id, text deltas, a final result event) and
varies its reply on marker phrases in the prompt."""
import json
import sys


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


args = sys.argv[1:]
prompt, resume = "", None
for i, arg in enumerate(args):
    if arg == "-p" and i + 1 < len(args):
        prompt = args[i + 1]
    if arg == "--resume" and i + 1 < len(args):
        resume = args[i + 1]

sid = resume or "stub-thread-1"
emit({"type": "system", "subtype": "init", "session_id": sid})

lowered = prompt.lower()
if "take me to the curriculum" in lowered:
    text = "Let's stand back and see the road ahead. [[go: curriculum]]"
elif "please rebuild" in lowered:
    emit({"type": "assistant", "session_id": sid, "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "uv run tools/build_shelf.py"}}]}})
    text = "Done - the shelf is rebuilt."
else:
    text = "Hello, friend. One breath, then we begin."

for i in range(0, len(text), 12):
    emit({"type": "stream_event", "session_id": sid,
          "event": {"type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": text[i:i + 12]}}})
emit({"type": "result", "session_id": sid, "result": text, "is_error": False})
'''


@pytest.fixture(scope="session")
def stub_bin(tmp_path_factory):
    """A bin dir whose `claude` is the canned stream-json stub."""
    bin_dir = tmp_path_factory.mktemp("stub-bin")
    stub = bin_dir / "claude"
    stub.write_text(STUB_CLAUDE)
    stub.chmod(0o755)
    return bin_dir


# --- fake gateways (ephemeral ports, canned answers) -----------------------


def _start_http(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class _JsonHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: N802 — quiet test server
        pass

    def _json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="session")
def fake_ollama():
    """A minimal Ollama: one tools-capable installed model, canned chat
    (only the non-streamed leave-summary path ever posts here)."""

    class Handler(_JsonHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/api/tags":
                self._json({"models": [{"name": "qwen3:8b", "size": 5_000_000_000}]})
            else:
                self.send_error(404)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            if self.path == "/api/show":
                self._json({"capabilities": ["completion", "tools"]})
            elif self.path == "/api/chat":
                self._json(
                    {
                        "message": {"content": "Title: A test\nSummary: Canned."},
                        "done": True,
                    }
                )
            else:
                self.send_error(404)

    server, base = _start_http(Handler)
    yield base
    server.shutdown()
    server.server_close()


class FakeHermes:
    """The wired fake gateway's handle: its base URL plus what it saw."""

    def __init__(self, base: str, captured: dict):
        self.base = base
        self.captured = captured


def _hermes_sse_reply(prompt: str) -> bytes:
    """Canned hermes SSE with the SAME marker-phrase behaviors as the stub
    claude CLI — hermes is the default brain now, so the chat e2e tests
    stream through this gateway."""
    lowered = prompt.lower()
    frames = []
    if "take me to the curriculum" in lowered:
        text = "Let's stand back and see the road ahead. [[go: curriculum]]"
    elif "please rebuild" in lowered:
        frames.append(
            "event: hermes.tool.progress\n"
            'data: {"tool": "mcp_second_arrow_rebuild_shelf"}\n\n'
        )
        text = "Done - the shelf is rebuilt."
    else:
        text = "Hello, friend. One breath, then we begin."
    for i in range(0, len(text), 12):
        frames.append(
            "data: "
            + json.dumps({"choices": [{"delta": {"content": text[i : i + 12]}}]})
            + "\n\n"
        )
    frames.append("data: [DONE]\n\n")
    return "".join(frames).encode()


@pytest.fixture(scope="session")
def fake_hermes():
    """A wired-looking hermes gateway: /health ok, allowed toolsets only,
    two model routes, a canned chat endpoint (marker-phrase replies), and
    the narrow jobs API the prep proxy uses — ONE nightly-prep job whose
    runs/patches are captured for round-trip assertions."""
    captured = {"chat": [], "runs": [], "patches": []}
    job = {
        "name": "nightly-prep",
        "id": "job-e2e",
        "schedule": "23 3 * * *",
        "model": "gpt-5.5",
        "provider": "openai-codex",
        "enabled": True,
    }

    class Handler(_JsonHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._json({"status": "ok"})
            elif self.path == "/v1/toolsets":
                self._json(["clarify"])  # subset of ALLOWED_TOOLSETS
            elif self.path == "/v1/models":
                self._json(
                    {
                        "data": [
                            {"id": "second-arrow", "object": "model"},
                            {"id": "deep", "root": "gpt-5.5"},
                            {"id": "local", "root": "gemma4:12b"},
                        ]
                    }
                )
            elif self.path == "/api/jobs":
                self._json([job])
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
            messages = body.get("messages") or [{}]
            prompt = str(messages[-1].get("content") or "")
            if "count slowly" in prompt.lower():
                # The slow marker: a genuinely streaming turn (~4s) so the
                # stop button and the busy queue have something to catch.
                # No Content-Length — the client reads until close.
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    for i in range(15):
                        frame = "data: " + json.dumps(
                            {"choices": [{"delta": {"content": f"count {i} "}}]}
                        ) + "\n\n"
                        self.wfile.write(frame.encode())
                        self.wfile.flush()
                        time.sleep(0.25)
                    self.wfile.write(b"data: [DONE]\n\n")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # the shelf stopped the turn: expected
                return
            payload = _hermes_sse_reply(prompt)
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
            job["enabled"] = body.get("enabled", job["enabled"])
            self._json({})

    server, base = _start_http(Handler)
    yield FakeHermes(base, captured)
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def hermes_profile(tmp_path_factory):
    """A scratch profile dir the wired-gate accepts: config.yaml registers
    our MCP server + pins its toolset; .env carries the API key."""
    profile = tmp_path_factory.mktemp("hermes-profile")
    (profile / "config.yaml").write_text(
        "model:\n"
        "  default: gpt-5.5\n"
        "toolsets:\n"
        "  - clarify\n"
        "  - mcp-second_arrow\n"
        "mcp_servers:\n"
        "  second_arrow:\n"
        "    command: uv\n"
    )
    (profile / ".env").write_text("API_SERVER_KEY=e2e-key\n")
    return profile


# --- the shelf server on an ephemeral port ---------------------------------


class ShelfServer:
    """One live serve_shelf app: base URL, its module, its scratch root."""

    def __init__(self, base: str, module, root: Path, uv_server, thread):
        self.base = base
        self.module = module
        self.root = root
        self._uv_server = uv_server
        self._thread = thread

    @property
    def library(self) -> Path:
        return self.root / "library"

    def rebuild_shelf(self) -> Path:
        return rebuild_scratch_shelf(self.root)

    def stop(self) -> None:
        self._uv_server.should_exit = True
        self._thread.join(timeout=10)


def start_shelf_server(root: Path, env: dict) -> ShelfServer:
    """Load a FRESH serve_shelf module with env pointed at scratch copies,
    then run its app on an ephemeral port in a daemon thread.

    env is applied only around the module load (the path/URL constants are
    read at import time) and restored afterwards — except values that must
    stay live for subprocess/probe calls, which the session fixture sets
    itself. Never touches port 8765 (uvicorn binds port 0)."""
    import uvicorn

    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        module = _load_module(f"serve_shelf_e2e_{id(root)}", TOOLS_DIR / "serve_shelf.py")
        assert module.LIBRARY == root / "library", "env override must have taken"
        app = module.create_app("claude", "qwen3")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not uv_server.started:
        if time.time() > deadline or not thread.is_alive():
            raise RuntimeError("shelf server did not start")
        time.sleep(0.05)
    port = uv_server.servers[0].sockets[0].getsockname()[1]
    assert port not in (8765, 8642), "ephemeral ports only"
    return ShelfServer(f"http://127.0.0.1:{port}", module, root, uv_server, thread)


@pytest.fixture(scope="session")
def shelf_server(scratch_library, stub_bin, fake_ollama, fake_hermes, hermes_profile):
    """The session's live shelf: scratch root, stub claude first on PATH
    (live for the whole session — _spawn_claude resolves PATH per call),
    fake ollama + wired fake hermes on ephemeral ports."""
    saved_path = os.environ.get("PATH", "")
    saved_key = os.environ.get("HERMES_API_KEY")
    os.environ["PATH"] = str(stub_bin) + os.pathsep + saved_path
    os.environ["HERMES_API_KEY"] = "e2e-key"
    server = start_shelf_server(
        scratch_library,
        {
            "SECOND_ARROW_ROOT": str(scratch_library),
            "OLLAMA_URL": fake_ollama,
            "HERMES_URL": fake_hermes.base,
            "HERMES_PROFILE_DIR": str(hermes_profile),
        },
    )
    yield server
    server.stop()
    os.environ["PATH"] = saved_path
    if saved_key is None:
        os.environ.pop("HERMES_API_KEY", None)
    else:
        os.environ["HERMES_API_KEY"] = saved_key


@pytest.fixture
def ghost_hermes_server(tmp_path, hermes_profile):
    """A second shelf whose hermes gateway is unreachable — the honest
    'not wired' ghost. Its own scratch root, so the session server's
    shelf.html is never touched."""
    root = build_scratch_root(tmp_path / "ghost-root")
    with socket.socket() as probe:  # a port nothing listens on
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
    server = start_shelf_server(
        root,
        {
            "SECOND_ARROW_ROOT": str(root),
            "OLLAMA_URL": "http://127.0.0.1:1",
            "HERMES_URL": f"http://127.0.0.1:{dead_port}",
            "HERMES_PROFILE_DIR": str(hermes_profile),
        },
    )
    yield server
    server.stop()


# --- the browser -----------------------------------------------------------


@pytest.fixture(scope="session")
def browser():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch(
            # Deterministic media: audio.play() needs no user gesture.
            args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"]
        )
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """A fresh context per test: clean localStorage, no cross-test state."""
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(15_000)
    yield page
    context.close()
