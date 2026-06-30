import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Concept } from "../types";

export default function Learn() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getConcepts()
      .then(setConcepts)
      .catch(() => setError("Could not load concepts. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1>Learning path</h1>
      <p className="lede">
        A short path of beginner-friendly ideas for working with anger and
        building patience. Start at the top.
      </p>
      <p className="muted small">
        Study material for personal practice — not scripture or professional
        advice.
      </p>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="notice">{error}</p>}

      <div style={{ marginTop: "1.25rem" }}>
        {concepts.map((c, i) => (
          <Link key={c.slug} to={`/learn/${c.slug}`} className="card card-link">
            <span className="card-index">{i + 1}</span>
            <h3>{c.title}</h3>
            <p className="muted">{c.summary}</p>
            <div className="tags">
              {c.tags.map((t) => (
                <span key={t} className="tag">
                  {t}
                </span>
              ))}
            </div>
            <span className="btn btn-secondary">Study →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
