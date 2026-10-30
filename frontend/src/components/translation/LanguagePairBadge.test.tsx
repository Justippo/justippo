import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { LanguagePairBadge } from "./LanguagePairBadge";
import { renderWithI18n as render } from "@/test-utils";

describe("LanguagePairBadge", () => {
  it("renders source and target language codes", () => {
    render(<LanguagePairBadge sourceLang="de" targetLang="en" />);
    expect(screen.getByTestId("language-pair-source").textContent).toBe("DE");
    expect(screen.getByTestId("language-pair-target").textContent).toBe("EN");
  });
});
