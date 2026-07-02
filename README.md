# Second Arrow

A calm, Buddhist-inspired learning and practice app for working with **anger,
patience, and emotional reactivity**.

The name comes from the Buddhist *second arrow* teaching: pain happens (the
first arrow), but we often add a second arrow on top — anger, rumination,
resentment, reaction. The first arrow we can't always avoid. The second one we
can learn to put down.

> Pain happens. The second arrow is optional.

This is a small personal learning project — a clean local MVP you can run on
your desktop and later host as a responsive web app / PWA.

> **Note:** Second Arrow is beginner-friendly study and practice material. It is
> **not** scripture, therapy, or medical advice.

---

## The study space

These days this repo works primarily as a **personal study space**, driven by
Claude Code sessions. The guide lives in `CLAUDE.md` — open a session and it
picks up where the last one left off.

- **Real talks** are ingested into a private, gitignored `library/` with
  `tools/fetch_talk.py` (YouTube captions when available, local Whisper
  transcription otherwise).
- **Primers and reflections** can be spoken aloud with `tools/speak.py`
  (local Kokoro TTS, with a `say` fallback) — a short spoken introduction
  before listening to a talk, eyes closed.
- **Curated clusters** of talks by theme live in `curriculum/`.
- **A local shelf page** (`tools/build_shelf.py`) renders the library as a
  calm, self-contained `library/shelf.html` — primers, players, and notes,
  clickable from the browser.
- **A served chat shelf** (`tools/serve_shelf.py`) serves the same page at
  `http://localhost:8765` with a guide chat panel — the Hermes harness by
  default whenever its gateway is wired (see below), with the Claude CLI
  and a local Ollama model as explicit fallbacks. A settings room on the
  shelf (`#settings`) holds the model routes, the fallback picks, the
  machinery status, and the nightly-prep controls in one calm place.
- Study memory (`STUDY.md`) and the journal stay private and out of git.

The web app described below still runs fine, but it's a dormant MVP — the
center of gravity has moved to the study sessions.

---

## The guide's harness: Hermes

The chat guide's home is **hermes-agent** (Nous Research) — one harness,
many models. A dedicated Hermes profile named `second-arrow` runs an
OpenAI-compatible gateway on localhost; the shelf treats it as the default
brain whenever the gateway is up and correctly locked down, and says so
honestly when it isn't (falling back to the Claude CLI — visibly, never
silently).

What makes it the home harness:

- **One harness, many models.** Model choice is a *route*, not a code
  change: `deep` targets a hosted frontier model (gpt-5.5), `local` runs
  fully offline through Ollama (gemma4:12b). The shelf's settings room
  picks a route per request; the profile's default model is Hermes
  configuration (`hermes -p second-arrow config set model.default …`,
  then a gateway restart) — the shelf reads that truth and never edits it.
- **A locked-down profile.** The profile's only toolset is this repo's
  own MCP server (`tools/mcp_second_arrow.py` — 14 reviewed tools:
  reading the library, scoped writes to study notes and the path, one
  explicit single-item fetch). The shelf refuses to talk to an
  over-provisioned gateway: if extra toolsets are enabled, it counts as
  not wired.
- **The journal is write-only by design.** There is a tool to append a
  reflection and deliberately no tool to read one back, so journal text
  never rides into a hosted model's context.
- **Nightly prep runs inside the gateway.** A single pinned cron job
  (`nightly-prep`, 03:23) writes primers and notes for queued talks —
  nothing is fetched that isn't already on the path. The shelf shows the
  job and offers run-now / pause / resume through a narrow server-side
  proxy scoped to that one job.

Wiring ritual (each step is user-run, idempotent, and verifiable):

```bash
uv run tools/wire_hermes_profile.py       # restrict toolsets, register the MCP server
hermes -p second-arrow gateway restart    # pick up the profile changes
uv run tools/hermes_probe.py              # verify the gate is really open
uv run tools/hermes_cron_setup.py         # install the nightly-prep job
```

The tools have two test suites — keep both green:

```bash
# unit
uv run --with pytest --with fastapi --with mlx-whisper pytest tools/tests/ -q

# browser e2e (Playwright driving a real served shelf on a scratch library)
uv run --with pytest --with fastapi --with uvicorn --with playwright \
  --with mlx-whisper pytest tools/tests -m e2e -v
```

---

## What's inside

Three main areas:

1. **Learn** — a short, ordered learning path through beginner-friendly Buddhist
   concepts (the second arrow, patience, mindfulness, compassion, equanimity,
   the Four Noble Truths, and more), starting with *The Second Arrow*.
2. **Practice** — a step-by-step "I'm angry now" flow: pause (60s timer), name
   the first arrow, identify the second arrow, do a body check, choose a
   skillful response, reflect, and save.
3. **Journal** — a private log of practice sessions so you can notice patterns
   over time.

Plus a **Resources** page (curated, growing — no invented links).

---

## Tech stack

- **Frontend:** React + TypeScript + Vite, plain calm CSS (no heavy UI
  framework), React Router.
- **Backend:** Python + FastAPI.
- **Database:** SQLite (auto-created and seeded on first run).

---

## Project structure

```
second-arrow/
├── Makefile                # convenience commands (install / dev / test)
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py         # FastAPI app + routes
│   │   ├── database.py     # SQLite/SQLAlchemy setup
│   │   ├── models.py       # ORM models (concepts, resources, journal_entries)
│   │   ├── schemas.py      # Pydantic request/response schemas
│   │   ├── seed.py         # seeds the DB on first run (idempotent)
│   │   └── seed_data.py    # the actual concept + resource content
│   └── tests/test_api.py   # API smoke tests
└── frontend/
    ├── package.json
    ├── vite.config.ts      # dev server proxies /api -> backend
    ├── index.html          # manifest + theme color (PWA prep)
    ├── public/
    │   ├── manifest.webmanifest
    │   └── icon.svg
    └── src/
        ├── App.tsx         # nav + routes
        ├── api.ts          # typed API client
        ├── types.ts
        ├── styles.css      # the calm design
        └── pages/          # Home, Learn, ConceptDetail, Practice, Journal, Resources
```

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and npm

---

## Setup

Clone the repo, then install both halves:

```bash
make install
```

Or manually:

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

---

## Running locally

You need the backend and frontend running at the same time (two terminals), or
use the combined command.

### Option A — one command

```bash
make dev
```

This starts the backend on **http://localhost:8000** and the frontend on
**http://localhost:5173**. Open the frontend URL in your browser.

### Option B — two terminals

**Terminal 1 (backend):**

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

**Terminal 2 (frontend):**

```bash
cd frontend
npm run dev
```

Then visit **http://localhost:5173**.

> The Vite dev server proxies `/api` requests to the backend, so no extra
> configuration is needed for local development.

The SQLite database (`backend/second_arrow.db`) is created and seeded with the
beginner concepts automatically the first time the backend starts.

---

## API endpoints

| Method | Path                     | Description                         |
| ------ | ------------------------ | ----------------------------------- |
| GET    | `/api/health`            | Health check                        |
| GET    | `/api/concepts`          | List concepts (learning path)       |
| GET    | `/api/concepts/{slug}`   | Single concept detail               |
| GET    | `/api/resources`         | List resources                      |
| GET    | `/api/journal`           | List journal entries (newest first) |
| POST   | `/api/journal`           | Create a journal entry              |
| GET    | `/api/journal/{id}`      | Single journal entry                |
| DELETE | `/api/journal/{id}`      | Delete a journal entry              |

Interactive API docs are available at **http://localhost:8000/docs** when the
backend is running.

---

## Tests

```bash
make test
# or
cd backend && source .venv/bin/activate && pytest
```

The tests use a throwaway SQLite database, so your real journal is never
touched.

---

## PWA / mobile

The layout is responsive and works on phone-sized screens. Basic PWA prep is in
place (app name, theme color, web manifest, installable metadata). Full offline
support is intentionally not implemented yet.

---

## Adding content

- **Concepts and resources** live in `backend/app/seed_data.py`. Edit that file,
  delete `backend/second_arrow.db` (or run `make clean`), and restart the
  backend to reseed.
- The seeder is idempotent, so adding *new* concepts/resources and restarting
  also works without wiping existing data.
- **Resources:** add only real, verified links. Several entries are placeholders
  with `TODO` notes for future curation — no fake URLs.

---

## What still needs work / next ideas

- Editing journal entries (currently create / view / delete only).
- Real curated resources with verified links.
- Concept "related concepts" linking and search/filter by tag.
- Offline support / full installable PWA with service worker.
- Optional gentle reminders or a streak of practice sessions.
- Light auth if you ever host it for more than just yourself.
