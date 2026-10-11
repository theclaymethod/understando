import { test, expect } from "./fixtures";

test("the app loads the pre-generated chapters and the tutor panel", async ({ page, learn }) => {
  await learn.open(page);
  const nav = page.getByRole("navigation", { name: "Chapters and exercises" });
  for (const title of ["The story", "The loop", "What changed", "The promises", "Can checks catch a bug?", "Exercises"])
    await expect(nav.getByRole("link", { name: title, exact: true })).toBeVisible();
  await expect(page.locator("[data-chapter='story'] .ve-section")).toBeVisible();
  await nav.getByRole("link", { name: "The promises", exact: true }).click();
  await expect(page.locator("[data-chapter='promises']")).toContainText("C01");
  await expect(page.locator("[data-chapter='promises']")).toContainText("OverdraftError");
  await nav.getByRole("link", { name: "Exercises", exact: true }).click();
  await expect(page.getByTestId("exercise-hub")).toBeVisible();
  await expect(page.getByTestId("tutor-panel")).toContainText("guess tier");
});
