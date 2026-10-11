import { useEffect, useRef, useState } from "react";
import { getJson, postJson, postStream, type Json, type Provider, type Setup, type StreamEvent } from "./api";
import { RunLog, useGradedRun } from "./GradedRun";
import { Markdownish } from "./Markdownish";
import { setProvider, useProvider } from "./provider";
import { onAskTutor } from "./tutor-bus";

type Tool = { id: string; name: string; status: string; detail: string };
type Proposal = { id: string; kind: string; target: string; verifier: string; description: string; argv: string[]; cwd: string };
type Message = { id: string; role: "user" | "assistant"; text: string; status?: string; provider?: string; model?: string | null;
  tools?: Tool[]; actions?: Proposal[]; refused?: string[] };

const LEVELS = [
  { id: "new", label: "New to this stack" },
  { id: "familiar", label: "Knows the stack" },
  { id: "reviewer", label: "Reviewer" },
];

function ProposalCard({ p }: { p: Proposal }) {
  const [state, setStateName] = useState<"pending" | "dismissed" | "confirmed">("pending");
  const run = useGradedRun();
  return (
    <div className="learn-proposal" data-testid="proposal" data-target={p.target}>
      <p><strong>The tutor asks for a graded run:</strong> {p.kind === "run-control" ? `control ${p.target} on ${p.verifier}` : `verifier ${p.target}`}. {p.description}</p>
      <p className="learn-muted">The server resets the worktree, then runs <code>{(p.argv ?? []).join(" ")}</code> in <code>{p.cwd}</code>.</p>
      {state === "pending" && (
        <div className="learn-row">
          <button type="button" onClick={() => { setStateName("confirmed"); void run.start("/api/actions/confirm", { proposalId: p.id }); }}>Confirm and run</button>
          <button type="button" className="learn-link" onClick={() => setStateName("dismissed")}>Dismiss</button>
        </div>
      )}
      {state === "dismissed" && <p className="learn-muted">You dismissed the run that the tutor asked for.</p>}
      <RunLog state={run.state} onStop={run.stop} />
    </div>
  );
}

function ProviderPicker({ setup }: { setup: Setup | null }) {
  const provider = useProvider();
  const current = provider || setup?.defaultProvider || "claude";
  const status = setup?.providers.find((p) => p.id === current);
  return (
    <div className="learn-provider">
      <div role="radiogroup" aria-label="Tutor provider" className="learn-row">
        {(["claude", "codex"] as Provider[]).map((id) => {
          const s = setup?.providers.find((p) => p.id === id);
          return (
            <label key={id} className={`learn-pill ${current === id ? "on" : ""}`}>
              <input type="radio" name="provider" value={id} checked={current === id} onChange={() => setProvider(id)} />
              {id === "claude" ? "Claude Code" : "Codex"} {s ? (s.ready ? "· ready" : "· not ready") : ""}
            </label>
          );
        })}
      </div>
      {status && (
        <p className="learn-muted" data-testid="billing">
          Bills to: {status.billing} Model: {status.model ?? "the CLI default"}. Shell: {status.shell ? "on, in the OS sandbox (no network, writes only in the worktree)" : "off"}.
        </p>
      )}
    </div>
  );
}

export function TutorPanel() {
  const provider = useProvider();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [level, setLevel] = useState("familiar");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const context = useRef<Record<string, string>>({});
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getJson<Setup>("/api/setup").then(setSetup).catch(() => undefined);
    getJson<{ messages: Message[] }>("/api/tutor/conversation").then((c) => setMessages(c.messages ?? [])).catch(() => undefined);
  }, []);
  useEffect(() => onAskTutor((ask) => { context.current = ask.context ?? {}; void send(ask.message); }));
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight }); }, [messages]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    const chosen = provider || setup?.defaultProvider || "claude";
    setBusy(true); setError(""); setInput("");
    const user: Message = { id: crypto.randomUUID(), role: "user", text: message };
    setMessages((m) => [...m, user]);
    let assistantId = "";
    const patch = (fn: (m: Message) => Message) => setMessages((all) => all.map((m) => (m.id === assistantId ? fn(m) : m)));
    try {
      await postStream("/api/tutor/chat", { provider: chosen, message, level, context: context.current }, (e: StreamEvent) => {
        if (e.type === "message") {
          const m = e.message as Message;
          if (!assistantId) { assistantId = m.id; setMessages((all) => [...all, { ...m, actions: [], tools: [], refused: [] }]); }
          else patch((old) => ({ ...old, text: m.text, status: m.status, model: m.model, provider: m.provider }));
        }
        if (e.type === "delta") patch((m) => ({ ...m, text: m.text + String(e.text) }));
        if (e.type === "status") setStatus(String(e.message));
        if (e.type === "tool") {
          const t = e.tool as Tool;
          patch((m) => {
            const tools = [...(m.tools ?? [])];
            const i = tools.findIndex((x) => x.id === t.id);
            if (i >= 0) tools[i] = t; else tools.push(t);
            return { ...m, tools };
          });
        }
        if (e.type === "action") patch((m) => ({ ...m, actions: [...(m.actions ?? []), e.proposal as Proposal] }));
        if (e.type === "action_refused") patch((m) => ({ ...m, refused: [...(m.refused ?? []), String(e.reason)] }));
        if (e.type === "error") setError(String(e.message));
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false); setStatus(""); context.current = {};
    }
  }

  return (
    <aside className="learn-tutor" aria-labelledby="tutor-title" data-testid="tutor-panel">
      <h2 id="tutor-title">Tutor</h2>
      <p className="learn-kicker">Live answers are model-generated, at guess tier.</p>
      <ProviderPicker setup={setup} />
      <label className="learn-row">Your level{" "}
        <select value={level} onChange={(e) => setLevel(e.target.value)}>{LEVELS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}</select>
      </label>
      <div className="learn-messages" ref={list}>
        {messages.length === 0 && <p className="learn-muted">Ask about a claim, a verifier or a line of code. The tutor reads and runs code in a sandboxed scratch worktree.</p>}
        {messages.map((m) => (
          <div key={m.id} className={`learn-msg ${m.role}`} data-testid={`msg-${m.role}`}>
            {m.role === "assistant" && <p className="learn-kicker">Model-generated answer ({m.provider ?? ""}{m.model ? `, ${m.model}` : ""}, guess tier)</p>}
            <Markdownish text={m.text} />
            {(m.tools ?? []).length > 0 && (
              <details className="learn-tools"><summary>Tutor shell and file tools ({m.tools!.length}), guess tier</summary>
                <ul>{m.tools!.map((t) => <li key={t.id}><code>{t.name}</code> {t.status}: <code>{t.detail}</code></li>)}</ul>
              </details>
            )}
            {(m.refused ?? []).map((r, i) => <p key={i} className="learn-refused" data-testid="refused">{r}</p>)}
            {(m.actions ?? []).map((p) => <ProposalCard key={p.id} p={p} />)}
          </div>
        ))}
      </div>
      {status && <p role="status" className="learn-muted">{status}</p>}
      {error && <p role="alert" className="learn-error">{error}</p>}
      <form className="learn-compose" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
        <textarea aria-label="Message to the tutor" value={input} onChange={(e) => setInput(e.target.value)} rows={3}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); } }} />
        <div className="learn-row">
          <button type="submit" disabled={busy || !input.trim()}>Send</button>
          {busy && <button type="button" className="learn-link" onClick={() => void postJson("/api/tutor/cancel", {})}>Stop</button>}
        </div>
      </form>
    </aside>
  );
}

export type { Json };
