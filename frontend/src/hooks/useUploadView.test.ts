import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useUploadView } from "./useUploadView";

vi.mock("./useUpload", () => ({
  useUpload: () => ({
    status: "empty",
    result: null,
    error: null,
    upload: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("./useDragAndDrop", () => ({
  useDragAndDrop: () => ({
    isDragging: false,
    file: new File(["content"], "contract.pdf", { type: "application/pdf" }),
    onDragEnter: vi.fn(),
    onDragLeave: vi.fn(),
    onDragOver: vi.fn(),
    onDrop: vi.fn(),
    onFileSelect: vi.fn(),
    clearFile: vi.fn(),
  }),
}));

vi.mock("./useUploadHistory", () => ({
  useUploadHistory: () => ({
    history: [],
    recordUpload: vi.fn(),
  }),
}));

describe("useUploadView", () => {
  it("requires GDPR consent before upload", () => {
    const { result } = renderHook(() => useUploadView());

    act(() => {
      result.current.onSubmit({
        preventDefault: () => {},
      } as unknown as React.FormEvent<HTMLFormElement>);
    });

    expect(result.current.consentError).toContain("GDPR consent is required");
  });
});
