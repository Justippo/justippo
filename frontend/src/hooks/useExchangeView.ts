"use client";

import { useCallback, useMemo, useState, type FormEvent } from "react";
import { useOfflineMode } from "@/context/OfflineModeContext";
import {
  EXCHANGE_ERROR_COPY,
  EXCHANGE_PARTICIPANT_PLACEHOLDER,
  EXCHANGE_ROOM_NAME_PLACEHOLDER,
  EXCHANGE_SAMPLE_ROOM,
  type ExchangeParticipant,
} from "@/data/mockData";
import { createExchangeRoom, type ExchangeApiError } from "@/lib/api-generated";
import { API_BASE } from "@/lib/config";

export type ExchangeViewState = "loading" | "success" | "error" | "empty";
export type ExchangeErrorAction = "retry" | "sign-in" | "dashboard";

interface ExchangeRoom {
  readonly id: string;
  readonly name: string;
  readonly status: "active";
  readonly createdAt: string;
  readonly documentName: string | null;
  readonly encryptionLabel: string;
  readonly participants: readonly ExchangeParticipant[];
}

interface UseExchangeViewOptions {
  readonly forcedState?: ExchangeViewState;
}

interface UseExchangeViewResult {
  readonly viewState: ExchangeViewState;
  readonly room: ExchangeRoom | null;
  readonly roomName: string;
  readonly roomNamePlaceholder: string;
  readonly participantId: string;
  readonly participantPlaceholder: string;
  readonly error: string | null;
  readonly errorAction: ExchangeErrorAction | null;
  readonly errorActionLabel: string | null;
  readonly canCreateRoom: boolean;
  readonly setRoomName: (value: string) => void;
  readonly setParticipantId: (value: string) => void;
  readonly onCreateRoom: (event: FormEvent<HTMLFormElement>) => void;
  readonly onLeaveRoom: () => void;
  readonly onErrorAction: () => void;
}

const MATRIX_USER_ID_PATTERN = /^@[a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
const AUTH_RETURN_PATH_KEY = "evidenceeu_auth_return_path";

function buildRoom(name: string, participantId: string, roomId: string): ExchangeRoom {
  return {
    id: roomId,
    name,
    status: "active",
    createdAt: new Date().toISOString(),
    documentName: null,
    encryptionLabel: "End-to-end encrypted · GDPR-native",
    participants: [{ id: participantId, name: participantId, role: "Invited" }],
  };
}

export function useExchangeView({
  forcedState,
}: Readonly<UseExchangeViewOptions> = {}): UseExchangeViewResult {
  const [viewState, setViewState] = useState<ExchangeViewState>("empty");
  const [room, setRoom] = useState<ExchangeRoom | null>(null);
  const [roomName, setRoomName] = useState("");
  const [participantId, setParticipantId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorAction, setErrorAction] = useState<ExchangeErrorAction | null>(null);
  const { isOfflineMode } = useOfflineMode();

  const onCreateRoom = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (forcedState) {
        return;
      }

      const trimmed = roomName.trim();
      if (!trimmed) {
        setError(EXCHANGE_ERROR_COPY.roomNameRequired);
        return;
      }

      const trimmedParticipant = participantId.trim();
      if (!trimmedParticipant) {
        setError(EXCHANGE_ERROR_COPY.participantRequired);
        return;
      }
      if (!MATRIX_USER_ID_PATTERN.test(trimmedParticipant)) {
        setError(EXCHANGE_ERROR_COPY.participantInvalid);
        return;
      }

      setError(null);
      setErrorAction(null);
      setViewState("loading");
      const savedRoomName = trimmed;
      const savedParticipant = trimmedParticipant;
      try {
        const created = isOfflineMode
          ? { room_id: EXCHANGE_SAMPLE_ROOM.id }
          : await createExchangeRoom([savedParticipant]);
        setRoom(buildRoom(savedRoomName, savedParticipant, created.room_id));
        setViewState("success");
      } catch (caught) {
        const exchangeError = caught as Partial<ExchangeApiError>;
        if (exchangeError.code === "matrix_rate_limited") {
          const retryMs = exchangeError.retryAfterMs;
          if (typeof retryMs === "number" && Number.isFinite(retryMs) && retryMs > 5_000) {
            const totalSeconds = Math.ceil(retryMs / 1000);
            const display =
              totalSeconds >= 60 ? `~${Math.ceil(totalSeconds / 60)}m` : `~${totalSeconds}s`;
            setError(`Matrix rate limit active. Try again in ${display}.`);
          } else {
            setError(EXCHANGE_ERROR_COPY.rateLimited);
          }
          setErrorAction("retry");
          setViewState("error");
        } else if (exchangeError.code === "matrix_authentication_required") {
          setError(EXCHANGE_ERROR_COPY.authenticationRequired);
          setErrorAction("sign-in");
        } else if (exchangeError.code === "matrix_exchange_disabled") {
          setError(EXCHANGE_ERROR_COPY.exchangeDisabled);
          setErrorAction("dashboard");
        } else if (exchangeError.code === "matrix_configuration_error") {
          setError(EXCHANGE_ERROR_COPY.configurationError);
          setErrorAction("dashboard");
        } else if (exchangeError.code === "matrix_timeout") {
          setError(EXCHANGE_ERROR_COPY.timeout);
          setErrorAction("retry");
        } else if (
          exchangeError.code === "matrix_room_creation_failed" ||
          exchangeError.code === "matrix_upstream_error"
        ) {
          setError(EXCHANGE_ERROR_COPY.providerUnavailable);
          setErrorAction("retry");
        } else if (exchangeError.code === "matrix_room_forbidden") {
          setError(EXCHANGE_ERROR_COPY.roomForbidden);
          setErrorAction("sign-in");
        } else if (exchangeError.code === "matrix_invitation_forbidden") {
          setError(EXCHANGE_ERROR_COPY.invitationForbidden);
          setErrorAction("retry");
        } else if (exchangeError.code === "matrix_participant_not_found") {
          setError(EXCHANGE_ERROR_COPY.participantNotFound);
          setErrorAction("retry");
        } else if (exchangeError.code === "matrix_invitation_failed") {
          setError(EXCHANGE_ERROR_COPY.invitationFailed);
          setErrorAction("retry");
        } else {
          setError(EXCHANGE_ERROR_COPY.unavailable);
          setErrorAction("retry");
        }
        setViewState("error");
      }
    },
    [forcedState, roomName, participantId, isOfflineMode]
  );

  const onLeaveRoom = useCallback(() => {
    if (forcedState) {
      return;
    }
    setRoom(null);
    setRoomName("");
    setParticipantId("");
    setError(null);
    setErrorAction(null);
    setViewState("empty");
  }, [forcedState]);

  const onErrorAction = useCallback(() => {
    if (forcedState) {
      return;
    }
    if (errorAction === "sign-in") {
      try {
        sessionStorage.setItem(AUTH_RETURN_PATH_KEY, "/exchange");
      } catch {
        // The backend post-login route remains available when storage is blocked.
      }
      window.location.assign(`${API_BASE}/api/v1/auth/matrix/login`);
      return;
    }
    if (errorAction === "dashboard") {
      window.location.assign("/dashboard");
      return;
    }
    setError(null);
    setErrorAction(null);
    setViewState("empty");
  }, [errorAction, forcedState]);

  return useMemo(() => {
    if (forcedState) {
      return {
        viewState: forcedState,
        room: forcedState === "success" ? EXCHANGE_SAMPLE_ROOM : null,
        roomName: forcedState === "empty" ? "" : EXCHANGE_SAMPLE_ROOM.name,
        roomNamePlaceholder: EXCHANGE_ROOM_NAME_PLACEHOLDER,
        participantId: "",
        participantPlaceholder: EXCHANGE_PARTICIPANT_PLACEHOLDER,
        error: forcedState === "error" ? EXCHANGE_ERROR_COPY.unavailable : null,
        errorAction: forcedState === "error" ? "retry" : null,
        errorActionLabel: forcedState === "error" ? "Try again" : null,
        canCreateRoom: false,
        setRoomName,
        setParticipantId,
        onCreateRoom,
        onLeaveRoom,
        onErrorAction,
      };
    }

    return {
      viewState,
      room,
      roomName,
      roomNamePlaceholder: EXCHANGE_ROOM_NAME_PLACEHOLDER,
      participantId,
      participantPlaceholder: EXCHANGE_PARTICIPANT_PLACEHOLDER,
      error,
      errorAction,
      errorActionLabel:
        errorAction === "sign-in"
          ? "Sign in with Matrix"
          : errorAction === "dashboard"
            ? "Go to dashboard"
            : errorAction === "retry"
              ? "Try again"
              : null,
      canCreateRoom:
        viewState === "empty" && roomName.trim().length > 0 && participantId.trim().length > 0,
      setRoomName,
      setParticipantId,
      onCreateRoom,
      onLeaveRoom,
      onErrorAction,
    };
  }, [
    forcedState,
    viewState,
    room,
    roomName,
    participantId,
    error,
    errorAction,
    setRoomName,
    onCreateRoom,
    onLeaveRoom,
    onErrorAction,
  ]);
}
