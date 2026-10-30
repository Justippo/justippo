"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

const DEFAULT_CITATION_TITLE = "Official EU source";
const TRUSTED_GUIDANCE_HOSTS = new Set(["sede.agenciatributaria.gob.es"]);

export function trustedCitationUrl(value: string | null | undefined): string | null {
  if (!value) return null;

  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase();
    const trustedHost = hostname === "europa.eu" || hostname.endsWith(".europa.eu");
    const trustedPort = url.port === "" || url.port === "443";

    if (url.protocol !== "https:" || !trustedHost || !trustedPort || url.username || url.password) {
      return null;
    }

    return url.toString();
  } catch {
    return null;
  }
}

export function trustedGuidanceUrl(value: string | null | undefined): string | null {
  if (!value) return null;

  try {
    const url = new URL(value);
    const trustedHost = TRUSTED_GUIDANCE_HOSTS.has(url.hostname.toLowerCase());
    const trustedPort = url.port === "" || url.port === "443";
    if (url.protocol !== "https:" || !trustedHost || !trustedPort || url.username || url.password) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

export function buildCitationGatewayHref(sourceUrl: string, sourceTitle?: string | null): string {
  const params = new URLSearchParams({ source: sourceUrl });
  if (sourceTitle) params.set("title", sourceTitle);
  return `/citation?${params.toString()}`;
}

interface CitationAccessState {
  readonly isAuthenticated: boolean;
  readonly isLoading: boolean;
  readonly isValid: boolean;
  readonly sourceUrl: string | null;
  readonly sourceTitle: string;
  readonly signInHref: string;
  readonly signUpHref: string;
}

export function useCitationAccess(): CitationAccessState {
  const searchParams = useSearchParams();
  const { isAuthenticated, isLoading } = useAuth();

  return useMemo(() => {
    const sourceUrl = trustedCitationUrl(searchParams?.get("source") ?? null);
    const requestedTitle = searchParams?.get("title")?.trim();
    const sourceTitle = requestedTitle?.slice(0, 200) || DEFAULT_CITATION_TITLE;
    const returnPath = sourceUrl ? buildCitationGatewayHref(sourceUrl, sourceTitle) : "/search";
    const encodedReturnPath = encodeURIComponent(returnPath);

    return {
      isAuthenticated,
      isLoading,
      isValid: sourceUrl !== null,
      sourceUrl,
      sourceTitle,
      signInHref: `/login?redirect=${encodedReturnPath}`,
      signUpHref: `/register?redirect=${encodedReturnPath}`,
    };
  }, [isAuthenticated, isLoading, searchParams]);
}
