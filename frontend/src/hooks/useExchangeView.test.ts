import { renderHook, act, waitFor } from "@testing-library/react";
import type { FormEvent } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockCreateExchangeRoom = vi.fn();
const mockUseOfflineMode = vi.fn();

vi.mock("@/lib/api-generated", () => ({
  createExchangeRoom: (...args: unknown[]) => mockCreateExchangeRoom(...args),
}));

vi.mock("@/context/OfflineModeContext", () => ({
  useOfflineMode: () => mockUseOfflineMode(),
}));
import { useExchangeView } from "./useExchangeView";

describe("useExchangeView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOfflineMode.mockReturnValue({ isOfflineMode: false });
  });

  it("starts in empty state", () => {
    const { result } = renderHook(() => useExchangeView());
    expect(result.current.viewState).toBe("empty");
    expect(result.current.room).toBeNull();
  });

  it("returns forced success room data", () => {
    const { result } = renderHook(() => useExchangeView({ forcedState: "success" }));
    expect(result.current.viewState).toBe("success");
    expect(result.current.room?.name).toBe("Residence permit review");
  });

  it("creates a room through the live API", async () => {
    mockCreateExchangeRoom.mockResolvedValue({ room_id: "!permit:evidence.eu" });
    const { result } = renderHook(() => useExchangeView());

    act(() => {
      result.current.setRoomName("Permit review");
      result.current.setParticipantId("@reviewer:evidence.eu");
    });

    await act(async () => {
      result.current.onCreateRoom({
        preventDefault: () => undefined,
      } as FormEvent<HTMLFormElement>);
    });

    await waitFor(() => expect(result.current.viewState).toBe("success"));
    expect(mockCreateExchangeRoom).toHaveBeenCalledWith(["@reviewer:evidence.eu"]);
    expect(result.current.room?.id).toBe("!permit:evidence.eu");
    expect(result.current.room?.name).toBe("Permit review");
  });

  it("uses the sample room ID without calling the API when offline", async () => {
    mockUseOfflineMode.mockReturnValue({ isOfflineMode: true });
    const { result } = renderHook(() => useExchangeView());

    act(() => {
      result.current.setRoomName("Permit review");
      result.current.setParticipantId("@reviewer:evidence.eu");
    });
    await act(async () => {
      result.current.onCreateRoom({
        preventDefault: () => undefined,
      } as FormEvent<HTMLFormElement>);
    });

    expect(result.current.viewState).toBe("success");
    expect(mockCreateExchangeRoom).not.toHaveBeenCalled();
    expect(result.current.room?.id).toBe("room-eu-2024-0891");
  });

  it("keeps invalid participant input in the form with an actionable error", async () => {
    const { result } = renderHook(() => useExchangeView());
    act(() => {
      result.current.setRoomName("Permit review");
      result.current.setParticipantId("reviewer");
    });
    await act(async () => {
      result.current.onCreateRoom({
        preventDefault: () => undefined,
      } as FormEvent<HTMLFormElement>);
    });

    expect(result.current.viewState).toBe("empty");
    expect(result.current.error).toContain("@name:organisation.eu");
    expect(mockCreateExchangeRoom).not.toHaveBeenCalled();
  });

  it("surfaces API failures as a recoverable error state", async () => {
    mockCreateExchangeRoom.mockRejectedValue(new Error("feature disabled"));
    const { result } = renderHook(() => useExchangeView());
    act(() => {
      result.current.setRoomName("Permit review");
      result.current.setParticipantId("@reviewer:evidence.eu");
    });
    await act(async () => {
      result.current.onCreateRoom({
        preventDefault: () => undefined,
      } as FormEvent<HTMLFormElement>);
    });

    expect(result.current.viewState).toBe("error");
    expect(result.current.error).toContain("Unable to create");
    expect(result.current.errorAction).toBe("retry");
    expect(result.current.errorActionLabel).toBe("Try again");
  });

  it.each([
    ["matrix_authentication_required", "sign-in", "Sign in with Matrix", "session has expired"],
    ["matrix_exchange_disabled", "dashboard", "Go to dashboard", "not available right now"],
    ["matrix_room_creation_failed", "retry", "Try again", "could not create the room"],
    ["matrix_room_forbidden", "sign-in", "Sign in with Matrix", "not permitted"],
    ["matrix_invitation_forbidden", "retry", "Try again", "rejected the invitation"],
    ["matrix_participant_not_found", "retry", "Try again", "could not be found"],
    ["matrix_invitation_failed", "retry", "Try again", "could not invite"],
    ["matrix_rate_limited", "retry", "Try again", "limiting room requests"],
  ] as const)("maps %s to an actionable recovery state", async (code, action, label, message) => {
    mockCreateExchangeRoom.mockRejectedValue({ code });
    const { result } = renderHook(() => useExchangeView());
    act(() => {
      result.current.setRoomName("Permit review");
      result.current.setParticipantId("@reviewer:evidence.eu");
    });

    await act(async () => {
      result.current.onCreateRoom({
        preventDefault: () => undefined,
      } as FormEvent<HTMLFormElement>);
    });

    expect(result.current.viewState).toBe("error");
    expect(result.current.error).toContain(message);
    expect(result.current.errorAction).toBe(action);
    expect(result.current.errorActionLabel).toBe(label);
    expect(result.current.roomName).toBe("Permit review");
    expect(result.current.participantId).toBe("@reviewer:evidence.eu");
  });
});
