import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

// vi.hoisted ensures mock functions exist before vi.mock factory runs
const mocks = vi.hoisted(() => ({
  mockCapture: vi.fn(),
  mockOptIn: vi.fn(),
  mockOptOut: vi.fn(),
  mockStartSessionRecording: vi.fn(),
  mockStopSessionRecording: vi.fn(),
  mockIsFeatureEnabled: vi.fn(),
  mockSetConfig: vi.fn(),
}));

vi.mock("posthog-js", () => ({
  __esModule: true,
  default: {
    init: vi.fn((_key: string, config: { loaded?: (ph: unknown) => void }) => {
      const mockPh = {
        capture: mocks.mockCapture,
        opt_in_capturing: mocks.mockOptIn,
        opt_out_capturing: mocks.mockOptOut,
        startSessionRecording: mocks.mockStartSessionRecording,
        stopSessionRecording: mocks.mockStopSessionRecording,
        set_config: mocks.mockSetConfig,
        isFeatureEnabled: mocks.mockIsFeatureEnabled,
      };
      config?.loaded?.(mockPh);
      return mockPh;
    }),
    isFeatureEnabled: mocks.mockIsFeatureEnabled,
  },
}));

// Import AFTER mock is registered
import { useAnalytics } from "./useAnalytics";
import { GDPRConsentProvider } from "@/context/GDPRConsentContext";
import { _resetPostHogForTests } from "@/lib/posthog";

function wrapper({ children }: { children: React.ReactNode }) {
  return <GDPRConsentProvider>{children}</GDPRConsentProvider>;
}

describe("useAnalytics", () => {
  beforeEach(async () => {
    process.env.NEXT_PUBLIC_POSTHOG_KEY = "phc_test_token";
    localStorage.clear();
    mocks.mockCapture.mockClear();
    mocks.mockOptIn.mockClear();
    mocks.mockOptOut.mockClear();
    mocks.mockStartSessionRecording.mockClear();
    mocks.mockStopSessionRecording.mockClear();
    mocks.mockIsFeatureEnabled.mockClear();
    mocks.mockSetConfig.mockClear();
    // Reset the posthog singleton so init runs fresh each test
    _resetPostHogForTests();
  });

  it("returns no-ops when consent is not active", async () => {
    const { result } = renderHook(() => useAnalytics(), { wrapper });

    // Wait for GDPRConsentProvider to finish its init effect
    await waitFor(() => {
      expect(result.current.isEnabled).toBe(false);
    });

    act(() => {
      result.current.trackUpload({
        page_count: 1,
        content_type: "application/pdf",
        target_language: "de",
        document_type: "legal_document",
        has_explanation: false,
      });
    });

    expect(mocks.mockCapture).not.toHaveBeenCalled();
  });

  it("calls posthog.capture() with correct properties when consent is active", async () => {
    localStorage.setItem("evidence-eu-gdpr-consent", "granted");
    const { result } = renderHook(() => useAnalytics(), { wrapper });

    await waitFor(() => {
      expect(result.current.isEnabled).toBe(true);
    });

    act(() => {
      result.current.trackUpload({
        page_count: 1,
        content_type: "application/pdf",
        target_language: "de",
        document_type: "legal_document",
        has_explanation: true,
      });
    });

    expect(mocks.mockCapture).toHaveBeenCalledWith("document_uploaded", {
      page_count: 1,
      content_type: "application/pdf",
      target_language: "de",
      document_type: "legal_document",
      has_explanation: true,
    });
  });

  it("no sensitive fields in any event property payload", async () => {
    localStorage.setItem("evidence-eu-gdpr-consent", "granted");
    const { result } = renderHook(() => useAnalytics(), { wrapper });

    await waitFor(() => {
      expect(result.current.isEnabled).toBe(true);
    });

    act(() => {
      result.current.trackSearch({
        language: "en",
        result_count: 5,
        query_length: 20,
        has_answer: true,
      });
    });

    const call = mocks.mockCapture.mock.calls[0];
    expect(call).toBeDefined();
    const properties = call[1] as Record<string, unknown>;
    // No document content, filenames, or extracted text
    expect(properties).not.toHaveProperty("document_content");
    expect(properties).not.toHaveProperty("filename");
    expect(properties).not.toHaveProperty("extracted_text");
    expect(properties).not.toHaveProperty("text");
  });

  it("getFlag() returns false when PostHog is uninitialized", async () => {
    const { result } = renderHook(() => useAnalytics(), { wrapper });

    await waitFor(() => {
      expect(result.current.isEnabled).toBe(false);
    });

    mocks.mockIsFeatureEnabled.mockReturnValue(false);
    const flag = result.current.getFlag("chat_enabled");
    expect(typeof flag).toBe("boolean");
  });
});
