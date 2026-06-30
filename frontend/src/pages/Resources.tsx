import { useEffect, useState } from "react";
import { api } from "../api";
import type { Resource } from "../types";

const TYPE_LABELS: Record<string, string> = {
  book: "Book",
  website: "Website",
  youtube: "YouTube",
  podcast: "Podcast",
  talk: "Talk",
  article: "Article",
  practice: "Practice",
};

export default function Resources() {
  const [resources, setResources] = useState<Resource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getResources()
      .then(setResources)
      .catch(() => setError("Could not load resources. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1>Resources</h1>
      <p className="lede">
        A small, growing collection of things worth exploring. This page is a
        starting point — more curated resources to come.
      </p>
      <p className="muted small">
        Only verified, appropriate resources are added here. No invented links.
      </p>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="notice">{error}</p>}

      {resources.map((r) => (
        <div key={r.id} className="card">
          <div className="tags">
            <span className="tag">{TYPE_LABELS[r.type] ?? r.type}</span>
            {r.beginner_level && <span className="tag">beginner</span>}
          </div>
          <h3>{r.title}</h3>
          {r.creator && <p className="muted small">by {r.creator}</p>}
          {r.description && <p>{r.description}</p>}
          {r.url ? (
            <a href={r.url} target="_blank" rel="noreferrer" className="btn btn-secondary">
              Open →
            </a>
          ) : (
            <p className="muted small">
              <em>Link to be added during curation.</em>
            </p>
          )}
        </div>
      ))}

      {!loading && resources.length === 0 && !error && (
        <p className="muted">No resources yet — check back soon.</p>
      )}
    </div>
  );
}
