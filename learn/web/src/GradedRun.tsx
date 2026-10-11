import { useCallback, useRef, useState } from "react";
import { postStream, postJson, type Json, type StreamEvent } from "./api";

export type RunState = {
  running: boolean;
  statuses: string[];
  output: string[];
  result: Json | null;
  grade: Json | null;
  error: string;
};

const empty: RunState = { running: false, statuses: [], output: [], result: null, grade: null, error: "" };

/** A server-run, fact-tier run: reset, setup, the recorded edit, the recorded argv. */
export function useGradedRun() {
  const [state, setState] = useState<RunState>(empty);
  const abort = useRef<AbortController | null>(null);
  const start = useCallback(async (path: string, body: unknown) => {
    abort.current = new AbortController();
    setState({ ...empty, running: true });
    try {
      await postStream(path, body, (e: StreamEvent) => {
        setState((s) => {
          if (e.type === "status") return { ...s, statuses: [...s.statuses, String(e.message)] };
          if (e.type === "output") return { ...s, output: [...s.output.slice(-400), String(e.text)] };
          if (e.type === "result") return { ...s, result: e.result as Json };
          if (e.type === "grade") return { ...s, grade: e.grade as Json };
          if (e.type === "error") return { ...s, error: String(e.message) };
          return s;
        });
      }, abort.current.signal);
    } catch (err) {
      setState((s) => ({ ...s, error: (err as Error).message }));
    } finally {
      setState((s) => ({ ...s, running: false }));
    }
  }, []);
  const stop = useCallback(() => { void postJson("/api/run/cancel", {}).catch(() => undefined); }, []);
  return { state, start, stop };
}

function badge(status: string) {
  return <span className={`learn-badge learn-badge-${status}`} data-status={status}>{status}</span>;
}

export function RunLog({ state, onStop }: { state: RunState; onStop?: () => void }) {
  const r = state.result;
  if (!state.running && !r && !state.error && !state.statuses.length) return null;
  const status = typeof r?.status === "string" ? r.status : "";
  return (
    <div className="learn-run" aria-live="polite" data-testid="run-log">
      <p className="learn-kicker">This is a server run at fact tier: the server reset the worktree, then ran the recorded command.</p>
      {state.statuses.length > 0 && <ul className="learn-steps">{state.statuses.map((s, i) => <li key={i}>{s}</li>)}</ul>}
      {state.running && <p role="status">Running… {onStop && <button type="button" className="learn-link" onClick={onStop}>Stop</button>}</p>}
      {r && (
        <div className="learn-result" data-testid="run-result" data-status={status}>
          <p>Result: {badge(status)} {r.exit !== undefined && r.exit !== null ? `exit ${String(r.exit)}` : ""} {r.seconds ? `in ${String(r.seconds)} s` : ""}
            {r.matched === false && " The output does not hold the expected pattern, so this red is for the wrong reason."}</p>
          {r.cannotFail === true && (
            <p className="learn-flag" role="alert" data-testid="cannot-fail">
              This check cannot fail: the planted bug did not make it fail. It checks nothing that the control broke.
            </p>
          )}
          {Boolean(r.recorded) && typeof (r.recorded as Json).status === "string" && (
            <p className="learn-muted">Recorded in the trust map: {String((r.recorded as Json).status)}. This live run does not change a verdict.</p>
          )}
          {typeof r.note === "string" && <p className="learn-muted">{r.note}</p>}
          {typeof r.outputTail === "string" && r.outputTail && <details><summary>Output</summary><pre className="learn-pre">{r.outputTail}</pre></details>}
        </div>
      )}
      {!r && state.output.length > 0 && <pre className="learn-pre learn-live">{state.output.slice(-30).join("\n")}</pre>}
      {state.error && <p role="alert" className="learn-error">{state.error}</p>}
    </div>
  );
}
