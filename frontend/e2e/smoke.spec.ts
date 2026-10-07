import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function runScenario(page: Page, title: RegExp) {
  await page.goto("/customer");
  await page.getByRole("button", { name: title }).click();
  await expect(page.getByLabel(/প্রাপকের ওয়ালেট|Receiver wallet/)).not.toHaveValue("");
  await page.getByRole("button", { name: /^(পাঠান|Send)$/ }).click();
  return page.locator("[aria-live=polite]"); // the decision card
}

test("home page explains the product and links to the demo", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: /customer/i }).first()).toBeVisible();
});

test("customer: an everyday transfer to family is allowed and sent", async ({ page }) => {
  const card = await runScenario(page, /Send money to family/);
  await expect(card).toContainText("Allow");
  await expect(page.getByText(/টাকা পাঠানো হয়েছে|Money sent/)).toBeVisible();
});

test("customer: an account takeover is held and the customer can cancel it", async ({ page }) => {
  const card = await runScenario(page, /Account takeover at night/);
  await expect(card).toContainText("Hold");
  await page.getByRole("button", { name: /লেনদেন বাতিল করুন|Cancel this transfer/ }).click();
  await expect(page.getByText(/বাতিল হয়েছে|Cancelled/)).toBeVisible();
  // The "What the AI saw" tab shows the evidence behind the decision.
  await page.getByRole("tab", { name: /What the AI saw/ }).click();
  await expect(page.getByRole("tabpanel")).toContainText(/HOLD|Hold/);
});

test("analyst: the start-here case opens with its evidence", async ({ page }) => {
  await page.goto("/analyst");
  const open = page.getByRole("link", { name: /Open case #\d+/ });
  await expect(open).toBeVisible();
  await open.click();
  await expect(page.getByRole("heading", { name: /Case #\d+/ })).toBeVisible();
});

test("impact: loss prevented is shown as a range with analyst time saved", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByText("What it means for upay")).toBeVisible();
  await expect(page.getByText(/h\/day saved/)).toBeVisible();
});

test("admin: changes need the admin password, which the site never ships", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByLabel(/password/i).first()).toBeVisible();
  const tokens = await page.evaluate(() => window.localStorage.getItem("shurokkha.token.admin"));
  expect(tokens).toBeNull();
});

for (const path of ["/", "/customer", "/analyst", "/dashboard", "/admin"]) {
  test(`accessibility: ${path} has no WCAG 2.1 AA violations`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`)).toEqual([]);
  });
}
