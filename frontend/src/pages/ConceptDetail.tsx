import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Concept } from "../types";

export default function ConceptDetail() {
  const { slug } = useParams<{ slug: string }>();
  const [concept, setConcept] = useState<Concept | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    api
      .getConcept(slug)
      .then(setConcept)
      .catch(() => setError("Could not load this concept."))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <p className="muted">Loading…</p>;
  if (error || !concept) return <p className="notice">{error ?? "Not found."}</p>;

  return (
    <article>
      <p className="muted small">
        <Link to="/learn">← Learning path</Link>
      </p>
      <h1>{concept.title}</h1>
      <p className="lede">{concept.summary}</p>

      <div className="tags">
        {concept.tags.map((t) => (
          <span key={t} className="tag">
            {t}
          </span>
        ))}
      </div>

      <h2>What it means</h2>
      <p>{concept.definition}</p>

      <h2>Why it matters for anger</h2>
      <p>{concept.why_anger}</p>

      <h2>A simple practice</h2>
      <p>{concept.practice}</p>

      <h2>Reflection</h2>
      <p>{concept.reflection}</p>

      {concept.source_notes && (
        <p className="muted small" style={{ marginTop: "1.5rem" }}>
          <em>Notes:</em> {concept.source_notes}
        </p>
      )}

      <div className="btn-row">
        <Link
          to={`/practice?concept=${concept.slug}`}
          className="btn btn-warm"
        >
          Use this in a practice session
        </Link>
      </div>
    </article>
  );
}
