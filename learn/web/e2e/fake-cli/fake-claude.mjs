#!/usr/bin/env node
// A fake `claude` CLI for the learn e2e tests: --version, auth status, --help and `-p` calls in
// the stream-json format. It logs its argv (without the system prompt), cwd and settings.
import { log, readConfig, sandboxedRead, sandboxedWrite } from "./common.mjs";

const argv = process.argv.slice(2);
const flag = (name) => { const i = argv.indexOf(name); return i < 0 ? undefined : argv[i + 1]; };

if (argv[0] === "--version") { process.stdout.write("2.1.289 (Claude Code, e2e fake)\n"); process.exit(0); }
if (argv[0] === "auth" && argv[1] === "status") { process.stdout.write(JSON.stringify({ loggedIn: true, authMethod: "claude.ai", subscriptionType: "e2e" }) + "\n"); process.exit(0); }
if (argv[0] === "--help") { process.stdout.write("  --restricted   Restricted mode\n  --tools <tools...>\n"); process.exit(0); }
if (!argv.includes("-p")) process.exit(0);

let prompt = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) prompt += chunk;
const system = flag("--system-prompt") ?? "";
const role = system.startsWith("You grade one explanation") ? "grader" : "tutor";
const settings = JSON.parse(flag("--settings") ?? "{}");
const schema = flag("--json-schema") ? JSON.parse(flag("--json-schema")) : null;
const logged = argv.filter((a, i) => a !== "--system-prompt" && argv[i - 1] !== "--system-prompt");
log({ cli: "claude", role, argv: logged, settings, prompt, systemPrompt: system.slice(0, 400) });
const config = readConfig();
const tools = (flag("--tools") ?? "").split(",").filter(Boolean);
const shell = tools.includes("Bash") && settings.sandbox?.enabled === true;

const lines = [{ type: "system", subtype: "init", model: "claude-e2e" }];
if (role === "tutor") {
  for (const [n, path] of (config.reads ?? []).entries()) {
    const id = `toolu_r${n}`;
    lines.push({ type: "assistant", message: { model: "claude-e2e", content: [{ type: "tool_use", id, name: "Bash", input: { command: `cat ${path}` } }] } });
    const r = shell ? sandboxedRead(path, settings.sandbox.filesystem?.denyRead ?? []) : { ok: false, detail: "Bash is not available" };
    lines.push({ type: "user", message: { content: [{ type: "tool_result", tool_use_id: id, is_error: !r.ok, content: r.detail }] } });
  }
  for (const [n, w] of (config.writes ?? []).entries()) {
    const id = `toolu_${n}`;
    lines.push({ type: "assistant", message: { model: "claude-e2e", content: [{ type: "tool_use", id, name: "Bash", input: { command: `cat > ${w.path}` } }] } });
    const r = shell ? sandboxedWrite(w.path, w.content, [process.cwd()]) : { ok: false, detail: "Bash is not available" };
    lines.push({ type: "user", message: { content: [{ type: "tool_result", tool_use_id: id, is_error: !r.ok, content: r.detail }] } });
  }
}
let text, structured;
if (schema) { structured = config.grade ?? { score: 2, covered: ["the guard"], missing: ["the control"], wrong: [], feedback: "e2e fake grade." }; text = JSON.stringify(structured); }
else text = config.tutorReply ?? "e2e tutor reply.";
if (!schema) {
  const half = Math.ceil(text.length / 2);
  for (const part of [text.slice(0, half), text.slice(half)]) lines.push({ type: "stream_event", event: { type: "content_block_delta", delta: { type: "text_delta", text: part } } });
}
lines.push({ type: "assistant", message: { model: "claude-e2e", content: [{ type: "text", text }] } });
lines.push({ type: "result", subtype: "success", is_error: false, result: text, usage: { input_tokens: 10, output_tokens: 5 }, ...(schema ? { structured_output: structured } : {}) });
process.stdout.write(lines.map((l) => JSON.stringify(l)).join("\n") + "\n");
