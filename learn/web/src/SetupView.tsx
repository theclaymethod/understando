import { useEffect, useState } from "react";
import { getJson, type Setup } from "./api";

export function SetupView() {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  async function check(refresh: boolean) {
    setChecking(true); setError("");
    try { setSetup(await getJson<Setup>(`/api/setup${refresh ? "?refresh=1" : ""}`)); } catch (e) { setError((e as Error).message); } finally { setChecking(false); }
  }
  useEffect(() => { void check(false); }, []);
  return (
    <section aria-labelledby="setup-title" className="learn-setup">
      <h2 id="setup-title">Setup doctor</h2>
      <p className="learn-muted">The doctor checks git, the scratch worktree, the OS sandbox, Claude Code and Codex.</p>
      <button type="button" disabled={checking} onClick={() => void check(true)}>{checking ? "Checking…" : "Check again"}</button>
      {error && <p role="alert" className="learn-error">{error}</p>}
      {setup && (
        <>
          <p role="status">{setup.ready ? "Required setup is ready." : "Do the steps below, then check again."}</p>
          <table className="learn-table">
            <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
            <tbody>{setup.checks.map((c) => (
              <tr key={c.id} data-testid={`check-${c.id}`}><td>{c.label}{c.required ? "" : " (optional)"}</td><td><span className={`learn-badge learn-badge-${c.status === "ready" ? "green" : "red"}`}>{c.status}</span></td><td>{c.detail}{c.version ? ` (${c.version})` : ""}</td></tr>
            ))}</tbody>
          </table>
          <h3>Providers</h3>
          <ul>{setup.providers.map((p) => <li key={p.id} data-testid={`provider-${p.id}`}><strong>{p.label}</strong>: {p.ready ? "ready" : "not ready"}. Bills to: {p.billing} Model: {p.model ?? "the CLI default"}. Shell: {p.shell ? "sandboxed" : "off"}.</li>)}</ul>
        </>
      )}
    </section>
  );
}
