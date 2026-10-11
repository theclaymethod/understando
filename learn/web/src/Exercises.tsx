import { useEffect, useMemo, useState } from "react";
import { getJson, postJson, type Json } from "./api";
import { RunLog, useGradedRun } from "./GradedRun";
import { useProvider } from "./provider";
import { askTutor } from "./tutor-bus";

type Exercise = Json & { id: string; kind: string; title: string };

const KIND_LABEL: Record<string, string> = {
  predict: "Predict, then run",
  trace: "Trace it",
  "find-line": "Find the line",
  "close-gap": "Close a gap",
  "explain-back": "Explain it back",
};
const KIND_INTRO: Record<string, string> = {
  predict: "Read the planted bug. Predict if the check goes red. Then the server runs the control, and the real result decides.",
  trace: "Step a scenario through the code. Code checks each answer against the answer key.",
  "find-line": "Point at the line that does what the claim says. Code checks it against the code that the claim names.",
  "close-gap": "Write the missing test. The server runs it at the PR head, where it must pass. Then it plants the bug, and the test must fail.",
  "explain-back": "Explain the claim in your own words. A model grades it against the answer key. The grade is a guess, not a fact.",
};

function Predict({ x }: { x: Exercise }) {
  const [prediction, setPrediction] = useState<"" | "red" | "green">("");
  const { state, start, stop } = useGradedRun();
  const g = state.grade;
  return (
    <div className="learn-card" data-testid={`exercise-${x.id}`}>
      <h3>{x.title}</h3>
      <p><strong>Planted bug ({String(x.recipe)}):</strong> {String(x.description)}</p>
      <p><strong>Check {String(x.verifier)}:</strong> {String(x.verifierDescription)}</p>
      <fieldset className="learn-choices" disabled={state.running}>
        <legend>Your prediction</legend>
        <label><input type="radio" name={`p-${x.id}`} value="red" checked={prediction === "red"} onChange={() => setPrediction("red")} /> The check goes red (it finds the bug)</label>
        <label><input type="radio" name={`p-${x.id}`} value="green" checked={prediction === "green"} onChange={() => setPrediction("green")} /> The check stays green (it misses the bug)</label>
      </fieldset>
      <div className="learn-row">
        <button type="button" disabled={!prediction || state.running} onClick={() => void start("/api/exercises/predict", { control: x.control, prediction })}>
          Run control {String(x.control)}
        </button>
        <button type="button" className="learn-link" onClick={() => askTutor({ message: `Give me a hint for control ${String(x.control)}. Do not tell me the result.`, context: { control: String(x.control), exercise: x.id } })}>Ask the tutor for a hint</button>
      </div>
      <RunLog state={state} onStop={stop} />
      {g && <p className={`learn-grade ${g.correct ? "ok" : "no"}`} data-testid="grade">{String(g.message)}</p>}
    </div>
  );
}

function FindLine({ x }: { x: Exercise }) {
  const [path, setPath] = useState(String(x.hintPath));
  const [text, setText] = useState("");
  const [line, setLine] = useState<number | null>(null);
  const [answer, setAnswer] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const paths = (x.paths as string[]) ?? [];
  useEffect(() => {
    setText("");
    getJson<{ text: string }>(`/api/file?path=${encodeURIComponent(path)}`).then((f) => setText(f.text)).catch((e: Error) => setError(e.message));
  }, [path]);
  async function submit(n: number) {
    setLine(n);
    try { setAnswer(await postJson("/api/exercises/find-line", { claim: x.claim, path, line: n })); } catch (e) { setError((e as Error).message); }
  }
  return (
    <div className="learn-card" data-testid={`exercise-${x.id}`}>
      <h3>{x.title}</h3>
      <p>{String(x.prompt)}</p>
      <label>File at the PR head{" "}
        <select value={path} onChange={(e) => setPath(e.target.value)}>{[...new Set(paths)].map((p) => <option key={p}>{p}</option>)}</select>
      </label>
      <p className="learn-muted">Click the line that does it.</p>
      <ol className="learn-file" aria-label={`Lines of ${path}`}>
        {text.split("\n").map((l, i) => (
          <li key={i} className={line === i + 1 ? "picked" : ""}>
            <button type="button" onClick={() => void submit(i + 1)} aria-label={`Line ${i + 1}`}><span className="n">{i + 1}</span><code>{l || " "}</code></button>
          </li>
        ))}
      </ol>
      {answer && <p className={`learn-grade ${answer.correct ? "ok" : "no"}`} data-testid="grade">Line {line}: {String(answer.message)}</p>}
      {error && <p role="alert" className="learn-error">{error}</p>}
    </div>
  );
}

function Trace({ x }: { x: Exercise }) {
  const steps = (x.steps as { prompt: string; choices: string[] }[]) ?? [];
  const [step, setStep] = useState(0);
  const [feedback, setFeedback] = useState<Json | null>(null);
  const done = step >= steps.length;
  async function choose(i: number) {
    const r = await postJson<Json>("/api/exercises/trace", { exercise: x.id, step, choice: i });
    setFeedback(r);
  }
  return (
    <div className="learn-card" data-testid={`exercise-${x.id}`}>
      <h3>{x.title}</h3>
      <p>{String(x.scenario)}</p>
      {done ? <p className="learn-grade ok" data-testid="grade">You traced every step of the scenario.</p> : (
        <>
          <p><strong>Step {step + 1} of {steps.length}:</strong> {steps[step].prompt}</p>
          <div className="learn-col">{steps[step].choices.map((c, i) => <button key={i} type="button" className="learn-option" onClick={() => void choose(i)}>{c}</button>)}</div>
          {feedback && (
            <div className={`learn-grade ${feedback.correct ? "ok" : "no"}`} data-testid="grade">
              {feedback.correct ? <>Correct: {String(feedback.why ?? "")} <button type="button" onClick={() => { setStep(step + 1); setFeedback(null); }}>Next step</button></> : "That choice is not the next step, so try another one."}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CloseGap({ x, saved }: { x: Exercise; saved?: string }) {
  const [content, setContent] = useState(saved ?? String(x.starter ?? ""));
  const [message, setMessage] = useState("");
  const { state, start, stop } = useGradedRun();
  async function save() {
    try { await postJson("/api/exercises/close-gap/test", { exercise: x.id, content }); setMessage(`Saved to ${String(x.testPath)} in the scratch worktree.`); }
    catch (e) { setMessage((e as Error).message); }
  }
  const g = state.grade;
  return (
    <div className="learn-card" data-testid={`exercise-${x.id}`}>
      <h3>{x.title}</h3>
      <p>{String(x.brief)}</p>
      <p className="learn-muted">You can edit only <code>{String(x.testPath)}</code>. The server runs <code>{((x.argv as string[]) ?? []).join(" ")}</code>. The planted bug: {String(x.bug)}</p>
      <textarea aria-label={`Test file ${String(x.testPath)}`} value={content} onChange={(e) => setContent(e.target.value)} rows={14} spellCheck={false} className="learn-editor" />
      <div className="learn-row">
        <button type="button" onClick={() => void save()}>Save the test</button>
        <button type="button" disabled={state.running} onClick={() => void save().then(() => start("/api/exercises/close-gap/run", { exercise: x.id }))}>Save and run</button>
        {message && <span className="learn-muted">{message}</span>}
      </div>
      <RunLog state={state} onStop={stop} />
      {g && <p className={`learn-grade ${g.correct ? "ok" : "no"}`} data-testid="grade">{String(g.message)}</p>}
    </div>
  );
}

function ExplainBack({ x }: { x: Exercise }) {
  const provider = useProvider();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [r, setR] = useState<Json | null>(null);
  const [error, setError] = useState("");
  async function grade() {
    setBusy(true); setError(""); setR(null);
    try { setR(await postJson("/api/exercises/explain", { claim: x.claim, text, provider: provider || "claude" })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const g = (r?.grade as Json) ?? null;
  return (
    <div className="learn-card" data-testid={`exercise-${x.id}`}>
      <h3>{x.title}</h3>
      <p>{String(x.prompt)}</p>
      <textarea aria-label="Your explanation" value={text} onChange={(e) => setText(e.target.value)} rows={5} />
      <button type="button" disabled={!text.trim() || busy} onClick={() => void grade()}>{busy ? "Grading…" : "Grade my explanation"}</button>
      {g && (
        <div className="learn-guess" data-testid="explain-grade">
          <p className="learn-kicker">{String(r?.label)}</p>
          <p>Score {String(g.score)} of 3. {String(g.feedback ?? "")}</p>
          {Array.isArray(g.missing) && g.missing.length > 0 && <p>Missing: {(g.missing as string[]).join("; ")}</p>}
        </div>
      )}
      {error && <p role="alert" className="learn-error">{error}</p>}
    </div>
  );
}

export function ExercisesView({ kind }: { kind: string }) {
  const [list, setList] = useState<Exercise[]>([]);
  const [progress, setProgress] = useState<Json>({});
  const [error, setError] = useState("");
  useEffect(() => {
    getJson<Exercise[]>("/api/exercises").then(setList).catch((e: Error) => setError(e.message));
    getJson<Json>("/api/progress").then(setProgress).catch(() => undefined);
  }, [kind]);
  const shown = useMemo(() => list.filter((x) => x.kind === kind), [list, kind]);
  const done = (progress.exercises as Record<string, { passed?: boolean }>) ?? {};
  const tests = (progress.closeGapTests as Record<string, { content?: string }>) ?? {};
  return (
    <section className="learn-exercises" aria-labelledby="ex-title">
      <h2 id="ex-title">{KIND_LABEL[kind] ?? kind}</h2>
      <p className="learn-muted">{KIND_INTRO[kind]}</p>
      {error && <p role="alert" className="learn-error">{error}</p>}
      {!shown.length && !error && <p>This run has no exercises of this kind.</p>}
      {shown.map((x) => (
        <div key={x.id} className={done[x.id]?.passed ? "learn-done" : ""}>
          {x.kind === "predict" && <Predict x={x} />}
          {x.kind === "find-line" && <FindLine x={x} />}
          {x.kind === "trace" && <Trace x={x} />}
          {x.kind === "close-gap" && <CloseGap x={x} saved={tests[x.id]?.content} />}
          {x.kind === "explain-back" && <ExplainBack x={x} />}
        </div>
      ))}
    </section>
  );
}

export const EXERCISE_KINDS = Object.keys(KIND_LABEL);
export { KIND_LABEL };
