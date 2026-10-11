import { test, expect } from "./fixtures";

test("predict, then run: the good verifier goes red on its control", async ({ page, learn }) => {
  await learn.open(page, "exercises/predict");
  const card = page.getByTestId("exercise-predict-K01");
  await card.getByLabel(/goes red/).check();
  await card.getByRole("button", { name: "Run control K01" }).click();
  await expect(card.getByTestId("run-result")).toHaveAttribute("data-status", "red", { timeout: 30_000 });
  await expect(card.getByTestId("grade")).toHaveText("Correct: the check went red.");
  await expect(card.getByTestId("cannot-fail")).toHaveCount(0);
  const progress = await (await fetch(`${learn.origin}/api/progress`)).json();
  expect(progress.exercises["predict-K01"].passed).toBe(true);
});

test("predict, then run: the cannot-fail verifier stays green, and the UI flags it", async ({ page, learn }) => {
  await learn.open(page, "exercises/predict");
  const card = page.getByTestId("exercise-predict-K02");
  await card.getByLabel(/goes red/).check();
  await card.getByRole("button", { name: "Run control K02" }).click();
  await expect(card.getByTestId("run-result")).toHaveAttribute("data-status", "green", { timeout: 30_000 });
  await expect(card.getByTestId("cannot-fail")).toContainText("This check cannot fail");
  await expect(card.getByTestId("grade")).toHaveText("Not this time: the check went green.");
});
