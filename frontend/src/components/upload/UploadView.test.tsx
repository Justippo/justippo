import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { UploadView } from "./UploadView";
import { UPLOAD_HISTORY } from "@/data/mockData";
import { renderWithI18n as render } from "@/test-utils";

const dragState = vi.hoisted(() => ({ file: null as File | null }));

vi.mock("@/hooks/useUpload", () => ({
  useUpload: () => ({
    status: "empty",
    result: null,
    error: null,
    upload: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("@/hooks/useDragAndDrop", () => ({
  useDragAndDrop: () => ({
    isDragging: false,
    file: dragState.file,
    onDragEnter: vi.fn(),
    onDragLeave: vi.fn(),
    onDragOver: vi.fn(),
    onDrop: vi.fn(),
    onFileSelect: vi.fn(),
    clearFile: vi.fn(),
  }),
}));

vi.mock("@/hooks/useUploadHistory", () => ({
  useUploadHistory: () => ({
    history: UPLOAD_HISTORY,
    recordUpload: vi.fn(),
  }),
}));

describe("UploadView", () => {
  beforeEach(() => {
    dragState.file = null;
  });

  it("renders dropzone in empty state", () => {
    render(<UploadView />);
    expect(screen.getByText("Drag and drop your document here")).toBeDefined();
  });

  it("shows GDPR consent checkbox", () => {
    render(<UploadView />);
    expect(screen.getByTestId("upload-gdpr-consent")).toBeDefined();
    expect(
      screen.getByText(
        "I consent to processing this document for OCR and translation. Data is handled ephemerally under GDPR Article 6(1)(a)."
      )
    ).toBeDefined();
  });

  it("shows upload history", () => {
    render(<UploadView />);
    expect(screen.getByText("Recent uploads")).toBeDefined();
    expect(screen.getAllByTestId("upload-history-item").length).toBe(UPLOAD_HISTORY.length);
  });

  it("uses the unified translation entry without upload history", () => {
    render(<UploadView context="translation" />);
    expect(screen.getByRole("heading", { name: "Translate document" })).toBeDefined();
    expect(screen.queryByText("Recent uploads")).toBeNull();
    expect(screen.queryByTestId("upload-lang-select")).toBeNull();
  });

  it("selects the translation target before document analysis", () => {
    dragState.file = new File(["%PDF"], "form.pdf", { type: "application/pdf" });

    render(<UploadView context="translation" />);

    expect(screen.getByTestId("translation-lang-select")).toHaveValue("en");
    expect(screen.getByRole("button", { name: "Upload for analysis" })).toBeDefined();
  });

  it("renders success state with confidence badges", () => {
    render(<UploadView forcedState="success" />);
    expect(screen.getByTestId("upload-avg-confidence")).toBeDefined();
    expect(screen.getByText(/Preview limited to first 120 characters/)).toBeDefined();
    expect(screen.getAllByText("96%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("58%").length).toBeGreaterThan(0);
  });

  it("uses the server-resolved target language after analysis", async () => {
    const onContinue = vi.fn();
    render(<UploadView context="translation" forcedState="success" onContinue={onContinue} />);

    await waitFor(() =>
      expect(screen.getByTestId("translation-target-confirmation")).toHaveTextContent(
        "Translation target: English"
      )
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to translation" }));

    expect(onContinue).toHaveBeenCalledWith("en", null);
  });

  it("renders loading state with skeleton", () => {
    render(<UploadView forcedState="loading" />);
    expect(screen.getByLabelText("Uploading document")).toBeDefined();
  });

  it("renders error state without demo copy", () => {
    render(<UploadView forcedState="error" />);
    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.queryByText(/demo/i)).toBeNull();
  });
});
