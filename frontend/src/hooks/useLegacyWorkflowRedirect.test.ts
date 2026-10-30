import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useLegacyWorkflowRedirect } from "./useLegacyWorkflowRedirect";

const navigation = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
}));

describe("useLegacyWorkflowRedirect", () => {
  beforeEach(() => {
    navigation.replace.mockClear();
  });

  it("replaces a legacy route with its canonical workflow destination", async () => {
    renderHook(() => useLegacyWorkflowRedirect("/translation?start=upload"));

    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith("/translation?start=upload")
    );
  });
});
