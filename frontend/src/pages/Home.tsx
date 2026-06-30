import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div>
      <section className="hero">
        <h1>Second Arrow</h1>
        <p className="quote">Pain happens. The second arrow is optional.</p>
        <p className="lede">
          A calm place to study a few Buddhist ideas and practice patience when
          anger or reactivity shows up.
        </p>

        <div className="hero-actions">
          <Link to="/learn" className="btn">
            Start learning
          </Link>
          <Link to="/practice" className="btn btn-warm">
            I'm angry now
          </Link>
        </div>
      </section>

      <section>
        <h2>First arrow vs. second arrow</h2>
        <div className="card">
          <p>
            There's an old Buddhist image of two arrows. The{" "}
            <strong>first arrow</strong> is the pain that actually happens — a
            harsh word, a setback, getting cut off in traffic. Often we can't
            avoid it.
          </p>
          <p>
            The <strong>second arrow</strong> is everything we pile on top: the
            anger, the replaying, the resentment, the story that{" "}
            <em>this should not be happening</em>. That one is optional — and
            it's the one we can practice putting down.
          </p>
          <p className="muted">
            Notice the reaction. Choose the response.
          </p>
        </div>
      </section>

      <section>
        <h2>Three small areas</h2>
        <Link to="/learn" className="card card-link">
          <h3>Learn</h3>
          <p className="muted">
            A short, beginner-friendly path through ideas like patience,
            mindfulness, and the second arrow.
          </p>
        </Link>
        <Link to="/practice" className="card card-link">
          <h3>Practice</h3>
          <p className="muted">
            A quick step-by-step flow for moments of anger: pause, name it,
            choose a skillful response.
          </p>
        </Link>
        <Link to="/journal" className="card card-link">
          <h3>Journal</h3>
          <p className="muted">
            A private log of your practice sessions, so you can notice patterns
            over time.
          </p>
        </Link>
      </section>
    </div>
  );
}
