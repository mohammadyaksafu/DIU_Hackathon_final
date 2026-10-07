import { expect, test } from "@playwright/test";

test("mobile: the customer wallet fits the screen without sideways scrolling", async ({ page }) => {
  await page.goto("/customer");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
