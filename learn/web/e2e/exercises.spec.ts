import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "./fixtures";

test("find the line, trace it and close a gap are graded by code", async ({ page, learn }) => {
  await learn.open(page, "exercises/find-line");
  const line = page.getByTestId("exercise-line-C01");
  await line.getByRole("button", { name: "Line 2", exact: true }).click();
  await expect(line.getByTestId("grade")).toContainText("not the line");
  await line.getByRole("button", { name: "Line 13", exact: true }).click();
  await expect(line.getByTestId("grade")).toContainText("Correct");

  await page.goto(`${learn.origin}/#exercises/trace`);
  const trace = page.getByTestId("exercise-X01");
  await trace.getByRole("button", { name: "It returns -1." }).click();
  await expect(trace.getByTestId("grade")).toContainText("not the next step");
  await trace.getByRole("button", { name: "It raises OverdraftError." }).click();
  await expect(trace.getByTestId("grade")).toContainText("Correct");

  await page.goto(`${learn.origin}/#exercises/close-gap`);
  const gap = page.getByTestId("exercise-X02");
  // The starter test passes at the head but checks nothing, so it cannot go red on the bug.
  await gap.getByRole("button", { name: "Save and run" }).click();
  await expect(gap.getByTestId("grade")).toContainText("Not yet", { timeout: 30_000 });
  const editor = gap.getByLabel("Test file tests/test_fees.py");
  await editor.fill("import unittest\n\nfrom wallet.fees import fee\n\n\nclass FeeTest(unittest.TestCase):\n    def test_fee(self) -> None:\n        self.assertEqual(fee(250), 3)\n");
  await gap.getByRole("button", { name: "Save and run" }).click();
  await expect(gap.getByTestId("grade")).toContainText("The gap has a check now", { timeout: 30_000 });
  const progress = JSON.parse(readFileSync(join(learn.run, "my-work", "progress.json"), "utf8"));
  expect(progress.exercises.X02.passed).toBe(true);
  expect(progress.exercises["line-C01"].passed).toBe(true);
  // The learner can write only the exercise's test path.
  const extra = await learn.post("/api/exercises/close-gap/test", { exercise: "X02", content: "x", path: "wallet/core.py" });
  expect(extra.status).toBe(400);
});

test("explain it back: the model grade is labelled as a guess, and the verdict does not change", async ({ page, learn }) => {
  const before = readFileSync(join(learn.run, "trust-map.json"), "utf8");
  await learn.open(page, "exercises/explain-back");
  const card = page.getByTestId("exercise-explain-C01");
  await card.getByLabel("Your explanation").fill("withdraw raises OverdraftError when the amount is more than the balance.");
  await card.getByRole("button", { name: "Grade my explanation" }).click();
  await expect(card.getByTestId("explain-grade")).toContainText("Model-generated grade");
  await expect(card.getByTestId("explain-grade")).toContainText("Score 2 of 3");
  expect(readFileSync(join(learn.run, "trust-map.json"), "utf8")).toBe(before);
  const [call] = await learn.calls((c) => c.cli === "claude" && c.role === "grader");
  expect(call.argv![call.argv!.indexOf("--tools") + 1]).toBe("");
  expect(call.cwd).not.toBe(learn.worktree);
});

test("the setup doctor reports both providers and the sandbox", async ({ page, learn }) => {
  await learn.open(page, "setup");
  await expect(page.getByTestId("provider-claude")).toContainText("ready");
  await expect(page.getByTestId("provider-codex")).toContainText("gpt-e2e");
  await expect(page.getByTestId("check-codex-isolation")).toContainText("ready");
  await expect(page.getByTestId("check-sandbox")).toBeVisible();
});
