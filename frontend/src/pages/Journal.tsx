import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { JournalEntry } from "../types";

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

const FIELDS: { key: keyof JournalEntry; label: string }[] = [
  { key: "first_arrow", label: "First arrow (what happened)" },
  { key: "second_arrow", label: "Second arrow (extra suffering)" },
  { key: "body_sensation", label: "Body sensation" },
  { key: "chosen_response", label: "Chosen response" },
  { key: "reflection", label: "Reflection" },
  { key: "concept_slug", label: "Concept used" },
];

export default function Journal() {
  const { id } = useParams<{ id: string }>();
  return id ? <JournalDetail id={Number(id)} /> : <JournalList />;
}

function JournalList() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getJournal()
      .then(setEntries)
      .catch(() => setError("Could not load journal. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1>Journal</h1>
      <p className="lede">
        A private record of your practice sessions. Notice the patterns; be
        gentle with what you find.
      </p>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="notice">{error}</p>}

      {!loading && !error && entries.length === 0 && (
        <div className="card">
          <p className="muted">No entries yet.</p>
          <Link to="/practice" className="btn btn-warm">
            Start a practice session
          </Link>
        </div>
      )}

      {entries.map((e) => (
        <Link key={e.id} to={`/journal/${e.id}`} className="card card-link">
          <p className="entry-meta">{formatDate(e.created_at)}</p>
          <h3>{e.first_arrow?.trim() || "(no trigger noted)"}</h3>
          {e.chosen_response && (
            <p className="muted">Response: {e.chosen_response}</p>
          )}
        </Link>
      ))}
    </div>
  );
}

function JournalDetail({ id }: { id: number }) {
  const navigate = useNavigate();
  const [entry, setEntry] = useState<JournalEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .getJournalEntry(id)
      .then(setEntry)
      .catch(() => setError("Could not load this entry."))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleDelete() {
    if (!window.confirm("Delete this journal entry?")) return;
    try {
      await api.deleteJournalEntry(id);
      navigate("/journal");
    } catch {
      setError("Could not delete this entry.");
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (error || !entry) return <p className="notice">{error ?? "Not found."}</p>;

  return (
    <article className="entry">
      <p className="muted small">
        <Link to="/journal">← All entries</Link>
      </p>
      <h1>Practice session</h1>
      <p className="entry-meta">{formatDate(entry.created_at)}</p>

      <div className="card">
        <dl>
          {FIELDS.map(({ key, label }) => {
            const value = entry[key];
            if (!value) return null;
            const display =
              key === "concept_slug"
                ? String(value).replace(/-/g, " ")
                : String(value);
            return (
              <div key={key}>
                <dt>{label}</dt>
                <dd>{display}</dd>
              </div>
            );
          })}
        </dl>
      </div>

      <div className="btn-row">
        <Link to="/practice" className="btn btn-secondary">
          New session
        </Link>
        <button className="btn btn-secondary" onClick={handleDelete}>
          Delete
        </button>
      </div>
    </article>
  );
}
