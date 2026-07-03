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
    # Queued talks not yet fetched appear muted — but they are real
    # links now: rooms-in-waiting (see the stub-room tests). One talk
    # (Anger Issues) and one reading (The Arrow).
    assert page.locator("#talk-nav li.nav-unfetched a").count() == 2


def test_rooms_navigate_by_hash(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    assert page.locator("#view-home.active").count() == 1
    # quiet-mind is studied — it rests in the archive, so the real user
    # path to its link runs through "show more" first.
    page.click("#nav-archive-toggle")
    page.click('#talk-nav a[href="#talk/quiet-mind"]')
    page.wait_for_selector("#talk-quiet-mind.active")
    assert page.evaluate("location.hash") == "#talk/quiet-mind"
    assert page.locator("#view-home.active").count() == 0
    page.evaluate("location.hash = '#curriculum'")
    page.wait_for_selector("#view-curriculum.active")
    # An unknown hash lands safely home.
    page.evaluate("location.hash = '#talk/no-such-talk'")
    page.wait_for_selector("#view-home.active")


# --- the sidebar archive: show more, remembered ------------------------------


def test_archive_show_more_toggles_and_persists(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # Studied talks start tucked away: the archived entry is attached but
    # hidden until the reader asks for it.
    archived_link = page.locator(
        '#talk-nav li.nav-archived a[href="#talk/quiet-mind"]'
    )
    assert archived_link.count() == 1
    assert not archived_link.is_visible()
    toggle = page.locator("#nav-archive-toggle")
    label = toggle.get_attribute("data-label")
    assert label.startswith("show more · ")
    assert toggle.inner_text() == label
    assert toggle.get_attribute("aria-expanded") == "false"
    # One tap opens the archive and the button says how to close it.
    toggle.click()
    page.wait_for_selector(
        '#talk-nav li.nav-archived a[href="#talk/quiet-mind"]', state="visible"
    )
    assert toggle.inner_text() == "show less"
    assert toggle.get_attribute("aria-expanded") == "true"
    # The choice is remembered (localStorage) across a full reload.
    _open_shelf(page, shelf_server.base)
    page.wait_for_selector(
        '#talk-nav li.nav-archived a[href="#talk/quiet-mind"]', state="visible"
    )
    assert page.inner_text("#nav-archive-toggle") == "show less"
    # And one more tap tucks it back behind its own label.
    page.click("#nav-archive-toggle")
    page.wait_for_selector(
        '#talk-nav li.nav-archived a[href="#talk/quiet-mind"]', state="hidden"
    )
    toggle = page.locator("#nav-archive-toggle")
    assert toggle.inner_text() == toggle.get_attribute("data-label")
    assert toggle.get_attribute("aria-expanded") == "false"


def test_active_archived_talk_expands_archive(page, shelf_server):
    # Landing directly in an archived room pulls the archive open around
    # it — the sidebar never hides the room the reader is standing in.
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    page.wait_for_selector(
        '#talk-nav a[href="#talk/quiet-mind"].active', state="visible"
    )
    assert page.get_attribute("#nav-archive-toggle", "aria-expanded") == "true"
    assert page.inner_text("#nav-archive-toggle") == "show less"


def test_settings_room_carries_the_machinery_card(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # Begin here keeps one quiet pointer; the card itself lives in settings.
    page.wait_for_selector("#machinery:not([hidden])")
    assert "the room's machinery → settings" in page.inner_text("#machinery")
    page.evaluate("location.hash = '#settings'")
    page.wait_for_selector("#view-settings.active")
    page.wait_for_selector("#machinery-list li")
    card = page.inner_text("#machinery-list")
    # Hermes leads — it is the home harness — then the fallbacks.
    assert card.index("hermes · second-arrow") < card.index("claude · deep")
    assert "wired · gpt-5.5" in card
    assert "ollama · offline" in card
    assert "aX presence" in card and "not set up" in card
    assert "nightly prep" in card and "not yet scheduled" in card


# --- the guide's brain: identity line + settings room ------------------------


def test_identity_line_names_hermes_and_opens_settings(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # Wired gateway → hermes is the default; the chat header says so with
    # ONE quiet line (no pills, no dropdowns over the conversation).
    page.wait_for_selector("#chat-identity:not([hidden])")
    assert page.inner_text("#identity-link") == "on Hermes · second-arrow"
    assert page.locator(".brain-pill").count() == 0
    page.click("#identity-link")
    page.wait_for_selector("#view-settings.active")
    # The route rows: default + the two configured routes, all enabled.
    rows = page.locator("#route-rows .pick-row")
    assert rows.count() == 3
    labels = rows.all_inner_texts()
    assert "default · gpt-5.5" in labels[0]
    assert any("deep · gpt-5.5" in label for label in labels)
    assert any("local · gemma4:12b" in label for label in labels)
    assert page.locator("#route-rows input:disabled").count() == 0
    # Exactly one pick across both groups: the hermes default row.
    assert page.locator("#route-rows input").first.is_checked()


def test_route_pick_persists_across_reload(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#settings")
    page.wait_for_selector("#route-rows .pick-row")
    # Pick the deep route — hermes stays the brain, the alias persists.
    page.locator('#route-rows .pick-row:has-text("deep · gpt-5.5") input').check()
    assert page.evaluate('localStorage.getItem("sa-route")') == "deep"
    assert page.evaluate('localStorage.getItem("sa-brain")') == "hermes"
    _open_shelf(page, shelf_server.base, "#settings")
    page.wait_for_selector("#route-rows .pick-row")
    assert page.locator(
        '#route-rows .pick-row:has-text("deep · gpt-5.5") input'
    ).is_checked()


def test_fallback_brain_pick_persists_across_reload(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#settings")
    page.wait_for_selector("#fallback-rows .pick-row")
    page.locator('#fallback-rows .pick-row:has-text("claude · deep") input').check()
    # The one-line note says what just changed; the identity line follows.
    page.wait_for_selector('#fallback-note:not([hidden])')
    assert "the guide answers via claude until you switch back" in page.inner_text(
        "#fallback-note"
    )
    assert page.inner_text("#identity-link") == "on claude"
    assert page.evaluate('localStorage.getItem("sa-brain")') == "claude"
    _open_shelf(page, shelf_server.base)
    page.wait_for_selector("#chat-identity:not([hidden])")
    assert page.inner_text("#identity-link") == "on claude"
    page.evaluate("location.hash = '#settings'")
    page.wait_for_selector("#view-settings.active")
    assert page.locator(
        '#fallback-rows .pick-row:has-text("claude · deep") input'
    ).is_checked()


def test_unwired_gateway_is_an_honest_ghost(page, ghost_hermes_server):
    _open_shelf(page, ghost_hermes_server.base)
    # No saved pick: the server's default falls to claude and the identity
    # line says why.
    page.wait_for_selector("#chat-identity:not([hidden])")
    assert page.inner_text("#identity-link") == "on claude — hermes not wired"
    page.evaluate("location.hash = '#settings'")
    page.wait_for_selector("#view-settings.active")
    page.wait_for_selector("#route-rows .pick-row")
    # The route rows are disabled ghosts and the wiring ritual is visible.
    assert page.locator("#route-rows input:not(:disabled)").count() == 0
    assert page.inner_text("#hermes-wired-state") == "not wired"
    page.wait_for_selector("#hermes-unwired:not([hidden])")
    assert "wire_hermes_profile" in page.inner_text("#hermes-unwired")


def test_saved_hermes_pick_falls_back_out_loud_and_survives(
    page, ghost_hermes_server
):
    _open_shelf(page, ghost_hermes_server.base)
    page.evaluate('localStorage.setItem("sa-brain", "hermes")')
    page.reload()
    page.wait_for_function("() => !document.getElementById('guide-chat').hidden")
    # The fallback is visible, never silent: one quiet system line.
    page.wait_for_selector(
        '.chat-msg.chat-system:has-text("hermes isn\'t reachable — using claude for now")',
        state="attached",
    )
    assert page.inner_text("#identity-link") == "on claude — hermes not wired"
    # The stored pick stays put — hermes returns by itself once wired.
    assert page.evaluate('localStorage.getItem("sa-brain")') == "hermes"


def test_sidebar_arrow_opens_the_sidebar_in_conversation_mode(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # Collapse the sidebar, then open the conversation overlay.
    page.click("#sidebar-collapse")
    page.wait_for_selector("#sidebar-reopen", state="visible")
    page.click("#chat-open")
    page.wait_for_selector("#guide-chat.chat-conversation")
    # The fletched arrow is still visible above the overlay — and works.
    assert page.locator("#sidebar-reopen").is_visible()
    page.click("#sidebar-reopen")
    page.wait_for_function(
        "() => !document.body.classList.contains('sidebar-collapsed')"
    )
    # A living-path link proves the sidebar is really back (quiet-mind
    # now rests in the collapsed archive, so it can't be the witness).
    assert page.locator('#talk-nav a[href="#talk/far-talk"]').is_visible()
    # Picking a talk navigates AND docks the chat — browsing wins.
    page.click('#talk-nav a[href="#talk/far-talk"]')
    page.wait_for_selector("#talk-far-talk.active")
    page.wait_for_selector("#guide-chat.chat-docked")


def test_prep_run_now_round_trips_to_the_gateway(page, shelf_server, fake_hermes):
    _open_shelf(page, shelf_server.base, "#settings")
    page.wait_for_selector("#set-prep:not([hidden])")
    # The job reads honestly: schedule · pinned model · state.
    page.wait_for_selector('#prep-line:has-text("23 3 * * *")')
    assert "gpt-5.5" in page.inner_text("#prep-line")
    runs_before = len(fake_hermes.captured["runs"])
    page.click("#prep-run")
    # The confirmation line lands and the gateway really saw the run.
    page.wait_for_selector('#prep-feedback:has-text("started")')
    assert fake_hermes.captured["runs"][runs_before:] == ["job-e2e"]


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


def _newer_than_the_shelf(shelf_server) -> float:
    """A stamp strictly newer than shelf.html, however fresh it is."""
    shelf = shelf_server.library / "shelf.html"
    return max(time.time(), shelf.stat().st_mtime) + 1


def test_rewritten_artifact_remounts_in_place(page, shelf_server):
    # The guide REWRITES an existing artifact (same filename) and does
    # NOT rebuild: /api/version notices the media outran the page,
    # freshens it server-side, and the soft refresh remounts the iframe
    # with a new ?v= stamp — new content, no navigation.
    _wait_for_version_baseline(page, shelf_server.base, "#talk/quiet-mind")
    frame_sel = '.artifact-item[data-name="breath-timer.html"] iframe.artifact-frame'
    page.wait_for_selector(frame_sel, state="attached")
    old_src = page.get_attribute(frame_sel, "src")
    page.fill("#chat-input", "half a thought")  # reload is now unsafe
    page.evaluate("window.__e2e_marker = 1")
    artifact = shelf_server.library / "quiet-mind" / "artifacts" / "breath-timer.html"
    artifact.write_text(
        "<!DOCTYPE html><html><body><h1>Fresh breath</h1></body></html>"
    )
    stamp = _newer_than_the_shelf(shelf_server)
    os.utime(artifact, (stamp, stamp))
    page.wait_for_function(
        "(old) => {"
        f" const f = document.querySelector('{frame_sel}');"
        " return f && f.getAttribute('src') !== old"
        "   && f.getAttribute('src').includes('?v='); }",
        arg=old_src,
        timeout=25_000,
    )
    # The remounted document really shows the NEW draft...
    page.locator(frame_sel).scroll_into_view_if_needed()  # lazy iframes load in view
    frame = page.frame_locator(frame_sel)
    from playwright.sync_api import expect

    expect(frame.locator("h1")).to_have_text("Fresh breath")
    # ...and nothing else moved: no reload, the draft untouched.
    assert page.evaluate("window.__e2e_marker") == 1
    assert page.input_value("#chat-input") == "half a thought"


def test_respoken_primer_restamps_the_player_in_place(page, shelf_server):
    # Re-spoken audio (primer.mp3 rewritten, no rebuild): the freshened
    # page carries a new ?v= stamp, the swap replaces the player node,
    # and the room comes back fully wired.
    _wait_for_version_baseline(page, shelf_server.base, "#talk/quiet-mind")
    primer_sel = '#talk-quiet-mind audio[src*="primer.mp3"]'
    old_src = page.get_attribute(primer_sel, "src")
    page.fill("#chat-input", "still drafting")  # reload is now unsafe
    page.evaluate("window.__e2e_marker = 1")
    primer = shelf_server.library / "quiet-mind" / "primer.mp3"
    primer.write_bytes(b"\x00\x00")  # the re-spoken take
    stamp = _newer_than_the_shelf(shelf_server)
    os.utime(primer, (stamp, stamp))
    page.wait_for_function(
        "(old) => {"
        f" const a = document.querySelector('{primer_sel}');"
        " return a && a.getAttribute('src') !== old"
        "   && a.getAttribute('src').includes('?v='); }",
        arg=old_src,
        timeout=25_000,
    )
    assert page.evaluate("window.__e2e_marker") == 1  # no reload
    # The swapped-in room is still wired: a transcript click seeks the
    # (also restamped) talk player through the ONE seek path.
    page.click("#talk-quiet-mind details.full-transcript summary")
    page.click('#talk-quiet-mind .seg[data-start="4.5"]')
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4.5) < 0.5; }"
    )


# --- listening: transcript and artifact seeks -------------------------------


def test_transcript_click_seeks_the_player(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    # The segmented transcript sits behind the quiet sub-expander now.
    page.click("#talk-quiet-mind details.full-transcript summary")
    page.click('#talk-quiet-mind .seg[data-start="4.5"]')
    # One seek path: the clicked segment's stamp becomes the position and
    # the talk plays from there.
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4.5) < 0.5; }"
    )
    assert page.evaluate("window.saIsPlaying()")


def test_transcript_opens_to_moments_first(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    # The Transcript block opens onto the curated moments; the segmented
    # transcript waits behind its own closed sub-expander.
    chip = page.wait_for_selector(
        '#talk-quiet-mind .moments[data-slug="quiet-mind"] .moment-chip'
    )
    assert not page.is_visible('#talk-quiet-mind .seg[data-start="4.5"]')
    assert not page.evaluate(
        "document.querySelector('#talk-quiet-mind details.full-transcript').open"
    )
    # The chip still seeks — exactly a transcript-line click.
    chip.click()
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4) < 0.5; }"
    )
    # Behind the sub-expander, the full transcript is all still there.
    page.click("#talk-quiet-mind details.full-transcript summary")
    page.wait_for_selector('#talk-quiet-mind .seg[data-start="4.5"]')


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


def test_guarded_storage_artifact_renders_inline_under_the_sandbox(page, shelf_server):
    # CLAUDE.md's storage contract, locked into the suite: under the
    # sandbox (no allow-same-origin) the storage getter throws — an
    # artifact that reaches storage THROUGH a guard keeps its script
    # alive and renders real content inline instead of dying silently.
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    frame_sel = '.artifact-item[data-name="guarded-notes.html"] iframe.artifact-frame'
    page.wait_for_selector(frame_sel, state="attached")
    page.locator(frame_sel).scroll_into_view_if_needed()  # lazy iframes load in view
    from playwright.sync_api import expect

    expect(page.frame_locator(frame_sel).locator("#state")).to_have_text(
        "guarded: memory only"
    )


# --- done for now: the manual heard door and the path's primary action -------


def test_expanded_artifact_keeps_the_seek_channel_and_the_chat(page, shelf_server):
    # Expanding in place keeps every power a top-level tab would lose:
    # same iframe, same window.parent — the seek buttons still drive the
    # player, and the chat tray stays usable above the immersion.
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    item = '.artifact-item[data-name="anchored-listen.html"]'
    page.click(item + " .artifact-expand")
    page.wait_for_selector(item + ".expanded")
    # The tray sits ABOVE the overlay: typing still works while immersed.
    page.fill("#chat-input", "still here")
    assert page.input_value("#chat-input") == "still here"
    # The anchored-listen button inside the EXPANDED frame seeks the talk.
    page.frame_locator(item + " iframe.artifact-frame").locator("#listen").click()
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4.5) < 0.5; }"
    )
    # One immersion at a time: expanding another collapses this one.
    other = '.artifact-item[data-name="guarded-notes.html"]'
    page.evaluate(
        f"document.querySelector('{other} .artifact-expand').click()"
    )
    page.wait_for_selector(other + ".expanded")
    assert page.locator(item + ".expanded").count() == 0


def test_expand_and_collapse_preserve_the_artifact_state(page, shelf_server):
    # The SAME iframe node lifts and settles by class alone — never
    # reparented, so in-tool state survives the round trip; Escape is
    # the way back (after the chat overlay's own rung).
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    item = '.artifact-item[data-name="guarded-notes.html"]'
    frame = page.frame_locator(item + " iframe.artifact-frame")
    from playwright.sync_api import expect

    frame.locator("#count").click()
    expect(frame.locator("#count")).to_have_text("1")
    page.click(item + " .artifact-expand")
    page.wait_for_selector(item + ".expanded")
    frame.locator("#count").click()
    expect(frame.locator("#count")).to_have_text("2")  # state carried up
    # Escape (keys back with the page) folds the artifact into its room.
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Escape")
    page.wait_for_selector(item + ":not(.expanded)")
    expect(frame.locator("#count")).to_have_text("2")  # and back down


def test_mark_as_heard_flips_the_card_in_place(page, shelf_server):
    _wait_for_version_baseline(page, shelf_server.base, "#talk/far-talk")
    page.wait_for_selector("#talk-far-talk.active")
    page.evaluate("window.__e2e_marker = 1")
    # far-talk has no completion on record: the quiet manual door is open.
    page.click("#talk-far-talk .mark-heard")
    # The completed listen lands on the card in place (soft refresh)...
    page.wait_for_selector("#talk-far-talk .listened-line")
    # ...bringing the quieter wrap-up door with it...
    page.wait_for_selector("#talk-far-talk .wrap-up-talk")
    assert page.locator("#talk-far-talk .mark-heard").count() == 0
    # ...without a reload — the page adopted the rebuilt shelf's mtime.
    assert page.evaluate("window.__e2e_marker") == 1
    # And the server wrote it on the SAME path the player's report uses.
    entries = shelf_server.module.load_listening(
        shelf_server.library / ".listening.jsonl"
    )
    assert "far-talk" in {entry["slug"] for entry in entries}


def _wait_for_text_in_file(path, needle, timeout=10.0):
    """Poll a scratch file for a substring (server-side write, no page
    hook to wait on) — tight loop, never a blind long sleep."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and needle in path.read_text():
            return
        time.sleep(0.05)
    raise AssertionError(f"{needle!r} never appeared in {path}")


def test_done_is_server_first_and_reopen_is_its_inverse(page, shelf_server):
    study_path = shelf_server.root / "STUDY.md"
    _open_shelf(page, shelf_server.base, "#talk/demon-story")
    page.wait_for_selector("#talk-demon-story.active")
    page.click("#talk-demon-story .done-for-now")
    # INSTANT recognition, before any reply arrives: the button becomes
    # its own receipt and the sidebar entry flips to ✓ optimistically.
    page.wait_for_selector(
        '#talk-demon-story .done-for-now:has-text("✓ done — finding what\'s next…")'
    )
    # (attached, not visible: the soft refresh may already have tucked
    # the now-studied entry into the collapsed archive — the ✓ is real
    # either way.)
    page.wait_for_selector(
        '#talk-nav a[href="#talk/demon-story"] .nav-state.nav-done',
        state="attached",
    )
    # The mark is REAL with no guide involvement: the SERVER moved the
    # path (the fake brain only ever streams canned text — it could not
    # have written this) and recorded the listen.
    _wait_for_text_in_file(
        study_path, "- **Demon Story** — (done for now — not yet discussed)"
    )
    entries = shelf_server.module.load_listening(
        shelf_server.library / ".listening.jsonl"
    )
    assert "demon-story" in {entry["slug"] for entry in entries}
    # The card flips in place to the done state (soft refresh)...
    page.wait_for_selector('#talk-demon-story .status-done')
    # ...and the follow-up — the guide's only job — went through chat in
    # the user's voice, answered in the same conversation.
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("I\'m done with Demon Story for now — '
        'the shelf has already marked it done on the path.")',
        state="attached",
    )
    page.wait_for_selector(
        '.chat-msg.chat-guide:has-text("One breath, then we begin")',
        state="attached",
    )
    # --- the round trip: reopen is the exact inverse, also server-first.
    page.click("#talk-demon-story .reopen-talk")
    # The optimistic → lands on the (still archived, so hidden) entry at
    # once; the swap soon re-lists it on the living path.
    page.wait_for_selector(
        '#talk-nav a[href="#talk/demon-story"] .nav-state.nav-next',
        state="attached",
    )
    page.wait_for_selector('#talk-nav a[href="#talk/demon-story"]')
    _wait_for_text_in_file(study_path, "- **Demon Story** — (reopened ")
    assert "(done for now — not yet discussed)" not in study_path.read_text().split(
        "## Studied"
    )[1].split("## Queued")[0]
    # Back on the path AND already heard: the card reads "heard — not
    # closed out yet" with the done button re-armed — the honest state.
    page.wait_for_selector("#talk-demon-story .status-heard")
    page.wait_for_selector("#talk-demon-story .done-for-now")
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("I\'ve reopened Demon Story")',
        state="attached",
    )


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


def test_moment_chip_seeks_the_player(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#talk/quiet-mind")
    # The guide's curated moments render as chips in an open details
    # block (no fold to click first) — the moments are the invitation.
    chip = page.wait_for_selector(
        '#talk-quiet-mind .moments[data-slug="quiet-mind"] .moment-chip'
    )
    assert "listen from 0:04" in chip.inner_text()
    assert "how it settles" in chip.inner_text()
    chip.click()
    # Exactly a transcript-line click: seek to the stamp and play.
    page.wait_for_function(
        f"() => {{ const a = {AUDIO_JS};"
        " return a && !a.paused && Math.abs(a.currentTime - 4) < 0.5; }"
    )
    assert page.evaluate("window.saPlayingSlug()") == "quiet-mind"
    # The out-of-range fixture moment (12:00 > 9s transcript) never
    # rendered — grounded chips only.
    assert page.locator('#talk-quiet-mind .moment-chip[data-start="720"]').count() == 0


def test_missing_primer_generator_sends_the_canned_ask(page, shelf_server):
    # far-talk (a reading) has no primer anywhere: the Primer section
    # still renders, holding its ✦ invitation — adapted for a reading.
    _open_shelf(page, shelf_server.base, "#talk/far-talk")
    button = page.wait_for_selector("#talk-far-talk .make-primer")
    assert "how to read this" in button.inner_text()
    button.click()
    # The canned ask lands in the conversation as the user's own message…
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("how to approach the text, what to notice")',
        state="attached",
    )
    page.wait_for_selector(
        ".chat-msg.chat-user:has-text(\"into the notes under '## Primer'\")",
        state="attached",
    )
    # …and the guide answers through the normal pipeline.
    page.wait_for_selector(
        '.chat-msg.chat-guide:has-text("One breath, then we begin")',
        state="attached",
    )
    # bare-yt (a talk) keeps the spoken-primer ask.
    page.evaluate("location.hash = '#talk/bare-yt'")
    talk_button = page.wait_for_selector("#talk-bare-yt .make-primer")
    assert "write & speak a primer" in talk_button.inner_text()


def test_prompt_chips_show_on_focus_send_and_hide_on_typing(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # A focused, empty input grows the quiet suggestion strip — home
    # context offers the path.
    page.focus("#chat-input")
    page.wait_for_selector("#prompt-chips:not([hidden])")
    chips = page.locator("#prompt-chips .prompt-chip").all_inner_texts()
    assert "where are we on the path?" in chips
    # Typing is intent: the strip steps aside on the first keystroke.
    page.keyboard.type("h")
    page.wait_for_selector("#prompt-chips[hidden]", state="attached")
    page.fill("#chat-input", "")
    # In a talk room the suggestions are about the talk.
    page.evaluate("location.hash = '#talk/quiet-mind'")
    page.wait_for_selector("#talk-quiet-mind.active")
    page.focus("#chat-input")
    page.wait_for_selector("#prompt-chips:not([hidden])")
    room_chips = page.locator("#prompt-chips .prompt-chip")
    assert "mark the moments in this talk" in room_chips.all_inner_texts()
    # One tap sends through the queue-aware door and the strip retires.
    room_chips.filter(has_text="what should I listen for?").click()
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("what should I listen for?")',
        state="attached",
    )
    page.wait_for_selector(
        '.chat-msg.chat-guide:has-text("One breath, then we begin")',
        state="attached",
    )


def test_stub_room_opens_and_offers_the_fetch(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    # The queued-but-unfetched entry is a real link now, not a dead end.
    page.click("#talk-nav li.nav-unfetched a")
    page.wait_for_selector("#talk-queued-anger-issues.active")
    room = page.inner_text("#talk-queued-anger-issues")
    assert "Anger Issues" in room
    assert "not fetched yet" in room
    assert "on the path because: A short, direct look" in room
    assert "downloads are explicit — this fetches one talk" in room
    # The one primary action sends the canned ingest ask through the
    # normal (queue-aware) chat pipeline, in the user's own voice.
    page.click("#talk-queued-anger-issues .fetch-stub")
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("Please fetch Anger Issues '
        '(Thanissaro Bhikkhu) — curriculum URL '
        'https://www.dhammatalks.org/audio/morning/2019/190531-anger-issues.html")',
        state="attached",
    )
    page.wait_for_selector(
        '.chat-msg.chat-guide:has-text("One breath, then we begin")',
        state="attached",
    )


def test_stub_room_is_a_decision_point_with_three_doors(page, shelf_server):
    _open_shelf(page, shelf_server.base, "#talk/queued-anger-issues")
    page.wait_for_selector("#talk-queued-anger-issues.active")
    room = page.inner_text("#talk-queued-anger-issues")
    # The copy invites the choice; the three doors stand together.
    assert "build it, set it aside, or talk it through" in room
    assert page.locator("#talk-queued-anger-issues .fetch-stub").count() == 1
    assert page.locator("#talk-queued-anger-issues .skip-stub").count() == 1
    assert page.locator("#talk-queued-anger-issues .ask-stub").count() == 1
    assert "✦ build this room" in room
    assert "skip — not for me right now" in room
    assert "ask the guide about this" in room
    # The reading stub's build door fetches TEXT, and its ask says so.
    page.evaluate(
        "location.hash = '#talk/queued-the-arrow'"
    )
    page.wait_for_selector(
        "#talk-queued-the-arrow.active"
    )
    reading_room = page.inner_text(
        "#talk-queued-the-arrow"
    )
    assert "this is a reading" in reading_room
    page.click("#talk-queued-the-arrow .fetch-stub")
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("Please fetch this reading — '
        'https://www.dhammatalks.org/suttas/SN/SN36_6.html")',
        state="attached",
    )
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("how to read this")',
        state="attached",
    )


def test_skip_sets_aside_instantly_and_the_guide_follows_up(page, shelf_server):
    study_path = shelf_server.root / "STUDY.md"
    _open_shelf(
        page, shelf_server.base, "#talk/queued-the-arrow"
    )
    page.wait_for_selector(
        "#talk-queued-the-arrow.active"
    )
    page.click("#talk-queued-the-arrow .skip-stub")
    # The mark is REAL with no guide involvement: the SERVER moved the
    # entry to Studied with the set-aside note (the fake brain only ever
    # streams canned text — it could not have written this).
    _wait_for_text_in_file(
        study_path,
        "- **The Arrow (Sallatha Sutta, SN 36:6)** — (set aside ",
    )
    studied = study_path.read_text().split("## Studied")[1].split("## Queued")[0]
    assert "didn't call right now" in studied
    # The soft refresh removes the stub room and its sidebar line —
    # skipped means gone from the queue — and the page lands safely home.
    page.wait_for_selector(
        "#talk-queued-the-arrow",
        state="detached",
    )
    page.wait_for_selector("#view-home.active")
    assert (
        page.locator(
            '#talk-nav a[href="#talk/queued-the-arrow"]'
        ).count()
        == 0
    )
    # THEN the follow-up — the guide's only job — in the user's voice,
    # answered in the same conversation.
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("I set aside The Arrow (Sallatha Sutta, '
        'SN 36:6) — it didn\'t call to me right now.")',
        state="attached",
    )
    page.wait_for_selector(
        '.chat-msg.chat-guide:has-text("One breath, then we begin")',
        state="attached",
    )


def test_reading_room_renders_the_text_readably(page, shelf_server):
    # far-talk is a reading (transcript.md only): its room IS the text —
    # open, readable, with no player and no seek anywhere.
    _open_shelf(page, shelf_server.base, "#talk/far-talk")
    page.wait_for_selector("#talk-far-talk.active")
    text_block = page.wait_for_selector("#talk-far-talk .reading-text")
    assert text_block.is_visible()
    assert "Words." in text_block.inner_text()
    assert "The reading" in page.inner_text("#talk-far-talk")
    assert page.locator("#talk-far-talk audio").count() == 0
    assert page.locator("#talk-far-talk .moment-chip").count() == 0
    assert page.locator("#talk-far-talk .seg").count() == 0
    # No spoken version yet: the Spoken ✦ stands (listening-first extends
    # to texts), and its click sends the recording ask through chat.
    recorder = page.wait_for_selector("#talk-far-talk .record-reading")
    assert "record this reading" in recorder.inner_text()
    recorder.click()
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("Please record this reading as audio: '
        'speak the text of Far Talk")',
        state="attached",
    )
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("to far-talk/reading.mp3")',
        state="attached",
    )


def test_spoken_reading_text_click_seeks_the_reading_player(page, shelf_server):
    # spoken-reading carries reading.mp3 + reading.segments.json: its text
    # renders as click-to-seek segments — open on arrival, no sub-expander,
    # still at the reading measure — and a click rides the ONE seek path.
    _open_shelf(page, shelf_server.base, "#talk/spoken-reading")
    page.wait_for_selector("#talk-spoken-reading.active")
    box = page.wait_for_selector(
        '#talk-spoken-reading .seg-transcript.reading-text[data-slug="spoken-reading"]'
    )
    assert box.is_visible()
    seg = page.wait_for_selector('#talk-spoken-reading .seg[data-start="3"]')
    assert seg.is_visible()
    assert "It settles at three." in seg.inner_text()
    # The spoken player carries the room copy that the text now clicks.
    assert "click any line to be there" in page.inner_text("#talk-spoken-reading")
    seg.click()
    audio_js = (
        "document.querySelector("
        "'audio.talk-audio[data-slug=\"spoken-reading\"]')"
    )
    page.wait_for_function(
        f"() => {{ const a = {audio_js};"
        " return a && !a.paused && Math.abs(a.currentTime - 3.0) < 0.5; }"
    )
    assert page.evaluate("window.saIsPlaying()")


# --- busy, visibly: the working line, stop, and the send queue ---------------


def test_stop_button_ends_a_streaming_turn(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    _send_chat(page, "count slowly for me")
    # The persistent working line appears the moment the turn starts...
    page.wait_for_selector("#chat-working:not([hidden])")
    assert "the guide is thinking…" in page.inner_text("#chat-working")
    # ...and the reply is genuinely streaming when we pull the cord.
    page.wait_for_selector('.chat-msg.chat-guide:has-text("count 1")')
    page.click("#chat-stop")
    # The turn ends with the quiet stopped line; the partial reply stays.
    page.wait_for_selector(
        '.chat-msg.chat-system:has-text("— stopped —")', state="attached"
    )
    page.wait_for_selector("#chat-working[hidden]", state="attached")
    bubbles = page.locator(".chat-msg.chat-guide").all_inner_texts()
    assert any("count 1" in text for text in bubbles)
    # Never the full canned count: the stream really was cut short.
    assert not any("count 14" in text for text in bubbles)


def test_send_while_busy_queues_visibly_then_delivers(page, shelf_server):
    _open_shelf(page, shelf_server.base)
    _send_chat(page, "count slowly for me")
    page.wait_for_selector('.chat-msg.chat-guide:has-text("count 1")')
    # A send mid-turn is never dropped: it queues, visibly.
    page.fill("#chat-input", "and here is my follow-up thought")
    page.click("#chat-send")
    page.wait_for_selector("#chat-queued:not([hidden])")
    note = page.inner_text("#chat-queued")
    assert "queued — the guide is finishing something" in note
    assert "and here is my follow-up thought" in note
    assert (
        page.locator('.chat-msg.chat-user:has-text("follow-up thought")').count() == 0
    )
    # The turn ends (stopped here, for speed) — the queue empties at once.
    page.click("#chat-stop")
    page.wait_for_selector(
        '.chat-msg.chat-user:has-text("and here is my follow-up thought")'
    )
    page.wait_for_selector("#chat-queued[hidden]", state="attached")
    # The queued message got its own real turn and reply.
    page.wait_for_function(
        "() => { const gs = document.querySelectorAll('.chat-msg.chat-guide');"
        " return gs.length && gs[gs.length - 1].textContent"
        ".includes('One breath, then we begin'); }"
    )
