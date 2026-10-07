import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Phase 2 features. Runs with no LLM configured: the AI features must fall back to their
// deterministic templates (no tokens are spent by these tests).

async function scenario(page: Page, title: RegExp, customer = 0) {
  await page.goto("/customer");
  if (customer) await page.locator("#cust").selectOption({ index: customer });
  await page.getByRole("button", { name: title }).click();
  await expect(page.getByLabel(/প্রাপকের ওয়ালেট|Receiver wallet/)).not.toHaveValue("");
  await page.getByRole("button", { name: /^(পাঠান|Send)$/ }).click();
  return page.locator("[aria-live=polite]");
}

test("agent cash-out scenario is flagged with agent reasons", async ({ page }) => {
  const card = await scenario(page, /Mule cash-out at an agent/);
  await expect(card).toContainText(/Warn|Hold/);
  await expect(card).toContainText(/এজেন্ট|ক্যাশ আউট/);
});

test("WARN has a cooling-off timer before 'send anyway' and a voice option", async ({ page }) => {
  // Repeating the mule pattern on the same wallet makes it bigger, so a later run may escalate to HOLD,
  // where there is no "send anyway" at all. Either way the customer cannot push the money through at once.
  const card = await scenario(page, /Mule cash-out at an agent/, 12);
  await expect(card).toContainText(/Warn|Hold/);
  if ((await card.textContent())?.includes("Warn")) {
    await expect(card.getByRole("button", { name: /একটু ভাবুন/ })).toBeDisabled();
  } else {
    await expect(card.getByRole("button", { name: /তবুও পাঠান/ })).toHaveCount(0);
  }
  await expect(card.getByRole("button", { name: /সতর্কবার্তাটি শুনুন/ })).toBeVisible();
});

test("on-call scenario sets the call flag and is interrupted", async ({ page }) => {
  const card = await scenario(page, /Coached on a phone call/);
  await expect(page.getByRole("checkbox", { name: /ফোনে কথা বলছি/ })).toBeChecked();
  await expect(card).toContainText(/Warn|Hold/);
  await expect(card).toContainText(/ফোনে কথা বলছেন/);
});

test("customer can appeal a HOLD and the analyst queue can filter appeals", async ({ page }) => {
  const card = await scenario(page, /Account takeover at night/);
  await expect(card).toContainText("Hold");
  await card.getByRole("button", { name: /আপিল করুন/ }).click();
  await expect(card).toContainText(/আপিল জমা হয়েছে/);
  await page.goto("/analyst");
  await page.getByRole("checkbox", { name: /Customer appeals only/ }).check();
  await expect(page.getByText(/appeal · reply by/).first()).toBeVisible();
});

test("case summary falls back to the rule-based template without an LLM", async ({ page }) => {
  await page.goto("/analyst");
  await page.getByRole("link", { name: /Open case #\d+/ }).click();
  await page.getByRole("button", { name: /Generate case summary/ }).click();
  await expect(page.getByText(/Rule-based summary \(AI unavailable\)|AI-generated/)).toBeVisible({ timeout: 30_000 });
});

test("SOP copilot answers from retrieved procedures without an LLM", async ({ page }) => {
  await page.goto("/copilot");
  await page.getByLabel("Question").fill("What should I do after a SIM swap?");
  await page.getByLabel("Question").press("Enter");
  await expect(page.getByText(/Retrieved passage \(AI unavailable\)|AI ·/)).toBeVisible({ timeout: 30_000 });
});

test("user study: consent, six transfers, trust rating, results table", async ({ page }) => {
  await page.goto("/study");
  await page.getByRole("checkbox", { name: /স্বেচ্ছায় অংশ নিতে রাজি/ }).check();
  await page.getByRole("button", { name: /Start/ }).click();
  for (let i = 0; i < 6; i++) {
    await expect(page.getByText(`Transfer ${i + 1} of 6`)).toBeVisible();
    await page.getByRole("button", { name: "পাঠাব না" }).click();
  }
  await page.getByRole("radio", { name: "4" }).click();
  await page.getByRole("radio", { name: "না" }).click();
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText(/উত্তর জমা হয়েছে/)).toBeVisible();
  await expect(page.getByText(/participants ·/)).toBeVisible();
});

test("impact page shows ROI, measured vs simulated and drift", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByText("Return on investment (simulated)")).toBeVisible();
  await expect(page.getByText("Measured vs simulated")).toBeVisible();
  await expect(page.getByText(/Model drift \(PSI/)).toBeVisible();
});

test("accessibility: /study has no WCAG 2.1 AA violations", async ({ page }) => {
  await page.goto("/study");
  await page.waitForLoadState("networkidle");
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`)).toEqual([]);
});

test("AI chat answers from the fallback without an LLM", async ({ page }) => {
  await page.goto("/chat");
  const box = page.getByPlaceholder("Ask a question…");
  await box.fill("How do I spot a prize scam?");
  await box.press("Enter");
  await expect(page.getByText(/AI unavailable/).first()).toBeVisible({ timeout: 30_000 });
});
