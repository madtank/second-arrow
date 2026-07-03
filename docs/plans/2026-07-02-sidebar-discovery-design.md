# Sidebar focus + "something new" discovery — design

Validated with Jacob 2026-07-02.

## Why

Two frustrations, one root:

1. The sidebar lists every talk forever; as the library grows, the
   living path drowns in ✓ done entries.
2. Asking for new material dead-ends: the guide answers from the
   hard-coded curriculum list ("we're out", "here's what we have")
   when the user is actually asking to go FIND something. The
   curriculum was acting as a fence; it should be a seed.

## Rule change (CLAUDE.md)

**Searching and proposing is free; downloading stays explicit and
single-item.** The guide may search the world for candidate talks
(grounded in STUDY.md, notes, history) and present candidates in
conversation. A download still happens only on the user's explicit
pick, one item at a time, with the full fetch ritual (probe,
`--expect-title`, verify, primer, rebuild). "We only have what's on
the list" is no longer a valid answer to "find me something new."

## Sidebar changes (build_shelf.py render; toggle is client-side)

- **Focus list**: the talks list shows only the living path — the
  → current talk (even if also ✓), queued/unheard talks, and
  unfetched stubs. Unheard first ordering stays close to path order;
  we'll vibe the fine ordering later.
- **show more · N**: everything studied tucks behind one muted line
  at the end of the list; click to expand/collapse (client-side,
  persisted in localStorage, default collapsed). If the open room is
  an archived talk, auto-expand and highlight it.
- **Legend replaced**: the "✓ done · → current" line is removed; in
  its place sits **✦ something new** (see below).
- **Footer slimmed**: the "Private — generated from your library.
  Rebuild: …" sentence is removed. The settings link stays.

## ✦ something new (a discovery room, not a button)

Clicking "✦ something new" navigates to a room (same machinery as
stub rooms, view id `discover`). Inside:

- A short static line of where the path stands.
- **Already waiting**: if fetched-but-unheard talks exist, they are
  listed first as links — the room nudges toward them before the
  world.
- **"find me something new"** — button sends a canned ask: search
  based on where we are (STUDY.md, recent notes, what's been
  landing) and bring back 2–3 candidates, each with a one-line why
  and its source URL. Present them in conversation. DO NOT download
  anything yet.
- **"tell me what you're looking for"** — focuses the chat input
  with a hint placeholder; the user steers the search in their own
  words.
- Picking a candidate in conversation IS the explicit single fetch.
  Candidates liked-but-not-taken may be parked under Queued in
  STUDY.md as light entries.

### Guard against pile-up

The canned ask embeds: "If two or more fetched talks are still
unheard, point me to them instead of searching." One fetch per pick,
never a batch — no mechanism exists to queue multiple downloads from
this room.

## New reviewed tool: tools/find_talks.py

`uv run tools/find_talks.py "<query>" [--limit N]` — searches for
candidate talks without downloading: yt-dlp `ytsearchN:` flat
extraction returning title, channel, duration, URL (JSON lines).
No API key. Read-only, network-only, never writes to library/.
Exposed to the Hermes profile through mcp_second_arrow as
`find_talks` so the shelf guide can search too.

## Testing

- Unit: find_talks (mocked yt-dlp), build_shelf render (focus list,
  show-more group, discover room, footer slimming, canned-ask
  wiring) against temp outputs.
- e2e (tools/tests/e2e): sidebar collapse/expand + persistence;
  discover room doors send the canned asks; archived-active talk
  auto-expands. Scratch dirs, ephemeral ports.
- Real shelf.html regenerated exactly once, from committed code, at
  the end.
