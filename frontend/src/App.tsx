import { NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Learn from "./pages/Learn";
import ConceptDetail from "./pages/ConceptDetail";
import Practice from "./pages/Practice";
import Journal from "./pages/Journal";
import Resources from "./pages/Resources";

function Nav() {
  const link = (to: string, label: string, end = false) => (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
    >
      {label}
    </NavLink>
  );
  return (
    <header className="site-header">
      <NavLink to="/" className="brand" end>
        Second Arrow
      </NavLink>
      <nav className="nav">
        {link("/", "Home", true)}
        {link("/learn", "Learn")}
        {link("/practice", "Practice")}
        {link("/journal", "Journal")}
        {link("/resources", "Resources")}
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <div className="app">
      <Nav />
      <main className="content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/learn" element={<Learn />} />
          <Route path="/learn/:slug" element={<ConceptDetail />} />
          <Route path="/practice" element={<Practice />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/journal/:id" element={<Journal />} />
          <Route path="/resources" element={<Resources />} />
          <Route
            path="*"
            element={<p className="muted">Page not found.</p>}
          />
        </Routes>
      </main>
      <footer className="site-footer">
        <p className="muted small">
          Second Arrow is beginner-friendly study and practice material — not
          scripture, therapy, or medical advice.
        </p>
      </footer>
    </div>
  );
}
