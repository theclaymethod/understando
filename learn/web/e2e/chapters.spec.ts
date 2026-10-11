import { test, expect } from "./fixtures";

test("the app loads the pre-generated chapters and the tutor panel", async ({ page, learn }) => {
  await learn.open(page);
  const nav = page.getByRole("navigation", { name: "Chapters and exercises" });
  // The guided review: one chapter of the app for each chapter of the explainer.
  for (const title of ["Start", "How it works", "What changed", "The checks", "Check yourself", "The review"])
    await expect(nav.getByRole("link", { name: title, exact: true })).toBeVisible();
  await expect(page.locator("[data-chapter='ch-0'] .ve-section")).toBeVisible();
  await nav.getByRole("link", { name: "The review", exact: true }).click();
  await expect(page.locator("[data-chapter='ch-7']")).toContainText("C01");
  await expect(page.locator("[data-chapter='ch-7']")).toContainText("OverdraftError");
  // The exercises sit in the chapter that keeps the old "exercises" id as an alias.
  await nav.getByRole("link", { name: "Check yourself", exact: true }).click();
  await expect(page.getByTestId("exercise-hub")).toBeVisible();
  await expect(page.getByTestId("tutor-panel")).toContainText("guess tier");
});
