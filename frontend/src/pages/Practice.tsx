import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

const SECOND_ARROW_OPTIONS = [
  "They always do this",
  "I'm being disrespected",
  "This should not be happening",
  "I need to win this",
  "I'm replaying it over and over",
];

const BODY_OPTIONS = ["chest", "jaw", "stomach", "shoulders", "head", "hands"];

const RESPONSE_OPTIONS = [
  "say nothing yet",
  "take a walk",
  "write but do not send",
  "ask a calm question",
  "set a boundary",
  "apologize",
  "return to the breath",
  "choose compassion",
];

const PAUSE_SECONDS = 60;

type Step =
  | "pause"
  | "first"
  | "second"
  | "body"
  | "response"
  | "reflection"
  | "done";

const STEP_ORDER: Step[] = [
  "pause",
  "first",
  "second",
  "body",
  "response",
  "reflection",
];

export default function Practice() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const conceptSlug = params.get("concept");

  const [step, setStep] = useState<Step>("pause");

  // Form state
  const [firstArrow, setFirstArrow] = useState("");
  const [secondArrow, setSecondArrow] = useState("");
  const [secondArrowOther, setSecondArrowOther] = useState("");
  const [body, setBody] = useState("");
  const [bodyOther, setBodyOther] = useState("");
  const [response, setResponse] = useState("");
  const [responseOther, setResponseOther] = useState("");
  const [reflection, setReflection] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Timer
  const [secondsLeft, setSecondsLeft] = useState(PAUSE_SECONDS);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (step !== "pause") return;
    timerRef.current = window.setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          if (timerRef.current) window.clearInterval(timerRef.current);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [step]);

  const stepIndex = STEP_ORDER.indexOf(step);
  const progress =
    step === "done" ? "" : `Step ${stepIndex + 1} of ${STEP_ORDER.length}`;

  const resolved = (choice: string, other: string) =>
    choice === "Other" ? other.trim() : choice;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const saved = await api.createJournalEntry({
        first_arrow: firstArrow.trim() || null,
        second_arrow: resolved(secondArrow, secondArrowOther) || null,
        body_sensation: resolved(body, bodyOther) || null,
        chosen_response: resolved(response, responseOther) || null,
        reflection: reflection.trim() || null,
        concept_slug: conceptSlug || null,
      });
      navigate(`/journal/${saved.id}`);
    } catch {
      setError("Could not save. Is the backend running?");
      setSaving(false);
    }
  }

  return (
    <div>
      <h1>Practice</h1>
      {conceptSlug && (
        <p className="notice">
          Practicing with: <strong>{conceptSlug.replace(/-/g, " ")}</strong>
        </p>
      )}
      {progress && <p className="step-progress">{progress}</p>}

      {step === "pause" && (
        <div className="card center">
          <h2 style={{ marginTop: 0 }}>Pause</h2>
          <p className="lede">Anger is here. You do not have to become it.</p>
          <div className="breathe" aria-hidden="true" />
          <p className="muted">Take about a minute. Just breathe.</p>
          <div className="timer">
            {Math.floor(secondsLeft / 60)}:
            {String(secondsLeft % 60).padStart(2, "0")}
          </div>
          <div className="btn-row" style={{ justifyContent: "center" }}>
            <button className="btn" onClick={() => setStep("first")}>
              {secondsLeft === 0 ? "Continue" : "Skip timer"}
            </button>
          </div>
        </div>
      )}

      {step === "first" && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>The first arrow</h2>
          <label htmlFor="first">What happened?</label>
          <textarea
            id="first"
            rows={3}
            value={firstArrow}
            placeholder="Someone interrupted me / I felt dismissed / I got stuck in traffic"
            onChange={(e) => setFirstArrow(e.target.value)}
          />
          <StepNav onBack={() => setStep("pause")} onNext={() => setStep("second")} />
        </div>
      )}

      {step === "second" && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>The second arrow</h2>
          <p className="muted">What extra suffering am I adding?</p>
          <Choices
            options={SECOND_ARROW_OPTIONS}
            selected={secondArrow}
            onSelect={setSecondArrow}
            otherValue={secondArrowOther}
            onOtherChange={setSecondArrowOther}
          />
          <StepNav onBack={() => setStep("first")} onNext={() => setStep("body")} />
        </div>
      )}

      {step === "body" && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Body check</h2>
          <p className="muted">Where do I feel it?</p>
          <Choices
            options={BODY_OPTIONS}
            selected={body}
            onSelect={setBody}
            otherValue={bodyOther}
            onOtherChange={setBodyOther}
          />
          <StepNav onBack={() => setStep("second")} onNext={() => setStep("response")} />
        </div>
      )}

      {step === "response" && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>A skillful response</h2>
          <p className="muted">What could I choose right now?</p>
          <Choices
            options={RESPONSE_OPTIONS}
            selected={response}
            onSelect={setResponse}
            otherValue={responseOther}
            onOtherChange={setResponseOther}
          />
          <StepNav onBack={() => setStep("body")} onNext={() => setStep("reflection")} />
        </div>
      )}

      {step === "reflection" && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Reflection</h2>
          <label htmlFor="reflection">
            What would patience look like here? What response would I respect
            tomorrow?
          </label>
          <textarea
            id="reflection"
            rows={4}
            value={reflection}
            placeholder="A few words for your future self…"
            onChange={(e) => setReflection(e.target.value)}
          />
          {error && <p className="notice">{error}</p>}
          <div className="btn-row">
            <button
              className="btn btn-secondary"
              onClick={() => setStep("response")}
            >
              ← Back
            </button>
            <button className="btn" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save to journal"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StepNav({
  onBack,
  onNext,
}: {
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <div className="btn-row">
      <button className="btn btn-secondary" onClick={onBack}>
        ← Back
      </button>
      <button className="btn" onClick={onNext}>
        Next →
      </button>
    </div>
  );
}

function Choices({
  options,
  selected,
  onSelect,
  otherValue,
  onOtherChange,
}: {
  options: string[];
  selected: string;
  onSelect: (v: string) => void;
  otherValue: string;
  onOtherChange: (v: string) => void;
}) {
  return (
    <div className="options">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          className={"option" + (selected === opt ? " selected" : "")}
          onClick={() => onSelect(opt)}
        >
          {opt}
        </button>
      ))}
      <button
        type="button"
        className={"option" + (selected === "Other" ? " selected" : "")}
        onClick={() => onSelect("Other")}
      >
        Other
      </button>
      {selected === "Other" && (
        <input
          type="text"
          value={otherValue}
          placeholder="Describe in your own words…"
          onChange={(e) => onOtherChange(e.target.value)}
        />
      )}
    </div>
  );
}
