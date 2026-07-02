"""Browser-level e2e tests for the served shelf.

Each test drives real Chromium against a real serve_shelf app on an
ephemeral port (see conftest.py: scratch library, stub claude, fake
ollama/hermes gateways). One behavior per test; hooks and polls, never
blind sleeps. Run:

    uv run --with pytest --with fastapi --with uvicorn --with playwright \
      --with mlx-whisper pytest tools/tests -m e2e -v
"""

import json
import os
import time
import urllib.request

import pytest

pytestmark = pytest.mark.e2e

AUDIO_JS = 'document.querySelector(\'audio.talk-audio[data-slug="quiet-mind"]\')'


def _get(base: str, path: str):
    """(status, headers, body) for one GET against the live server.

    headers is the HTTPMessage itself — case-insensitive lookups, the
    way header names must be compared."""
    with urllib.request.urlopen(base + path, timeout=30) as response:
        return response.status, response.headers, response.read()


def _chat(base: str, text: str, session: str | None = None):
    """(x_session, reply_text) for one POST /api/chat turn."""
    body: dict = {"messages": [{"role": "user", "content": text}]}
    if session:
        body["session"] = session
    request = urllib.request.Request(
        base + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.headers.get("X-Session"), response.read().decode()


def _open_shelf(page, base: str, hash_: str = ""):
    """Load the shelf and wait for served mode (the chat panel unhides
    once /health answers — everything else is wired by then too)."""
    page.goto(base + "/" + hash_)
    page.wait_for_function("() => !document.getElementById('guide-chat').hidden")


def _wait_for_version_baseline(page, base: str, hash_: str = ""):
    """Load the shelf and let the version poller record its baseline
    mtime (the page's first /api/version response, plus a whisker for
    the .then handler)."""
    with page.expect_response(lambda r: r.url.endswith("/api/version")):
        page.goto(base + "/" + hash_)
    page.wait_for_function("() => !document.getElementById('guide-chat').hidden")
    page.wait_for_timeout(200)


def _bump_shelf_mtime(shelf_server):
    stamp = time.time() + 5
    os.utime(shelf_server.library / "shelf.html", (stamp, stamp))


def _send_chat(page, text: str):
    """Open the conversation and send one message through the real form."""
    page.click("#chat-open")
    page.fill("#chat-input", text)
    page.click("#chat-send")


# --- the page itself --------------------------------------------------------


def test_page_loads_and_sidebar_shows_the_path(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # Every library talk is in the sidebar...
    for slug in ("quiet-mind", "far-talk", "demon-story", "bare-yt"):
        assert page.locator(f'#talk-nav a[href="#talk/{slug}"]').count() == 1
    # ...with its STUDY.md state riding inline: ✓ studied, → queued.
    quiet = page.locator('#talk-nav a[href="#talk/quiet-mind"]')
    assert quiet.locator(".nav-state.nav-done").count() == 1
    far = page.locator('#talk-nav a[href="#talk/far-talk"]')
    assert far.locator(".nav-state.nav-next").count() == 1
    # A queued talk not yet fetched appears muted, not clickable.
    assert page.locator("#talk-nav li.nav-unfetched").count() == 1


def test_rooms_navigate_by_hash(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    assert page.locator("#view-home.active").count() == 1
    page.click('#talk-nav a[href="#talk/quiet-mind"]')
    page.wait_for_selector("#talk-quiet-mind.active")
    assert page.evaluate("location.hash") == "#talk/quiet-mind"
    assert page.locator("#view-home.active").count() == 0
    page.evaluate("location.hash = '#curriculum'")
    page.wait_for_selector("#view-curriculum.active")
    # An unknown hash lands safely home.
    page.evaluate("location.hash = '#talk/no-such-talk'")
    page.wait_for_selector("#view-home.active")


def test_begin_here_machinery_card_fills_from_health(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    page.wait_for_selector("#machinery-list li")
    card = page.inner_text("#machinery")
    assert "claude · deep" in card and "ready" in card
    assert "ollama · offline" in card
    # The wired fake gateway + scratch profile: hermes states its model.
    assert "hermes · second-arrow" in card
    assert "wired · gpt-5.5" in card
    assert "aX presence" in card and "not set up" in card
    assert "nightly prep" in card and "not yet scheduled" in card


# --- brain pills ------------------------------------------------------------


def test_brain_pills_reflect_health_and_hermes_routes(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # claude is the server default and the active pill.
    page.wait_for_selector('.brain-pill[data-brain="claude"].brain-active')
    assert not page.locator('.brain-pill[data-brain="ollama"]').is_disabled()
    hermes_pill = page.locator('.brain-pill[data-brain="hermes"]')
    assert not hermes_pill.is_disabled()
    # Picking hermes surfaces the route dropdown: default + two routes.
    hermes_pill.click()
    page.wait_for_selector("#hermes-route:not([hidden])")
    options = page.locator("#hermes-route option").all_inner_texts()
    assert len(options) == 3
    assert "default · gpt-5.5" in options[0]
    assert any("deep · gpt-5.5" in option for option in options)
    assert any("local · gemma4:12b" in option for option in options)


def test_hermes_ghost_when_gateway_unreachable(page, ghost_hermes_server):
    _open_shelf(page, ghost_hermes_server.base)
    pill = page.locator('.brain-pill[data-brain="hermes"]')
    page.wait_for_selector('.brain-pill[data-brain="hermes"][disabled]')
    assert pill.inner_text() == "hermes — not wired"
    # The honest ghost carries the wiring ritual, not a dead button.
    assert "wire_hermes_profile" in pill.get_attribute("title")


# --- chat -------------------------------------------------------------------


def test_chat_message_streams_a_reply_into_the_conversation(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    _send_chat(page, "Where do we begin?")
    # The stub claude's canned greeting lands in the last guide bubble.
    page.wait_for_selector('.chat-msg.chat-guide:has-text("One breath, then we begin")')
    # The user's own words are on the page too.
    assert page.locator('.chat-msg.chat-user:has-text("Where do we begin?")').count() >= 1


def test_chat_tool_use_renders_a_progress_line(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    _send_chat(page, "please rebuild the shelf")
    # The stub emits a Bash(build_shelf) tool_use first: the page lifts it
    # out as a centered system line, then the reply settles beneath it.
    page.wait_for_selector(
        '.chat-msg.chat-system:has-text("— rebuilding the shelf… —")',
        state="attached",
    )
    page.wait_for_selector('.chat-msg.chat-guide:has-text("the shelf is rebuilt")')


def test_chat_session_continuity_across_two_turns(shelf_server):
    # Two default-continuation turns record into ONE episode (X-Session).
    first_sid, first_reply = _chat(shelf_server.base, "hello there")
    assert first_sid
    assert "One breath, then we begin" in first_reply
    second_sid, second_reply = _chat(shelf_server.base, "and again")
    assert second_sid == first_sid
    assert "One breath" in second_reply
    status, _, body = _get(shelf_server.base, f"/api/history?session={first_sid}")
    assert status == 200
    turns = json.loads(body)["turns"]
    contents = [turn["content"] for turn in turns]
    assert "hello there" in contents and "and again" in contents


def test_guide_action_cue_navigates_and_announces(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    _send_chat(page, "take me to the curriculum")
    # The cue executes: hash moves, the room switches, a system line says so.
    page.wait_for_selector(
        '.chat-msg.chat-system:has-text("the guide took you to the curriculum")',
        state="attached",
    )
    assert page.evaluate("location.hash") == "#curriculum"
    page.wait_for_selector("#view-curriculum.active")
    # The cue itself never reaches the reader's eyes.
    bubbles = page.locator(".chat-msg.chat-guide").all_inner_texts()
    assert not any("[[go" in text for text in bubbles)


# --- the self-refreshing shelf ----------------------------------------------


def test_version_poll_reloads_an_idle_page(page, shelf_server):
    _wait_for_version_baseline(page, shelf_server.base)
    page.evaluate("window.__e2e_marker = 1")
    # Idle (docked, no draft, nothing playing): a rebuilt shelf reloads
    # outright on the next poll.
    with page.expect_event("load", timeout=20_000):
        _bump_shelf_mtime(shelf_server)
    assert page.evaluate("window.__e2e_marker") is None  # a REAL reload
    page.wait_for_selector("#views")


def test_version_poll_with_a_draft_holds_the_chip_instead(page, shelf_server):
    shelf = shelf_server.library / "shelf.html"
    original = shelf.read_bytes()
    try:
        _wait_for_version_baseline(page, shelf_server.base)
        page.fill("#chat-input", "half a thought, not yet sent")
        page.evaluate("window.__e2e_marker = 1")
        # A draft makes reload unsafe; the soft refresh can't swap either
        # (the fetched page no longer looks like the shelf) — so the change
        # waits behind the chip.
        shelf.write_text(
            "<!DOCTYPE html><html><body><p>not the shelf</p></body></html>"
        )
        page.wait_for_selector("#fresh-chip:not([hidden])", timeout=20_000)
        assert page.evaluate("window.__e2e_marker") == 1  # no reload happened
        assert page.input_value("#chat-input") == "half a thought, not yet sent"
    finally:
        shelf.write_bytes(original)
    # The chip is the manual door: clicking it reloads now.
    with page.expect_event("load", timeout=15_000):
        page.click("#fresh-chip")
    page.wait_for_selector("#views")


def test_soft_refresh_swaps_new_room_content_under_playing_audio(page, shelf_server):
    _wait_for_version_baseline(page, shelf_server.base, "#talk/quiet-mind")
    # Start the talk playing, then wander to another room — the voice
    # carries across rooms by design.
    page.evaluate(f"{AUDIO_JS}.play()")
    page.wait_for_function("() => window.saIsPlaying && window.saIsPlaying()")
    page.evaluate("location.hash = '#talk/far-talk'")
    page.wait_for_selector("#talk-far-talk.active")
    page.wait_for_function(f"() => !{AUDIO_JS}.paused")
    page.evaluate("window.__e2e_marker = 1")
    # New content lands: an artifact for the OPEN talk, shelf rebuilt.
    artifacts = shelf_server.library / "far-talk" / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "new-practice.html").write_text(
        "<!DOCTYPE html><html><body><h1>New practice</h1></body></html>"
    )
    shelf_server.rebuild_shelf()
    # The soft refresh swaps the fresh room in under the reader...
    page.wait_for_selector(
        '#talk-far-talk .artifact-item[data-name="new-practice.html"]',
        timeout=25_000,
    )
    # ...without a reload, and without touching the playing talk.
    assert page.evaluate("window.__e2e_marker") == 1
    assert page.evaluate("window.saPlayingSlug()") == "quiet-mind"
    assert page.evaluate(f"!{AUDIO_JS}.paused")


# --- listening: transcript and artifact seeks -------------------------------


def test_transcript_click_seeks_the_player(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    page.click("#talk-quiet-mind details:has(.seg-transcript) summary")
    page.click('#talk-quiet-mind .seg[data-start="4.5"]')
    # One seek path: the clicked segment's stamp becomes the position and
    # the talk plays from there.
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4.5) < 0.5; }"
    )
    assert page.evaluate("window.saIsPlaying()")


def test_artifact_iframe_is_sandboxed_behind_the_csp_wall(page, shelf_server):
    # Both artifact routes serve with the no-network CSP + nosniff.
    for route in (
        "/artifacts/quiet-mind/breath-timer.html",
        "/quiet-mind/artifacts/breath-timer.html",
    ):
        status, headers, _ = _get(shelf_server.base, route)
        assert status == 200
        assert headers["Content-Security-Policy"] == shelf_server.module.ARTIFACT_CSP
        assert headers["X-Content-Type-Options"] == "nosniff"
    # The served shelf mounts artifacts as allow-scripts-only iframes —
    # never the same-origin grant.
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    frame = page.wait_for_selector(
        '.artifact-item[data-name="breath-timer.html"] iframe.artifact-frame',
        state="attached",
    )
    assert frame.get_attribute("sandbox") == "allow-scripts"


def test_artifact_seek_postmessage_drives_the_player(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    # The anchored-listening button inside the sandboxed tool posts
    # second-arrow:seek up to the shelf; the parent treats it exactly
    # like a transcript-line click.
    frame = page.frame_locator(
        '.artifact-item[data-name="anchored-listen.html"] iframe.artifact-frame'
    )
    frame.locator("#listen").click()
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4.5) < 0.5; }"
    )
    assert page.evaluate("window.saPlayingSlug()") == "quiet-mind"
