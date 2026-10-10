import http from "node:http";
import { test, expect } from "./fixtures";

test("a graded action with an unknown id or a made-up argv is refused", async ({ page, learn }) => {
  // The direct route takes only a kind and an id from the trust map.
  const unknown = await learn.post("/api/run", { kind: "run-control", id: "K99" });
  expect(unknown.status).toBe(403);
  expect(unknown.json.error).toContain("No control K99");
  const argv = await learn.post("/api/run", { kind: "run-verifier", id: "V01", argv: ["sh", "-c", "touch /tmp/pwned"] });
  expect(argv.status).toBe(400);
  expect(argv.json.error).toContain('"argv" is not permitted');
  const kind = await learn.post("/api/run", { kind: "shell", id: "V01" });
  expect(kind.status).toBe(403);
  const recorded = await learn.post("/api/run", { kind: "run-verifier", id: "V05" });
  expect(recorded.json.error).toContain("no command");
  const noOrigin = await fetch(`${learn.origin}/api/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"kind":"run-control","id":"K01"}' });
  expect(noOrigin.status).toBe(403);
  const badHost = await new Promise<number>((resolve) => {
    const u = new URL(learn.origin);
    http.get({ host: u.hostname, port: u.port, path: "/api/session", headers: { Host: "evil.example" } }, (r) => { r.resume(); resolve(r.statusCode ?? 0); });
  });
  expect(badHost).toBe(403);

  // The tutor proposes in tags. The server refuses each tag outside the allowlist.
  await learn.configureFake({ tutorReply: [
    "Run these:",
    '<understando-action kind="run-control" id="K99"/>',
    '<understando-action kind="run-verifier" id="V01" argv="rm -rf /"/>',
    '<understando-action kind="run-control" id="K01"/>',
  ].join("\n") });
  await learn.open(page);
  await page.getByLabel("Message to the tutor").fill("Which control should I run?");
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.getByTestId("msg-assistant").last();
  await expect(answer.getByTestId("refused")).toHaveCount(2);
  await expect(answer.getByTestId("refused").first()).toContainText("No control K99");
  await expect(answer.getByTestId("refused").nth(1)).toContainText("argv");
  await expect(answer).not.toContainText("understando-action");
  const proposal = answer.getByTestId("proposal");
  await expect(proposal).toHaveCount(1);
  await expect(proposal).toHaveAttribute("data-target", "K01");
  // Nothing ran before the learner confirmed.
  let progress = await (await fetch(`${learn.origin}/api/progress`)).json();
  expect(progress.runs).toHaveLength(0);
  await proposal.getByRole("button", { name: "Confirm and run" }).click();
  await expect(proposal.getByTestId("run-result")).toHaveAttribute("data-status", "red", { timeout: 30_000 });
  progress = await (await fetch(`${learn.origin}/api/progress`)).json();
  expect(progress.runs.map((r: any) => r.id)).toEqual(["K01"]);
  // A proposal runs once.
  const again = await learn.post("/api/actions/confirm", { proposalId: "not-a-proposal" });
  expect(again.status).toBe(404);
});
