import type { ErrorEvent } from "@sentry/nextjs";

const NEW_RELIC_FRAME_MARKERS = ["js-agent.newrelic.com/", "nr-loader-spa-", "nr-spa-"] as const;
const TOLGEE_FETCH_FAILURE = 'Tolgee: Failed to fetch record for "';
const EVENT_PROMISE_REJECTION = "captured as promise rejection";

function isNewRelicFrame(frame: { abs_path?: string; filename?: string }): boolean {
  const source = `${frame.abs_path ?? ""} ${frame.filename ?? ""}`;
  return NEW_RELIC_FRAME_MARKERS.some((marker) => source.includes(marker));
}

function isNewRelicOnlyError(event: ErrorEvent): boolean {
  const exceptions = event.exception?.values ?? [];

  return (
    exceptions.length > 0 &&
    exceptions.every((exception) => {
      const frames = exception.stacktrace?.frames ?? [];
      return frames.length > 0 && frames.every(isNewRelicFrame);
    })
  );
}

function isKnownTolgeeEventRejection(event: ErrorEvent): boolean {
  const exceptionValues = event.exception?.values ?? [];
  const isEventRejection = exceptionValues.some((exception) => {
    const description = `${exception.type ?? ""} ${exception.value ?? ""}`;
    return description.includes("Event") && description.includes(EVENT_PROMISE_REJECTION);
  });

  if (!isEventRejection) {
    return false;
  }

  return (event.breadcrumbs ?? []).some((breadcrumb) =>
    breadcrumb.message?.includes(TOLGEE_FETCH_FAILURE)
  );
}

/** Drop only verified third-party browser noise; preserve application errors. */
export function filterBrowserSentryEvent(event: ErrorEvent): ErrorEvent | null {
  if (isNewRelicOnlyError(event) || isKnownTolgeeEventRejection(event)) {
    return null;
  }

  return event;
}
