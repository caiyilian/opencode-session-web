import { expect, test } from "@playwright/test";

test("browses, searches, opens a session, and keeps composer reachable", async ({
  page,
}, testInfo) => {
  const isMobile = testInfo.project.name === "mobile";

  await page.goto("/");
  await expect(page).toHaveTitle("OpenCode Session Web");

  const search = page.getByPlaceholder("Search sessions");
  const rows = page.locator(".session-row");
  await expect(search).toBeVisible();
  await expect(rows).toHaveCount(3);

  await expect(page.locator(".compare-panel .panel-status")).toContainText(
    "Choose two sessions and compare",
  );
  await expect(page.locator(".compare-panel .panel-status")).toHaveAttribute("role", "status");

  await search.fill("__missing_session__");
  await expect(page.locator(".session-list .status-block")).toHaveText("No sessions");
  await expect(page.locator(".session-list .status-block")).toHaveAttribute("role", "status");
  await expect(rows).toHaveCount(0);

  await search.fill("Alpha");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Alpha release planning");

  await rows.first().click();
  if (isMobile) {
    await expect(page.locator(".sidebar-shell")).toBeHidden();
  } else {
    await expect(page.locator(".sidebar-shell")).toBeVisible();
  }

  await expect(page.getByRole("heading", { name: "Messages" })).toBeVisible();
  await expect(page.locator(".timeline-panel")).toBeInViewport();
  await expect(page.locator(".composer-panel")).toBeInViewport();
  await expect(page.locator(".tool-card")).toContainText("bash");
  await expect(page.locator(".tool-card")).toContainText("Run alpha checks");

  const composer = page.getByPlaceholder("Continue this session");
  await expect(composer).toBeVisible();
  await composer.fill("Draft from Playwright");
  await expect(composer).toHaveValue("Draft from Playwright");

  await expect(page.locator("body")).not.toContainText("Internal Server Error");
  const isOverflowing = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(isOverflowing).toBe(false);
});
