# Second Arrow — Personal Study Space Design

**Date:** 2026-07-01
**Status:** Approved direction from brainstorming session

## What this is

Second Arrow becomes a personal study space for learning Buddhism and working
with anger, driven by curated real teachings (audio talks and videos) rather
than training-data paraphrase. The "app" is a Claude Code session opened in
this repo; the repo holds the guide's instructions, the ingest tools, the
curated curriculum, and (privately) the library, journal, and study memory.

The previous direction — building out the web app — produced code instead of a
learning experience. This design inverts that: the practice comes first, and
tooling exists only to serve the loop of *pick a talk → ingest it → listen →
discuss together → reflect → remember*.

## Principles

- **Talk-first, story-first.** Audio teachings and stories over textbook
  explanations. The user learns by listening, eyes closed, then discussing.
- **Source-grounded.** The guide teaches from transcripts in `library/`. When
  it lacks the source, it says so and offers to fetch it. No confident
  paraphrasing from memory. Transcripts are working aids; the original audio
  is the authority.
- **Meet the user where they are.** Sessions open with "Where are you right
  now?" — angry, curious, wanting a story, back from a talk — and route
  accordingly. Never a rigid syllabus.
- **Anger is the root cluster.** Anger, aversion, patience, the two arrows.
  Everything else radiates out from there.
- **Resonance, not doctrine.** AA, NDEs, psychology, mind/brain, and
  AI/spirituality parallels are welcome as resonance, never as proof.
- **Public method, private practice.** Tools, guide persona, and curriculum
  are committed and shareable. Transcripts, journal entries, and study memory
  are gitignored and never leave the machine.
- **Explicit downloads only.** One URL at a time, user-initiated. No bulk
  scraping of teaching archives.
- **AI offloads recall, not understanding.** (The Karpathy constraint.) The
  guide remembers, organizes, tags, and connects; understanding is built by
  revisiting ideas through stories, talks, and reflection.

## Layout

```
second-arrow/
├── CLAUDE.md            # guide persona + session rituals        (committed)
├── curriculum/          # curated talks/videos by theme          (committed)
│   └── 01-anger-and-the-second-arrow.md
├── tools/
│   ├── fetch_talk.py    # URL → audio + transcript into library/ (committed)
│   ├── transcribe_talk.py  # existing MLX Whisper tool           (committed)
│   ├── speak.py         # text → audio, local TTS                (committed)
│   └── tests/
├── library/             # one folder per ingested talk           (gitignored)
│   ├── INDEX.md         # catalog: title, teacher, source, themes
│   └── <talk-slug>/
│       ├── audio.mp3
│       ├── transcript.md    (+ transcript.json)
│       ├── notes.md         # themes, stories, quotes, takeaways
│       └── primer.mp3       # optional spoken primer
├── journal/             # daily reflections                      (gitignored)
│   └── YYYY-MM-DD.md
├── STUDY.md             # guide's cross-session memory           (gitignored)
└── backend/ frontend/   # existing web app — dormant, untouched
```

## Components

### 1. The guide (CLAUDE.md)

Sessions in this repo open as the guide, not a coding assistant. On open it
reads `STUDY.md` and `library/INDEX.md`, then asks where the user is. Routes:

- **"I'm angry"** → short grounding practice, then one teaching drawn from an
  already-ingested transcript. Small, warm, no lecture.
- **"I'm curious about X" / "I want a story"** → a small tray: one talk or
  story, one plain-language concept, one practical reflection, one possible
  next resource.
- **"I listened to that talk"** → discussion mode over the transcript,
  section by section — what landed, what confused, what met resistance.
- **"Play me something short"** → the guide composes a 1–2 minute reflection
  grounded in studied transcripts and renders it with `speak.py`.

At session end the guide saves a journal entry (if there was reflection),
updates the talk's `notes.md`, and updates `STUDY.md`.

### 2. Ingest pipeline (fetch_talk.py)

`uv run tools/fetch_talk.py <url> [--title ...]`

- **YouTube:** `yt-dlp` fetches captions/subtitles first (free transcript);
  falls back to downloading the audio track for local transcription.
- **dhammatalks.org:** downloads the mp3 from the talk page.
- **Direct audio URLs:** downloads directly.

Audio without a transcript flows into `transcribe_talk.py` (MLX Whisper,
fully local). Output lands in `library/<slug>/` and the talk is registered in
`library/INDEX.md` with title, teacher, source URL, date, and themes.

### 3. Voice (speak.py)

`uv run tools/speak.py --text "..." -o out.mp3` (or `--file primer.md`)

Local TTS via Kokoro on `mlx-audio` (Apple Silicon), with macOS `say` as a
fallback. Uses:

- **Primers:** 60–90 seconds of "who this teacher is, what to listen for"
  rendered to audio before the user plays the real talk.
- **After-summaries:** short spoken recap, replayable later.
- **Custom talks:** short reflections composed for the user's current state,
  quoting studied transcripts.

### 4. Curriculum

Markdown clusters of real, verified links with one sentence each on why this
talk and when to reach for it. Cluster 1: **Anger & the Second Arrow**
(two arrows, aversion, patience — includes the already-transcribed Patience
talk from dhammatalks.org, 2026-06-12). Later clusters: Patience & Endurance;
Foundations (Four Noble Truths, Eightfold Path — held lightly). Sources lean
on Ajahn Brahm / BSWA (warm, story-rich) and dhammatalks.org (structured).
Links are verified to resolve before being added. The curriculum grows out of
what is actually studied.

### 5. Memory

- `STUDY.md`: what has been studied, what landed, open questions, candidate
  next steps. Read at session start, updated at session end.
- `journal/YYYY-MM-DD.md`: the user's reflections, private.
- `library/<slug>/notes.md`: per-talk understanding that accretes over
  repeat visits.

## The web app

Left untouched and runnable; no further investment. If the study practice
later wants an interface (e.g., the "I'm angry now" Practice flow on a
phone), revisit with real usage behind the decision.

## Build order

1. Restructure: create `library/`, `journal/`, `STUDY.md`; update
   `.gitignore`; move existing Patience outputs into `library/patience/`.
2. Write the guide `CLAUDE.md`.
3. `fetch_talk.py` with tests (captions-first, audio fallback).
4. `speak.py` with tests (Kokoro via mlx-audio, `say` fallback).
5. Curriculum Cluster 1 with verified links.
6. End-to-end proof: ingest one Ajahn Brahm anger talk from YouTube,
   generate a spoken primer, run a full study session, write the first real
   journal entry.

## Roadmap (iterating)

- **Iter 1 — DONE: chat agency, persistence, rich bubbles.** The chat
  guide streams replies, remembers (scoped writes to `STUDY.md`,
  `journal/`, notes, the index; history and session survive restarts
  under `library/.chat/`), and acts through the reviewed tools only
  (fetch_talk, speak, build_shelf — no general Bash). Brain toggle in
  the panel; bubbles render safe mini-markdown.
- **Iter 2 — DONE: path-flow.** `STUDY.md` normalized to Where we are /
  Studied / Queued / Open questions; the guide advances the path when a
  discussion wraps (distill → move to Studied → queue the next best-fit
  talk, offering — never auto-running — the fetch), and the shelf shows
  a small "The path" strip (✓ studied, → queued) parsed from `STUDY.md`.
  A nightly prep cron stays optional, unscheduled.
- **Iter 3 — DONE: Ollama tool loop.** The local brain gets the same
  three reviewed tools as the claude brain (fetch_talk, rebuild_shelf,
  speak) through a bounded loop (max 4 rounds): every call is validated
  into an argv list (no shell, http(s)-only URLs, no flag smuggling,
  outputs pinned under library/), progress lines keep the panel alive
  during long fetches, and models without tool support (per /api/show
  capabilities) degrade gracefully — they're told they have no hands.
  Honest constraint to design around: the offline brain now has tools
  but remains the weaker discussion partner, so it should still lean on
  retrieval (quote the transcript, surface notes) more than free-form
  teaching. Everything else is already local: Whisper transcription,
  Kokoro TTS, the library and journal on disk.
- **Iter 4 — DONE: two-pane shelf, embedded player.** The shelf grew a
  sidebar (title, the path, one nav entry per talk, a Sessions
  placeholder) and a main pane showing one view at a time via
  `location.hash` routing (`#talk/<slug>`, default `#home`) — built to
  survive 50 talks, degrading to a stacked page with JS off. YouTube
  talks get a click-to-load embedded player (youtube-nocookie iframe,
  created only on "Play here" — no third-party request until asked) plus
  a new-tab escape hatch; non-YouTube source links open in a new tab,
  nothing navigates the page away. Chat stays the constant companion
  below the active view.
- **Iter 5 — DONE: sessions with recall; ambient talk context; web
  search.** Chat memory became sessions
  (`library/.chat/sessions/<id>.jsonl` plus a meta sidecar with
  title/summary/talks/claude thread; the old history.jsonl folds into an
  "Earlier conversation" session on startup). The sidebar's Sessions
  list is live: click to reopen and continue, "new conversation" to
  start fresh; when a session is left, one cheap non-streamed call
  (ollama preferred, claude fallback) writes its title + two-line
  summary, degrading to the first user line. Every POST carries the
  open talk's slug as ambient context — the claude prompt gets a
  one-line "[the user has X open]" prefix, ollama retrieval leads with
  that talk's chunks — so "this talk" means the thing on screen. Past
  tense goes through search_sessions (keyword scoring over turns and
  summaries), exposed as `tools/search_history.py` (allowlisted) and as
  the ollama search_history tool; the claude brain also gained
  read-only WebSearch/WebFetch for current-world questions. CLAUDE.md
  carries the tense-routing contract: ambient → the open transcript,
  past → search_history, new material → curriculum/fetch.

## Boundaries

- Private data (`library/`, `journal/`, `STUDY.md`, `output/`) stays
  gitignored.
- Downloads are explicit and single-item; no bulk scraping.
- The guide may adapt content freely but does not silently rewrite or
  execute app code; code changes are reviewed and tested intentionally.
- Not scripture, therapy, or medical advice.
