// Shared parts of the fake CLIs. They make no model call and no network call.
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";

export function readConfig() {
  try { return JSON.parse(readFileSync(process.env.FAKE_CLI_CONFIG, "utf8")); } catch { return {}; }
}

export function log(entry) {
  if (!process.env.FAKE_CLI_LOG) return;
  const env = {};
  for (const k of ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CLAUDECODE", "CODEX_HOME", "FAKE_SECRET_TOKEN"]) env[k] = k in process.env ? (k === "CODEX_HOME" ? process.env[k] : "set") : null;
  appendFileSync(process.env.FAKE_CLI_LOG, JSON.stringify({ at: new Date().toISOString(), cwd: process.cwd(), env, ...entry }) + "\n");
}

/**
 * Model the OS sandbox of the real CLI from the config that the server passed: a write is
 * allowed only under one of `roots`. The real sandbox is checked in learn/web/e2e/sandbox-check.sh.
 */
export function sandboxedWrite(path, content, roots) {
  const target = isAbsolute(path) ? path : resolve(process.cwd(), path);
  const inside = roots.some((r) => { const rel = relative(r, target); return rel && !rel.startsWith("..") && !isAbsolute(rel); });
  if (!inside) return { ok: false, detail: `${target}: Operation not permitted (sandbox: write outside the allowed roots)` };
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content);
  return { ok: true, detail: `wrote ${target}` };
}
