"use client";

import { Shield, Users } from "lucide-react";
import styles from "./ExchangeView.module.css";
import { useExchangeView, type ExchangeViewState } from "@/hooks/useExchangeView";
import { Badge, Button, Input, Skeleton } from "@/components/atoms";

interface ExchangeViewProps {
  readonly className?: string;
  readonly forcedState?: ExchangeViewState;
}

function formatRoomDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ExchangeView({ className = "", forcedState }: Readonly<ExchangeViewProps>) {
  const exchange = useExchangeView({ forcedState });

  if (exchange.viewState === "loading") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.centerState} role="status" aria-label="Creating exchange room">
          <Skeleton height="1.5rem" width="220px" />
          <p className={styles.stateText}>Setting up your secure exchange room…</p>
        </div>
      </div>
    );
  }

  if (exchange.viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.centerState} role="alert">
          <h1 className={styles.heading}>Document exchange</h1>
          <p className={styles.stateText} data-testid="exchange-error">
            {exchange.error}
          </p>
          {exchange.errorActionLabel && (
            <Button
              variant="primary"
              onClick={exchange.onErrorAction}
              data-testid="exchange-error-action"
            >
              {exchange.errorActionLabel}
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (exchange.viewState === "success" && exchange.room) {
    const room = exchange.room;

    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.roomHeader}>
          <div>
            <h1 className={styles.heading} data-testid="exchange-room-name">
              {room.name}
            </h1>
            <p className={styles.roomMeta} data-testid="exchange-room-id">
              Room ID: {room.id}
            </p>
          </div>
          <Badge variant="success" data-testid="exchange-room-status">
            Active
          </Badge>
        </div>

        <div className={styles.securityRow}>
          <Shield className={styles.securityIcon} aria-hidden="true" />
          <span className={styles.securityText}>{room.encryptionLabel}</span>
        </div>

        {room.documentName && (
          <p className={styles.documentLine} data-testid="exchange-document">
            Shared document: {room.documentName}
          </p>
        )}

        <p className={styles.createdAt}>Created {formatRoomDate(room.createdAt)}</p>

        <section className={styles.participantsSection}>
          <div className={styles.sectionHeading}>
            <Users className={styles.sectionIcon} aria-hidden="true" />
            <h2 className={styles.sectionTitle}>Participants</h2>
          </div>
          <ul className={styles.participantList}>
            {room.participants.map((participant) => (
              <li key={participant.id} className={styles.participant}>
                <span className={styles.participantName}>{participant.name}</span>
                <Badge variant="default">{participant.role}</Badge>
              </li>
            ))}
          </ul>
        </section>

        <div className={styles.actions}>
          <Button variant="secondary" onClick={exchange.onLeaveRoom} data-testid="exchange-leave">
            Leave room
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.centerState}>
        <h1 className={styles.heading}>Document exchange</h1>
        <p className={styles.stateText}>
          Create a secure room to share documents with colleagues across borders. Rooms are
          end-to-end encrypted and access is limited to invited participants.
        </p>
        <form className={styles.createForm} onSubmit={exchange.onCreateRoom}>
          <label className={styles.fieldLabel} htmlFor="exchange-room-name">
            Room name
          </label>
          <Input
            id="exchange-room-name"
            data-testid="exchange-room-input"
            value={exchange.roomName}
            placeholder={exchange.roomNamePlaceholder}
            onChange={(event) => exchange.setRoomName(event.target.value)}
          />
          <label className={styles.fieldLabel} htmlFor="exchange-participant-id">
            Participant ID
          </label>
          <Input
            id="exchange-participant-id"
            data-testid="exchange-participant-input"
            value={exchange.participantId}
            placeholder={exchange.participantPlaceholder}
            onChange={(event) => exchange.setParticipantId(event.target.value)}
          />
          {exchange.error && (
            <p
              className={styles.validationError}
              role="alert"
              data-testid="exchange-validation-error"
            >
              {exchange.error}
            </p>
          )}
          <Button
            variant="primary"
            type="submit"
            disabled={!exchange.canCreateRoom}
            data-testid="exchange-create"
          >
            Create room
          </Button>
        </form>
      </div>
    </div>
  );
}
