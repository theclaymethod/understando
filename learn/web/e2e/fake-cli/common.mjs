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

function globRegex(glob) {
  let re = "";
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === "*" && glob[i + 1] === "*") { re += glob[i + 2] === "/" ? "(?:.*/)?" : ".*"; i += glob[i + 2] === "/" ? 2 : 1; }
    else if (c === "*") re += "[^/]*";
    else re += c.replace(/[.+?^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${re}$`);
}

/** Model a read deny list: an entry denies itself, everything under it, or each glob match. */
export function readDenied(path, deny) {
  const target = isAbsolute(path) ? path : resolve(process.cwd(), path);
  return deny.some((d) => (d.includes("*") ? globRegex(d).test(target) : target === d || target.startsWith(`${d}/`)));
}

export function sandboxedRead(path, deny) {
  if (readDenied(path, deny)) return { ok: false, detail: `cat: ${path}: Operation not permitted` };
  try { return { ok: true, detail: readFileSync(path, "utf8") }; } catch (e) { return { ok: false, detail: `cat: ${path}: ${e.code}` }; }
}

/** The filesystem entries of `-c permissions.learn={..., filesystem={"p"="deny", ...}}`. */
export function codexProfile(argv) {
  const arg = argv.find((a) => a.startsWith("permissions.learn="));
  if (!arg) return null;
  const entries = [...arg.matchAll(/("(?:[^"\\]|\\.)*")="(read|write|deny)"/g)].map((m) => ({ path: JSON.parse(m[1]), access: m[2] }));
  return { extendsReadOnly: arg.includes('extends=":read-only"'), deny: entries.filter((e) => e.access === "deny").map((e) => e.path), write: entries.filter((e) => e.access === "write").map((e) => e.path) };
}
