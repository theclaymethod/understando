// Calls to the local server. Every POST sends JSON, so the server's Origin guard applies.

export type Json = Record<string, unknown>;
export type StreamEvent = { type: string; [key: string]: unknown };

export class ApiError extends Error {}

export async function getJson<T = Json>(path: string): Promise<T> {
  const r = await fetch(path, { headers: { Accept: "application/json" } });
  const v = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError((v as Json).error as string ?? `The server answered ${r.status}.`);
  return v as T;
}

export async function postJson<T = Json>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const v = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError((v as Json).error as string ?? `The server answered ${r.status}.`);
  return v as T;
}

const KNOWN = new Set(["start", "status", "output", "result", "grade", "done", "error", "message", "delta", "tool", "action", "action_refused"]);

/** POST, then read the NDJSON stream line by line. Unknown event types are dropped. */
export async function postStream(path: string, body: unknown, onEvent: (e: StreamEvent) => void, signal?: AbortSignal) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!r.ok) {
    const v = await r.json().catch(() => ({}));
    throw new ApiError((v as Json).error as string ?? `The server answered ${r.status}.`);
  }
  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  for (;;) {
    const { done, value } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const lines = pending.split("\n");
    pending = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let e: unknown;
      try { e = JSON.parse(line); } catch { continue; }
      if (e && typeof e === "object" && KNOWN.has((e as StreamEvent).type)) onEvent(e as StreamEvent);
    }
    if (done) break;
  }
}

export type Provider = "claude" | "codex";
export type ProviderStatus = { id: Provider; label: string; installed: boolean; ready: boolean; billing: string; model: string | null; shell: boolean };
export type Check = { id: string; label: string; required: boolean; status: string; detail: string; version?: string };
export type Setup = { ready: boolean; defaultProvider: Provider; providers: ProviderStatus[]; checks: Check[]; sandbox: { ready: boolean; detail: string } };
export type Session = { repo: string; pr: number | null; title: string; head: string; summary: Record<string, number>; worktree: string; scratch: string; shell: boolean; hasChapters: boolean; hasExplainerHtml: boolean };
