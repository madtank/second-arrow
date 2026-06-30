# Second Arrow — convenience commands.
# Most targets assume Python 3 and Node.js are installed.

.PHONY: help install backend frontend dev test seed clean

help:
	@echo "Second Arrow — available commands:"
	@echo "  make install   Install backend (venv) and frontend dependencies"
	@echo "  make backend   Run the FastAPI backend (http://localhost:8000)"
	@echo "  make frontend  Run the Vite dev server (http://localhost:5173)"
	@echo "  make dev       Run backend + frontend together"
	@echo "  make test      Run backend tests"
	@echo "  make clean     Remove the local SQLite database"

install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev

# Run both at once. Backend runs in the background; Ctrl-C stops the frontend,
# then the trap cleans up the backend.
dev:
	@echo "Starting backend + frontend. Press Ctrl-C to stop."
	@cd backend && . .venv/bin/activate && uvicorn app.main:app --reload & \
	BACK_PID=$$!; \
	trap "kill $$BACK_PID 2>/dev/null" EXIT; \
	cd frontend && npm run dev

test:
	cd backend && . .venv/bin/activate && pytest

clean:
	rm -f backend/second_arrow.db
	@echo "Removed local database. It will be recreated and reseeded on next run."
