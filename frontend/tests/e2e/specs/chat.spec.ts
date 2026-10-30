import { expect, test } from "@playwright/test";
import { injectAuthSession } from "../fixtures/auth";

const SOURCE_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038";

test.beforeEach(async ({ page }) => {
  await injectAuthSession(page);
});

test("authenticated user can hold a grounded, model-disclosed RAG conversation", async ({
  page,
}) => {
  const requests: Array<{ message: string; history: Array<{ role: string; content: string }> }> =
    [];
  await page.route("**/api/v1/chat/**", async (route) => {
    const request = route.request().postDataJSON() as (typeof requests)[number];
    requests.push(request);
    const answer = request.message.includes("documents")
      ? "Next steps:\n1. Confirm your residence category.\n2. Prepare identity documents."
      : "EU citizens have residence rights under Directive 2004/38/EC.";
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-cache" },
      body: [
        "event: result",
        `data: ${JSON.stringify({
          id: "result-1",
          text: "Directive 2004/38/EC protects residence rights for EU citizens.",
          type: "world",
          chunk_id: "chunk-1",
          entities: ["EU citizens"],
          document_id: "eurlex-32004L0038",
          source_url: SOURCE_URL,
          source_title: "Directive 2004/38/EC",
          source_language: "en",
          rank: 1,
        })}`,
        "",
        "event: answer_model",
        `data: ${JSON.stringify({
          provider: "public-ai",
          provider_display: "Public AI",
          model: "swiss-ai/apertus-8b-instruct",
          display_name: "Apertus 8B",
        })}`,
        "",
        "event: answer_chunk",
        `data: ${JSON.stringify({
          text: answer,
        })}`,
        "",
        "event: done",
        "data: [DONE]",
        "",
      ].join("\n"),
    });
  });

  // injectAuthSession in beforeEach already mocks authenticated session.
  // Navigate directly to /chat — no need to go through the login flow.
  await page.goto("/chat");

  await expect(page.getByTestId("chat-corpus-badge")).toHaveText("Public corpus — EUR-Lex");
  const questionInput = page.getByLabel("What would you like to know about EU law?");
  const sendButton = page.getByRole("button", { name: "Send" });
  await expect(sendButton).toBeDisabled();

  await questionInput.fill("What are the EU residence rights?");
  await expect(sendButton).toBeEnabled();
  await sendButton.click();

  await expect(page.getByText("What are the EU residence rights?")).toBeVisible();
  await expect(
    page.getByText("EU citizens have residence rights under Directive 2004/38/EC.")
  ).toBeVisible();
  await expect(page.getByText(/Answered by Apertus 8B via Public AI/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Directive 2004/38/EC" })).toHaveAttribute(
    "href",
    SOURCE_URL
  );

  await questionInput.fill("What documents do I need?");
  await sendButton.click();
  await expect(page.getByText(/Prepare identity documents/)).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[1].history).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        role: "user",
        content: "What are the EU residence rights?",
      }),
      expect.objectContaining({
        role: "assistant",
        content: "EU citizens have residence rights under Directive 2004/38/EC.",
      }),
    ])
  );
});
