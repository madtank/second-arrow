# Sidebar Focus + Something-New Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Focus the sidebar on the living path (studied talks behind "show more"), replace the legend with a "✦ something new" discovery room whose doors search the world for candidates, and add a reviewed `find_talks.py` search tool.

**Architecture:** All UI is rendered by `tools/build_shelf.py` into one static `shelf.html`; interactivity is inline JS using the existing `sendOrQueue(text)` canned-ask pattern (buttons put words in the user's mouth; the guide does the work). New search capability is a standalone PEP-723 script mirrored as an MCP tool in `tools/mcp_second_arrow.py` for the Hermes brain. Design doc: `docs/plans/2026-07-02-sidebar-discovery-design.md`.

**Tech Stack:** Python 3.13, yt-dlp (search only, `extract_flat`), pytest, Playwright e2e (`tools/tests/e2e/`, see its README — scratch dirs, ephemeral ports, never 8765/8642).

**House rules that bind every task:**
- Tests first, always. Unit run: `uv run --with pytest --with fastapi --with mlx-whisper pytest tools/tests/ -q`. E2e run: `uv run --with pytest --with fastapi --with uvicorn --with playwright --with mlx-whisper pytest tools/tests -m e2e -v`.
- NEVER regenerate `library/shelf.html` from uncommitted code. Tests use tmp outputs; regenerate the real shelf exactly once, from committed code, in the final task.
- Match surrounding comment voice (short, why-not-what, room metaphors).

---

### Task 1: `tools/find_talks.py` — search without downloading

**Files:**
- Create: `tools/find_talks.py`
- Test: `tools/tests/test_find_talks.py`

**Step 1: Write the failing tests.** Mirror the mocking style in `tools/tests/test_fetch_talk.py` (import module via `importlib` the way other tool tests do — check its header for the loader helper).

```python
"""find_talks searches; it never downloads, never writes."""
import json

import find_talks  # via the same sys.path/loader convention as test_fetch_talk


class FakeYDL:
    def __init__(self, opts):
        self.opts = opts
        FakeYDL.seen_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, target, download=False):
        FakeYDL.seen_target = target
        assert download is False
        return {
            "entries": [
                {"title": "Unentangled Knowing", "channel": "dhammatalks",
                 "duration": 900.0, "url": "https://youtu.be/abc"},
                None,  # yt-dlp yields None for dead entries — skip, don't crash
                {"title": "No duration", "uploader": "someone", "url": "u2"},
            ]
        }


def test_search_flattens_entries(monkeypatch):
    monkeypatch.setattr(find_talks, "_ydl", lambda: FakeYDL)
    rows = find_talks.search("thanissaro feelings", limit=3)
    assert FakeYDL.seen_target == "ytsearch3:thanissaro feelings"
    assert FakeYDL.seen_opts["extract_flat"] is True
    assert rows[0] == {"title": "Unentangled Knowing", "channel": "dhammatalks",
                       "duration": 900, "url": "https://youtu.be/abc"}
    assert rows[1]["channel"] == "someone" and rows[1]["duration"] is None


def test_main_prints_json_lines(monkeypatch, capsys):
    monkeypatch.setattr(find_talks, "search", lambda q, limit: [{"title": "t", "url": "u"}])
    find_talks.main(["some query", "--limit", "2"])
    line = capsys.readouterr().out.strip()
    assert json.loads(line) == {"title": "t", "url": "u"}
```

**Step 2: Run to verify failure.**
Run: `uv run --with pytest --with fastapi --with mlx-whisper pytest tools/tests/test_find_talks.py -v`
Expected: FAIL — `ModuleNotFoundError: find_talks` (or import error).

**Step 3: Minimal implementation.**

```python
#!/usr/bin/env python3
# /// script
# dependencies = ["yt-dlp"]
# ///
"""Search for candidate talks — read-only discovery, one JSON line each.

The companion to fetch_talk: this one only LOOKS. It searches (yt-dlp
flat extraction, no download, no key) and prints candidates for the
guide to weigh in conversation; a download still happens only through
an explicit fetch_talk the user asked for.

Run with:
    uv run tools/find_talks.py "thanissaro bhikkhu restlessness" --limit 5
"""

import argparse
import json


def _ydl():
    import yt_dlp

    return yt_dlp.YoutubeDL


def search(query: str, limit: int = 5) -> list[dict]:
    """Top candidates for a query: title, channel, duration (s), url."""
    opts = {"quiet": True, "extract_flat": True, "skip_download": True}
    with _ydl()(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    rows = []
    for entry in (info or {}).get("entries") or []:
        if not entry:
            continue
        rows.append({
            "title": entry.get("title") or "",
            "channel": entry.get("channel") or entry.get("uploader") or "",
            "duration": int(entry["duration"]) if entry.get("duration") else None,
            "url": entry.get("url") or entry.get("webpage_url") or "",
        })
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    for row in search(args.query, args.limit):
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

**Step 4: Run tests — PASS. Full unit suite still green.**

**Step 5: Commit.** `git add tools/find_talks.py tools/tests/test_find_talks.py && git commit -m "find_talks: search the world, download nothing"`

---

### Task 2: MCP `find_talks` for the Hermes brain

**Files:**
- Modify: `tools/mcp_second_arrow.py` (add handler near `search_history`, ~line 273; register in `build_server`, ~line 439)
- Test: `tools/tests/test_mcp_second_arrow.py`

**Step 1: Failing test** — copy the existing `search_history` test's shape (it monkeypatches `run_tool`); assert `find_talks("x", limit=3)` builds `["uv", "run", <tools>/find_talks.py", "x", "--limit", "3"]` and returns the tool output, and that a failure comes back as the error string (same contract as siblings).

**Step 2: Verify FAIL.** **Step 3:** implement handler exactly like `search_history` (run_tool + passthrough), register it in `build_server` with a one-line description: "Search for candidate talks (read-only) — present candidates in conversation; downloads stay explicit via fetch_talk." **Step 4:** suite green. **Step 5:** commit `"mcp: find_talks — discovery reaches the gateway brain"`.

---

### Task 3: render_nav — focus list, show-more archive, ✦ something new

**Files:**
- Modify: `tools/build_shelf.py:3551-3588` (`render_nav`), `_NAV_LEGEND` (3548) dies
- Test: `tools/tests/test_build_shelf.py`

**Step 1: Failing tests** (fixtures per `shelf_fixtures.py` conventions):

```python
def test_render_nav_archives_studied_behind_show_more():
    talks = [{"slug": "a", "title": "A"}, {"slug": "b", "title": "B"},
             {"slug": "c", "title": "C"}]
    states = {"a": "studied", "b": "queued"}
    html = build_shelf.render_nav(talks, states)
    # living path first and visible; studied hidden behind the toggle
    assert html.index('#talk/b') < html.index('nav-archive-toggle')
    assert 'show more · 1' in html
    a_item = html[html.index('#talk/a') - 200:html.index('#talk/a')]
    assert 'nav-archived' in a_item
    # legend gone, something-new door present, after the path
    assert '✓ done' not in html
    assert '#talk/something-new' in html and '✦ something new' in html


def test_render_nav_no_archive_when_nothing_studied():
    html = build_shelf.render_nav([{"slug": "b", "title": "B"}], {"b": "queued"})
    assert 'nav-archive-toggle' not in html
    assert '#talk/something-new' in html
```

**Step 2: FAIL.** **Step 3: Implementation** — inside `render_nav`: split `talks` into `living` (state != "studied") and `archived` preserving order; render living items + stubs as today; then `<li class="nav-something-new"><a href="#talk/something-new">✦ <span class="nav-title">something new</span></a></li>`; then, only if `archived`: a toggle `<li class="nav-archive-toggle"><button type="button" id="nav-archive-toggle">show more · N</button></li>` followed by archived items each carrying `class="nav-archived" hidden`. Drop `_NAV_LEGEND` from the return (delete the constant). Update the docstring — the three-marks story now includes "studied rests behind show more; ✦ something new is the door out of the list".

**Step 4: PASS + suite green. Step 5: commit** `"sidebar: the path stays visible; the finished rests behind show more"`.

---

### Task 4: nav JS — toggle, persistence, active-archived auto-expand

**Files:**
- Modify: `tools/build_shelf.py` inline JS: near the nav-swap (`2361`) and hash-routing active-link code (`2309`, `2669-2690`); add a small `applyArchiveState()` helper; CSS for `.nav-archive-toggle`/`.nav-something-new` near `#talk-nav` styles (~598-610)
- Test: `tools/tests/e2e/test_shelf_e2e.py`

**Step 1: Failing e2e tests** (read `tools/tests/e2e/README.md` + copy an existing test's fixture pattern — they build a scratch shelf and drive Playwright):

- `test_archive_show_more_toggles_and_persists`: build shelf with 1 queued + 2 studied → archived links hidden; click "show more · 2" → visible, button reads "show less"; reload page → still expanded (localStorage).
- `test_active_archived_talk_expands_archive`: navigate to `#talk/<studied-slug>` directly → its nav link is visible and `.active`.

**Step 2: FAIL.** **Step 3:** implement:

```javascript
// The archive stays tucked unless the reader asked otherwise — one
// remembered choice, and never hiding the room you are standing in.
function applyArchiveState(expand) {
  var toggle = document.getElementById("nav-archive-toggle");
  if (!toggle) return;
  var open = typeof expand === "boolean" ? expand
    : (function () { try { return localStorage.getItem("nav-archive") === "open"; }
       catch (e) { return false; } })();
  document.querySelectorAll("#talk-nav .nav-archived").forEach(function (li) {
    li.hidden = !open;
  });
  toggle.textContent = open ? "show less" : toggle.getAttribute("data-label");
  try { localStorage.setItem("nav-archive", open ? "open" : "closed"); }
  catch (e) { /* no memory is fine */ }
}
```

Wire: toggle stores its initial "show more · N" in `data-label` (render side); click handler flips (`delegate on #sidebar`, survive nav swaps); call `applyArchiveState()` after initial load AND after the `#talk-nav` swap at ~2361; in the hash router where `.active` is set on nav links, if the active link's `li` has `.nav-archived`, call `applyArchiveState(true)`.

**Step 4: e2e green** (`-m e2e`). **Step 5: commit** `"sidebar: show more remembers, and never hides the open room"`.

---

### Task 5: the something-new room

**Files:**
- Modify: `tools/build_shelf.py` — new `render_discover_card(talks, states, listening)` next to `render_stub_card` (3282); include it in `render_shelf`'s views; canned-ask JS next to the `.fetch-stub` handler (~1479); CSS reuses `.talk-stub` styles
- Test: `tools/tests/test_build_shelf.py` (render), `tools/tests/e2e/test_shelf_e2e.py` (doors)

**Step 1: Failing render tests:**

```python
def test_discover_room_renders_with_doors_and_unheard():
    talks = [{"slug": "a", "title": "A"}, {"slug": "b", "title": "B"}]
    states = {"a": "studied"}          # b is fetched, untouched: unheard
    html = build_shelf.render_discover_card(talks, states, listening={})
    assert 'id="talk-something-new"' in html
    assert 'class="find-new"' in html and 'class="describe-new"' in html
    assert 'already waiting' in html and '#talk/b' in html and '#talk/a' not in html


def test_discover_room_omits_waiting_when_all_heard():
    html = build_shelf.render_discover_card(
        [{"slug": "a", "title": "A"}], {}, listening={"a": {"seconds": 5}})
    assert 'already waiting' not in html
```

**Step 2: FAIL.** **Step 3:** implement `render_discover_card`: a `section.card.view.talk-stub` id `talk-something-new`, title "something new", copy line "the shelf is not the world — from here we go looking."; **already waiting** block (links) for talks with no listening record and state != "studied"; two doors:

- `<button type="button" class="find-new">✦ find me something new</button>`
- `<button type="button" class="describe-new">tell me what you're looking for</button>`

JS, following the `.fetch-stub` comment voice:

```javascript
// The something-new doors: searching is free, downloading stays a
// separate explicit pick — the ask says so out loud.
document.addEventListener("click", function (event) {
  if (event.target.closest(".find-new")) {
    sendOrQueue("Find me something new — search beyond the curriculum, "
      + "grounded in where we are (STUDY.md, recent notes, what's been "
      + "landing). Bring back 2-3 candidate talks, each with a one-line "
      + "why and its source URL, and present them in conversation — do "
      + "NOT download anything yet. If two or more fetched talks are "
      + "still unheard on the shelf, point me to those first instead.");
  }
  var describe = event.target.closest(".describe-new");
  if (describe) {
    var input = document.getElementById("chat-input");
    if (input) {
      input.placeholder = "what are you looking for? your own words…";
      input.focus();
    }
  }
});
```

Register the section in `render_shelf` views alongside stub cards. **Step 4:** render tests pass; add e2e: click `✦ something new` in nav → room visible; click `.find-new` → the chat input/queue carries "Find me something new" (assert like existing canned-ask e2e tests do). **Step 5: commit** `"the something-new room: from here we go looking"`.

---

### Task 6: footer slim

**Files:** Modify `tools/build_shelf.py:4002-4006`; adjust any test asserting the footer text (grep `Private —` in tests).

Test-first: assert `render_shelf` output contains the settings link but NOT "generated from your library". Implementation: footer becomes just the settings link. Commit `"sidebar: the footer says one thing"`.

---

### Task 7: CLAUDE.md — the fence becomes a seed

**Files:** Modify `CLAUDE.md` (no test; prose).

- Reviewed tools list gains: `uv run tools/find_talks.py "<query>"` — search for candidates, read-only; present candidates in conversation; never fetch from a search without the user's explicit pick (single item, full ritual).
- Hard rules: soften "curriculum first" for new material into: *searching and proposing is free; downloading stays explicit and single-item.* When the user asks for something new, "we're out / here's what we have" is not an answer — search, propose 2-3, let them pick.
- Chat-shelf section: recognize the two canned asks — "Find me something new — search beyond the curriculum…" (search → propose, honor the built-in unheard-first guard) and the describe-door conversations that follow. A candidate pick in conversation IS the explicit fetch request.

Commit `"CLAUDE.md: search is free, downloads stay explicit"`.

---

### Task 8: ship

1. Full unit suite green; full e2e suite green (commands at top).
2. `git status` clean; all commits in.
3. Regenerate the real shelf ONCE from committed code: `uv run tools/build_shelf.py`.
4. Restart 8765 per the deploy note if `serve_shelf.py` changed (it should NOT in this plan — nav/room are build_shelf-only; if it didn't change, leave the server alone) and tell Jacob to refresh.
5. `git push`.
