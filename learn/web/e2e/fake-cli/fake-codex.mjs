#!/usr/bin/env node
// A fake `codex` CLI for the learn e2e tests: --version, login status, `mcp list --json` and
// `app-server --stdio` (JSON-RPC). It logs thread/start and turn/start params, cwd and env.
import { createInterface } from "node:readline";
import { codexProfile, log, readConfig, sandboxedRead, sandboxedWrite } from "./common.mjs";

const argv = process.argv.slice(2);
const config = readConfig();
if (argv[0] === "--version") { process.stdout.write("codex-cli 0.144.5 (e2e fake)\n"); process.exit(0); }
if (argv[0] === "login" && argv[1] === "status") { process.stdout.write("Logged in using an API key (e2e fake)\n"); process.exit(0); }
if (argv[0] === "mcp" && argv[1] === "list") {
  // One configured server. The -c overrides that the server passes turn it off.
  const off = argv.some((a) => a.startsWith("mcp_servers.docs=") && a.includes("enabled=false"));
  log({ cli: "codex", role: "mcp-list", argv });
  process.stdout.write(JSON.stringify([{ name: "docs", enabled: !off, transport: { type: "streamable_http", url: "https://example.invalid/mcp" } }]) + "\n");
  process.exit(0);
}
if (argv[0] !== "app-server") process.exit(0);

const send = (m) => process.stdout.write(JSON.stringify(m) + "\n");
// The profile is Codex's own seatbelt. `breakDeny` models a layer that does not deny reads.
const profile = codexProfile(argv);
const denyList = profile && !config.breakDeny ? profile.deny : [];
const shellOff = argv.includes("features.shell_tool=false");
let thread = null;
const rl = createInterface({ input: process.stdin });
for await (const line of rl) {
  let m; try { m = JSON.parse(line); } catch { continue; }
  if (m.method === "initialize") send({ id: m.id, result: { userAgent: "fake" } });
  else if (m.method === "account/login/start") { log({ cli: "codex", role: "login", type: m.params?.type, keyLength: String(m.params?.apiKey ?? "").length }); send({ id: m.id, result: { type: "apiKey" } }); }
  else if (m.method === "command/exec") {
    const [cmd, path] = m.params.command;
    const roots = profile ? profile.write : [];
    const r = cmd === "cat" ? sandboxedRead(path, denyList) : cmd === "touch" ? sandboxedWrite(path, "", config.breakDeny ? ["/"] : roots) : { ok: true, detail: "" };
    log({ cli: "codex", role: "probe", command: m.params.command, ok: r.ok });
    send({ id: m.id, result: { exitCode: r.ok ? 0 : 1, stdout: "", stderr: r.ok ? "" : r.detail } });
  }
  else if (m.method === "model/list") send({ id: m.id, result: { data: [{ model: "gpt-e2e", isDefault: true }] } });
  else if (m.method === "thread/start") { thread = m.params; log({ cli: "codex", role: "thread", argv, params: { ...m.params, baseInstructions: undefined, developerInstructions: undefined } }); send({ id: m.id, result: { thread: { id: "t1" }, model: "gpt-e2e", sandbox: profile ? { type: "workspaceWrite", writableRoots: [], networkAccess: false } : { type: "readOnly", networkAccess: false } } }); }
  else if (m.method === "turn/start") {
    const p = m.params;
    const grader = String(thread?.baseInstructions ?? "").startsWith("You grade one explanation");
    log({ cli: "codex", role: grader ? "grader" : "tutor", params: { ...p, input: undefined }, prompt: p.input?.[0]?.text ?? "" });
    send({ id: m.id, result: { turn: { id: "u1" } } });
    const roots = profile && !shellOff ? profile.write : [];
    if (!grader && !shellOff) for (const [n, r0] of (config.reads ?? []).entries()) {
      const item = { id: `read${n}`, type: "commandExecution", command: `cat ${r0}` };
      send({ method: "item/started", params: { turnId: "u1", item } });
      const r = sandboxedRead(r0, denyList);
      send({ method: "item/completed", params: { turnId: "u1", item: { ...item, status: r.ok ? "completed" : "failed", aggregatedOutput: r.detail } } });
    }
    if (!grader && !shellOff) for (const [n, w] of (config.writes ?? []).entries()) {
      const item = { id: `cmd${n}`, type: "commandExecution", command: `cat > ${w.path}` };
      send({ method: "item/started", params: { turnId: "u1", item } });
      const r = sandboxedWrite(w.path, w.content, roots);
      send({ method: "item/completed", params: { turnId: "u1", item: { ...item, status: r.ok ? "completed" : "failed", aggregatedOutput: r.detail } } });
    }
    const text = grader ? JSON.stringify(config.grade ?? { score: 1, covered: [], missing: ["the control"], wrong: [], feedback: "e2e fake codex grade." }) : (config.codexReply ?? config.tutorReply ?? "e2e codex reply.");
    send({ method: "item/agentMessage/delta", params: { turnId: "u1", delta: text } });
    send({ method: "item/completed", params: { turnId: "u1", item: { type: "agentMessage", text } } });
    send({ method: "turn/completed", params: { threadId: "t1", turn: { id: "u1", status: "completed" } } });
  }
}
