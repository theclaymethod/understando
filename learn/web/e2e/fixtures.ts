// The e2e harness: copy the fixture run, start the real binary with fake claude and codex CLIs
// first on PATH, and give tests small helpers. No test makes a model call.
import { test as base, type Page } from "@playwright/test";
import { spawn, type ChildProcess, execFileSync } from "node:child_process";
import { accessSync, constants } from "node:fs";
import { chmod, cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:net";

const here = fileURLToPath(new URL(".", import.meta.url));

export type Call = { cli: string; role: string; cwd: string; env: Record<string, string | null>; argv?: string[]; settings?: any; params?: any; prompt?: string; type?: string; keyLength?: number };

export interface Learn {
  origin: string;
  repo: string;
  run: string;
  scratch: string;
  worktree: string;
  dir: string;
  output: () => string;
  open(page: Page, route?: string): Promise<void>;
  configureFake(config: object): Promise<void>;
  calls(filter?: (c: Call) => boolean): Promise<Call[]>;
  post(path: string, body: unknown): Promise<{ status: number; events: any[]; json: any }>;
  stop(): Promise<number | null>;
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.listen(0, "127.0.0.1", () => { const a = s.address(); s.close(() => (a && typeof a === "object" ? resolve(a.port) : reject(new Error("no port")))); });
  });
}

function toolDir(name: string) {
  for (const dir of (process.env.PATH ?? "").split(delimiter)) {
    try { accessSync(join(dir, name), constants.X_OK); return dir; } catch { /* next */ }
  }
  throw new Error(`The e2e harness needs ${name} on PATH.`);
}

export type LaunchOptions = { repoName?: string; fiEnv?: string; mutateMap?: (map: any) => void; fakeConfig?: object };

async function launch(opts: LaunchOptions = {}): Promise<Learn> {
  const dir = await mkdtemp(join(tmpdir(), "learn-e2e-"));
  const template = process.env.LEARN_E2E_TEMPLATE!;
  await cp(join(template, "repo"), join(dir, "repo"), { recursive: true });
  await cp(join(template, "run"), join(dir, "run"), { recursive: true });
  if (opts.repoName || opts.mutateMap) {
    const mapPath = join(dir, "run", "trust-map.json");
    const map = JSON.parse(await readFile(mapPath, "utf8"));
    if (opts.repoName) map.repo = opts.repoName;
    opts.mutateMap?.(map);
    await writeFile(mapPath, JSON.stringify(map, null, 2));
  }
  const bin = join(dir, "bin");
  await mkdir(bin);
  for (const name of ["claude", "codex"]) {
    await writeFile(join(bin, name), `#!/bin/sh\nexec "${process.execPath}" "${join(here, "fake-cli", `fake-${name}.mjs`)}" "$@"\n`);
    await chmod(join(bin, name), 0o755);
  }
  const fakeConfig = join(dir, "fake-config.json");
  const fakeLog = join(dir, "fake-calls.jsonl");
  await writeFile(fakeConfig, JSON.stringify(opts.fakeConfig ?? {}));
  await writeFile(fakeLog, "");
  const codexHome = join(dir, "codex-home");
  await mkdir(codexHome);
  const port = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  const env: Record<string, string> = {
    HOME: process.env.HOME ?? dir,
    TMPDIR: process.env.TMPDIR ?? tmpdir(),
    PATH: [...new Set([bin, dirname(process.execPath), ...["git", "python3", "bash", "sh"].map(toolDir)])].join(delimiter),
    FAKE_CLI_CONFIG: fakeConfig,
    FAKE_CLI_LOG: fakeLog,
    CODEX_HOME: codexHome,
    // Secrets that must never reach a child process.
    OPENAI_API_KEY: "sk-e2e-must-not-leak-000000000000",
    ANTHROPIC_API_KEY: "sk-ant-e2e-must-not-leak-000000000000",
    FAKE_SECRET_TOKEN: "e2e-must-not-leak",
    CLAUDECODE: "1",
  };
  if (opts.fiEnv) env.UNDERSTANDO_FI_ENV = opts.fiEnv;
  let out = "";
  const child: ChildProcess = spawn(process.env.UNDERSTANDO_LEARN_BIN!, [join(dir, "run"), "--repo", join(dir, "repo"), "--port", String(port), "--no-open"], { env, stdio: ["ignore", "pipe", "pipe"] });
  child.stdout!.on("data", (c) => { out += c; });
  child.stderr!.on("data", (c) => { out += c; });
  const deadline = Date.now() + 20_000;
  for (;;) {
    if (child.exitCode !== null) throw new Error(`understando-learn exited:\n${out}`);
    if (/^worktree: /m.test(out)) {
      try { if ((await fetch(`${origin}/api/health`)).ok) break; } catch { /* not yet */ }
    }
    if (Date.now() > deadline) throw new Error(`understando-learn did not start:\n${out}`);
    await new Promise((r) => setTimeout(r, 100));
  }
  const scratch = /^scratch: (.+)$/m.exec(out)![1];
  const worktree = /^worktree: (.+)$/m.exec(out)![1];
  let stopped = false;
  const learn: Learn = {
    origin, repo: join(dir, "repo"), run: join(dir, "run"), scratch, worktree, dir,
    output: () => out,
    async open(page, route = "") {
      await page.addInitScript(() => localStorage.setItem("understando:tutor-provider", "claude"));
      await page.goto(`${origin}/${route ? `#${route}` : ""}`);
    },
    async configureFake(config) { await writeFile(fakeConfig, JSON.stringify(config)); },
    async calls(filter) {
      const lines = (await readFile(fakeLog, "utf8")).split("\n").filter(Boolean).map((l) => JSON.parse(l) as Call);
      return filter ? lines.filter(filter) : lines;
    },
    async post(path, body) {
      const r = await fetch(`${origin}${path}`, { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const text = await r.text();
      let json: any = null;
      try { json = JSON.parse(text); } catch { /* ndjson */ }
      const events = text.split("\n").filter(Boolean).flatMap((l) => { try { return [JSON.parse(l)]; } catch { return []; } });
      return { status: r.status, events, json };
    },
    async stop() {
      if (stopped) return child.exitCode;
      stopped = true;
      if (child.exitCode === null) {
        child.kill("SIGTERM");
        await new Promise<void>((r) => { child.once("exit", () => r()); setTimeout(r, 8000); });
      }
      return child.exitCode;
    },
  };
  return learn;
}

export const test = base.extend<{ startLearn: (o?: LaunchOptions) => Promise<Learn>; learn: Learn }>({
  // eslint-disable-next-line no-empty-pattern
  startLearn: async ({}, use) => {
    const started: Learn[] = [];
    await use(async (o) => { const l = await launch(o); started.push(l); return l; });
    for (const l of started) { await l.stop(); await rm(l.dir, { recursive: true, force: true }); }
  },
  learn: async ({ startLearn }, use) => { await use(await startLearn()); },
});
export const expect = test.expect;

export function worktreeList(repo: string) {
  return execFileSync("git", ["-C", repo, "worktree", "list", "--porcelain"], { encoding: "utf8" });
}
