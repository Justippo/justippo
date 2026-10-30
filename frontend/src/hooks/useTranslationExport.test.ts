import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildTranslationExportText, useTranslationExport } from "./useTranslationExport";

const partialResult = {
  job_id: "job-export",
  status: "partial",
  translated_pages: [
    {
      page: 1,
      text: "Translated section",
      sections: [
        {
          index: 0,
          source_text: "Source section",
          translated_text: "Translated section",
          status: "translated" as const,
          attempts: 1,
        },
        {
          index: 1,
          source_text: "Source section two",
          translated_text: "",
          status: "failed" as const,
          attempts: 2,
          error_code: "TRANSLATION_SECTION_FAILED" as const,
        },
      ],
    },
  ],
};

describe("useTranslationExport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds transparent text for successful and failed sections", () => {
    const text = buildTranslationExportText(partialResult, "form.pdf", "en");

    expect(text).toContain("Translated section");
    expect(text).toContain("Section 2 could not be translated after 2 attempts");
    expect(text).toContain("Target language: EN");
  });

  it("downloads a local text artifact without a backend request", () => {
    const createObjectUrl = vi.fn(() => "blob:translation");
    const revokeObjectUrl = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrl,
    });
    const { result } = renderHook(() =>
      useTranslationExport(partialResult, "fillable-form.pdf", "en")
    );

    result.current.downloadTranslatedText();

    expect(result.current.canDownload).toBe(true);
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:translation");
  });
});
