import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OfflineModeProvider, useOfflineMode } from "./OfflineModeContext";

function OfflineModeConsumer() {
  const { status, isOfflineMode, fallbackData } = useOfflineMode();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="offline">{String(isOfflineMode)}</span>
      <span data-testid="fallback">{fallbackData ? "loaded" : "none"}</span>
    </div>
  );
}

describe("OfflineModeContext", () => {
  it("provides healthy defaults to consumers", () => {
    render(
      <OfflineModeProvider
        status="healthy"
        isOfflineMode={false}
        fallbackData={null}
        retry={() => {}}
      >
        <OfflineModeConsumer />
      </OfflineModeProvider>
    );

    expect(screen.getByTestId("status").textContent).toBe("healthy");
    expect(screen.getByTestId("offline").textContent).toBe("false");
    expect(screen.getByTestId("fallback").textContent).toBe("none");
  });

  it("provides offline fallback data to consumers", () => {
    const fallback = {
      fallbackMode: true,
      search: [{ id: "s1", text: "x", type: "world", chunk_id: "c1", entities: [], rank: 1 }],
    };

    render(
      <OfflineModeProvider
        status="offline"
        isOfflineMode={true}
        fallbackData={fallback}
        retry={() => {}}
      >
        <OfflineModeConsumer />
      </OfflineModeProvider>
    );

    expect(screen.getByTestId("status").textContent).toBe("offline");
    expect(screen.getByTestId("offline").textContent).toBe("true");
    expect(screen.getByTestId("fallback").textContent).toBe("loaded");
  });
});
