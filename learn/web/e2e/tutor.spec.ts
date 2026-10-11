import { existsSync, readFileSync, writeFileSync, mkdtempSync, mkdirSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test, expect, worktreeList } from "./fixtures";

async function ask(page: import("@playwright/test").Page, text: string) {
  await page.getByLabel("Message to the tutor").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("msg-assistant").last()).toBeVisible({ timeout: 30_000 });
}

for (const provider of ["claude", "codex"] as const) {
  test(`${provider}: the tutor works in the scratch worktree, never in the checkout`, async ({ page, learn }) => {
    await learn.configureFake({ tutorReply: "The guard is in wallet/core.py:13.", codexReply: "The guard is in wallet/core.py:13." });
    await learn.open(page);
    await page.getByRole("radio", { name: provider === "claude" ? /Claude Code/ : /Codex/ }).check();
    await expect(page.getByTestId("billing")).toContainText("Bills to:");
    await ask(page, "Where is the overdraft guard?");
    await expect(page.getByTestId("msg-assistant").last()).toContainText("wallet/core.py:13");
    await expect(page.getByTestId("msg-assistant").last()).toContainText("Model-generated");
    const calls = await learn.calls((c) => c.cli === provider && (c.role === "tutor" || c.role === "thread"));
    expect(calls.length).toBeGreaterThan(0);
    for (const c of calls) {
      expect(c.cwd).toBe(learn.worktree);
      expect(c.cwd).not.toBe(learn.repo);
      expect(c.cwd.startsWith(learn.scratch)).toBe(true);
      expect(c.env.OPENAI_API_KEY).toBeNull();
      expect(c.env.ANTHROPIC_API_KEY).toBeNull();
      expect(c.env.CODEX_API_KEY).toBeNull();
      expect(c.env.FAKE_SECRET_TOKEN).toBeNull();
      expect(c.env.CLAUDECODE).toBeNull();
    }
    if (provider === "codex") expect(calls.find((c) => c.role === "thread")!.params.cwd).toBe(learn.worktree);
    // The tutor's prompt holds the trust map, and the saved conversation is under my-work.
    const saved = JSON.parse(readFileSync(join(learn.run, "my-work", "tutor-conversation.json"), "utf8"));
    expect(saved.messages.map((m: any) => m.role)).toEqual(["user", "assistant"]);
    expect(saved.messages[1].tier).toBe("guess");
  });

  test(`${provider}: the sandbox config is passed, and a shell write outside the worktree fails`, async ({ page, learn }) => {
    const outside = join(learn.repo, "tutor-was-here.txt");
    const inside = "notes/tutor-scratch.txt";
    await learn.configureFake({ writes: [{ path: outside, content: "x" }, { path: inside, content: "y" }] });
    await learn.open(page);
    await page.getByRole("radio", { name: provider === "claude" ? /Claude Code/ : /Codex/ }).check();
    await ask(page, "Write two files.");
    await expect(page.getByTestId("msg-assistant").last()).toContainText("Tutor shell and file tools (2)");
    expect(existsSync(outside)).toBe(false);
    expect(readFileSync(join(learn.worktree, inside), "utf8")).toBe("y");
    if (provider === "claude") {
      const [c] = await learn.calls((x) => x.cli === "claude" && x.role === "tutor");
      const sb = c.settings.sandbox;
      expect(sb.enabled).toBe(true);
      expect(sb.failIfUnavailable).toBe(true);
      expect(sb.allowUnsandboxedCommands).toBe(false);
      expect(sb.autoAllowBashIfSandboxed).toBe(true);
      expect(sb.network.allowedDomains).toEqual([]);
      expect(sb.filesystem.denyRead).toContain(realpathSync(learn.repo));
      expect(c.settings.disableAllHooks).toBe(true);
      const argv = c.argv!;
      const arg = (f: string) => argv[argv.indexOf(f) + 1];
      expect(arg("--tools")).toBe("Bash,Read,Grep,Glob,Edit,Write");
      expect(arg("--allowedTools")).toBe("Bash,Read,Grep,Glob,Edit,Write");
      expect(arg("--permission-mode")).toBe("dontAsk");
      expect(arg("--setting-sources")).toBe("");
      expect(arg("--mcp-config")).toBe('{"mcpServers":{}}');
      for (const f of ["--restricted", "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"]) expect(argv).toContain(f);
    } else {
      const turn = (await learn.calls((x) => x.cli === "codex" && x.role === "tutor"))[0];
      // The permission profile is the sandbox, so neither the thread nor the turn sets one.
      expect(turn.params.sandboxPolicy).toBeUndefined();
      expect(turn.params.approvalPolicy).toBe("never");
      const thread = (await learn.calls((x) => x.cli === "codex" && x.role === "thread"))[0];
      expect(thread.params.sandbox).toBeUndefined();
      const args = thread.argv!.join(" ");
      expect(args).toContain('default_permissions="learn"');
      expect(args).toContain('permissions.learn={extends=":read-only", filesystem={' + JSON.stringify(learn.worktree) + '="write"');
      for (const f of ["features.plugins=false", "features.hooks=false", "features.browser_use=false", "features.multi_agent=false", "features.memories=false", 'web_search="disabled"', 'approval_policy="never"', "mcp_servers.docs={enabled=false"]) expect(args).toContain(f);
      // The turn ran only after the deny probes passed in the same app-server.
      const probes = await learn.calls((x) => x.cli === "codex" && x.role === "probe");
      expect(probes.some((p: any) => p.command[1].endsWith("/canary/deep/.env.local") && p.ok === false)).toBe(true);
      expect(args).not.toContain("features.shell_tool=false");
    }
  });
}

test("a tutor edit in the worktree does not change a graded result, because the reset comes first", async ({ page, learn }) => {
  // The tutor rewrites BalanceTest so that it checks the value. Without a reset, control K02 would go red.
  const stricter = readFileSync(join(learn.worktree, "tests/test_core.py"), "utf8").replace("self.assertIsInstance(withdraw(10, 3), int)", "self.assertEqual(withdraw(10, 3), 7)");
  await learn.configureFake({ writes: [{ path: "tests/test_core.py", content: stricter }] });
  await learn.open(page);
  await ask(page, "Make BalanceTest stricter.");
  await expect(page.getByTestId("msg-assistant").last()).toContainText("Tutor shell and file tools (1)");
  expect(readFileSync(join(learn.worktree, "tests/test_core.py"), "utf8")).toContain("assertEqual(withdraw(10, 3), 7)");
  const run = await learn.post("/api/run", { kind: "run-control", id: "K02" });
  const result = run.events.find((e) => e.type === "result").result;
  expect(result.status).toBe("green");
  expect(result.cannotFail).toBe(true);
  // The worktree is back at the head after the graded run.
  expect(readFileSync(join(learn.worktree, "tests/test_core.py"), "utf8")).toContain("assertIsInstance(withdraw(10, 3), int)");
});

test("the scratch worktree and clone are removed on exit", async ({ learn }) => {
  const before = worktreeList(learn.repo);
  expect(existsSync(learn.worktree)).toBe(true);
  expect(before).not.toContain(learn.worktree);
  await learn.stop();
  expect(existsSync(learn.scratch)).toBe(false);
  expect(worktreeList(learn.repo)).toBe(before);
  expect(learn.output()).toContain(`scratch removed: ${learn.scratch}`);
});

test("codex on a function-intelligence run: the key comes from the .env file by RPC, with an empty CODEX_HOME", async ({ page, startLearn }) => {
  const dir = mkdtempSync(join(tmpdir(), "learn-fi-env-"));
  const envFile = join(dir, ".env");
  writeFileSync(envFile, 'OTHER=1\nOPENAI_API_KEY="sk-synthetic-e2e-key-1234567890"\n');
  const learn = await startLearn({ repoName: "Function-Health/function-intelligence", fiEnv: envFile });
  await learn.open(page);
  await page.getByRole("radio", { name: /Codex/ }).check();
  await expect(page.getByTestId("billing")).toContainText(envFile);
  await ask(page, "Hello");
  await expect(page.getByTestId("msg-assistant").last()).toContainText("e2e codex reply", { timeout: 10_000 });
  const login = await learn.calls((c) => c.cli === "codex" && c.role === "login");
  expect(login).toHaveLength(1);
  expect(login[0].type).toBe("apiKey");
  expect(login[0].keyLength).toBe("sk-synthetic-e2e-key-1234567890".length);
  for (const c of await learn.calls((x) => x.cli === "codex")) {
    expect(c.env.CODEX_API_KEY).toBeNull();
    expect(c.env.OPENAI_API_KEY).toBeNull();
    expect(c.env.CODEX_HOME!.startsWith(learn.scratch)).toBe(true);
  }
  const thread = (await learn.calls((x) => x.role === "thread"))[0];
  expect(thread.argv!.join(" ")).toContain('cli_auth_credentials_store="ephemeral"');
  expect(learn.output()).not.toContain("sk-synthetic");
  const page2 = await (await fetch(`${learn.origin}/api/setup`)).text();
  expect(page2).not.toContain("sk-synthetic");
});

for (const provider of ["claude", "codex"] as const) {
  test(`${provider}: a shell cat of a planted secret outside the worktree fails`, async ({ page, learn }) => {
    const repo = realpathSync(learn.repo);
    const secret = "sk-planted-e2e-secret-0123456789";
    writeFileSync(join(repo, ".env"), `OPENAI_API_KEY=${secret}\n`);
    mkdirSync(join(repo, "config"), { recursive: true });
    writeFileSync(join(repo, "config", ".env.local"), `TOKEN=${secret}\n`);
    await learn.configureFake({ reads: [join(repo, ".env"), join(repo, "config", ".env.local"), "wallet/core.py"] });
    await learn.open(page);
    await page.getByRole("radio", { name: provider === "claude" ? /Claude Code/ : /Codex/ }).check();
    await ask(page, "Read three files.");
    const answer = page.getByTestId("msg-assistant").last();
    await expect(answer).toContainText("Tutor shell and file tools (3)");
    await answer.locator("summary").click();
    await expect(answer.locator("li").filter({ hasText: ".env" }).first()).toContainText("failed");
    await expect(answer.locator("li").filter({ hasText: "wallet/core.py" })).toContainText("completed");
    const saved = readFileSync(join(learn.run, "my-work", "tutor-conversation.json"), "utf8");
    expect(saved).not.toContain(secret);
    if (provider === "claude") {
      const [c] = await learn.calls((x) => x.cli === "claude" && x.role === "tutor");
      for (const p of [repo, "/Users/clayton/dev/function-intelligence/**/.env*", `${process.env.HOME}/.codex`, `${process.env.HOME}/Library/Keychains`, `${process.env.HOME}/.docker/config.json`])
        expect(c.settings.sandbox.filesystem.denyRead).toContain(p);
    }
  });
}

test("codex fails closed: when the deny check fails, the shell is off and the doctor says why", async ({ page, startLearn }) => {
  const learn = await startLearn({ fakeConfig: { breakDeny: true } });
  await learn.open(page, "setup");
  await expect(page.getByTestId("check-codex-deny")).toContainText("needs-action");
  await expect(page.getByTestId("check-codex-deny")).toContainText("the Codex shell is off");
  await expect(page.getByTestId("provider-codex")).toContainText("Shell: off");
  await page.goto(`${learn.origin}/`);
  await page.getByRole("radio", { name: /Codex/ }).check();
  await ask(page, "Read a file.");
  await expect(page.getByTestId("msg-assistant").last()).toContainText("e2e codex reply");
  const thread = (await learn.calls((x) => x.cli === "codex" && x.role === "thread")).at(-1)!;
  expect(thread.argv).toContain("features.shell_tool=false");
  expect(thread.argv!.join(" ")).not.toContain("default_permissions");
  expect(thread.params.sandbox).toBe("read-only");
});
