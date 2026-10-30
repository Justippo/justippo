import { expect, test } from "@playwright/test";
import { injectAuthSession } from "../fixtures/auth";
import { mockHealthyApi } from "../fixtures/health-mock";

test.describe("Secure document exchange", () => {
  test.beforeEach(async ({ page }) => {
    await mockHealthyApi(page);
    await injectAuthSession(page);
  });

  test("creates a room through the backend contract", async ({ page }) => {
    let requestBody: unknown;
    let consentHeader: string | undefined;
    await page.route("**/api/v1/exchange/rooms", async (route) => {
      requestBody = route.request().postDataJSON();
      consentHeader = route.request().headers()["x-gdpr-consent"];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ room_id: "!permit:evidence.eu" }),
      });
    });

    await page.goto("/exchange");
    await page.getByTestId("exchange-room-input").fill("Permit review");
    await page.getByTestId("exchange-participant-input").fill("@reviewer:evidence.eu");
    await page.getByTestId("exchange-create").click();

    await expect(page.getByTestId("exchange-room-name")).toHaveText("Permit review");
    await expect(page.getByTestId("exchange-room-id")).toContainText("!permit:evidence.eu");
    expect(requestBody).toEqual({ participants: ["@reviewer:evidence.eu"] });
    expect(consentHeader).toBe("demo");
  });

  test("validates participant IDs before sending", async ({ page }) => {
    await page.goto("/exchange");
    await page.getByTestId("exchange-room-input").fill("Permit review");
    await page.getByTestId("exchange-participant-input").fill("reviewer");
    await page.getByTestId("exchange-create").click();

    await expect(page.getByTestId("exchange-validation-error")).toContainText(
      "@name:organisation.eu"
    );
  });

  test("shows a recoverable error when room creation fails", async ({ page }) => {
    await page.route("**/api/v1/exchange/rooms", (route) =>
      route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({ detail: "upstream unavailable" }),
      })
    );

    await page.goto("/exchange");
    await page.getByTestId("exchange-room-input").fill("Permit review");
    await page.getByTestId("exchange-participant-input").fill("@reviewer:evidence.eu");
    await page.getByTestId("exchange-create").click();

    await expect(page.getByTestId("exchange-error")).toContainText("Unable to create");
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
