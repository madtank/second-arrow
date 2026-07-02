# Browser-level e2e tests

Real Chromium (Playwright) driving a real `serve_shelf` app on an
**ephemeral** port, against a **scratch** study space. This is the durable
home for the browser checks earlier iterations hand-rolled in scratchpads —
UI behavior gets a failing test here FIRST, then the fix.

## Run

```sh
# the default run stays the fast unit suite (e2e deselected via pytest.ini):
uv run --with pytest --with fastapi --with mlx-whisper pytest tools/tests/ -q

# the e2e suite (opt-in):
uv run --with pytest --with fastapi --with uvicorn --with playwright \
  --with mlx-whisper pytest tools/tests -m e2e -v
```

If Chromium is missing (`playwright._impl._errors` about the executable):

```sh
uv run --with playwright playwright install chromium
```

## The TDD loop

1. **Write the failing e2e test first.** One behavior per test, named for
   the behavior (`test_version_poll_reloads_an_idle_page`), in
   `test_shelf_e2e.py` (or a new `test_*.py` beside it — everything under
   this directory is auto-marked `e2e` by `conftest.py`).
2. Run it, watch it fail for the right reason.
3. Change `build_shelf.py` / `serve_shelf.py` (unit tests first for any
   pure logic), watch the e2e test pass.
4. Run BOTH suites before calling it done.

## Fixtures (conftest.py)

- `scratch_library` — a throwaway study-space root: the SAME library
  shape the unit tests render (`tools/tests/shelf_fixtures.py` — extend
  it there, don't fork it), plus STUDY.md, curriculum/, a real playable
  silent WAV, and an artifact carrying the `second-arrow:seek`
  postMessage contract.
- `shelf_server` (session) — a fresh `serve_shelf` module loaded with
  `SECOND_ARROW_ROOT` / `OLLAMA_URL` / `HERMES_URL` / `HERMES_PROFILE_DIR`
  pointed at scratch copies, running under uvicorn on `127.0.0.1:0`.
  Its brains are fakes: a stub `claude` CLI first on PATH (canned
  stream-json; marker phrases "please rebuild" and "take me to the
  curriculum" select its behaviors), a fake Ollama, a wired fake hermes
  gateway. `shelf_server.rebuild_shelf()` regenerates the scratch
  shelf.html.
- `ghost_hermes_server` — a second shelf whose hermes gateway is
  unreachable, for not-wired UI states.
- `page` — a headless Chromium page in a fresh context per test
  (clean localStorage), launched with autoplay enabled so
  `audio.play()` is deterministic.

## Hard rules

- **Ephemeral ports only.** Never 8765 (the production shelf) and never
  8642 (the hermes gateway). `start_shelf_server` asserts this.
- **Scratch dirs only.** Never the real `library/`, `STUDY.md`,
  `journal/`, or `~/.hermes`. The server module is loaded fresh with the
  env overrides so the real paths aren't even reachable.
- **Deterministic over patient.** Use the page's own hooks
  (`window.saIsPlaying`, `saPlayingSlug`, `saExecuteCue`, DOM classes)
  and `wait_for_function` / `wait_for_selector` with timeouts — no
  arbitrary sleeps over 500ms, no retry loops around flaky assertions.
  If a check is flaky headless, make the page observable instead.
- **Keep the default run fast.** New e2e tests must stay behind the
  `e2e` marker (automatic under this directory); the unit suite must
  keep passing unchanged.
