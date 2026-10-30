import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { OfflineBanner } from "./OfflineBanner";
import { OFFLINE_BANNER_MESSAGE } from "@/data/mockData";

describe("OfflineBanner", () => {
  it("renders neutral sample data message", () => {
    render(<OfflineBanner />);
    expect(screen.getByTestId("offline-banner").textContent).toBe(OFFLINE_BANNER_MESSAGE);
    expect(screen.queryByText(/demo mode/i)).toBeNull();
    expect(screen.queryByText(/backend offline/i)).toBeNull();
  });
});
