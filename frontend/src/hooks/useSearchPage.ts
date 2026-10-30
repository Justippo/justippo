"use client";

import { useMemo } from "react";
import type { FormEvent } from "react";
import { useAuth } from "@/context/AuthContext";
import { SEARCH_ERROR_COPY, SEARCH_SAMPLE_RESULTS } from "@/data/mockData";
import { buildCitationGatewayHref, trustedCitationUrl } from "@/hooks/useCitationAccess";
import { useSearchView } from "./useSearchView";
import type { SSEResult } from "./useSearch";

export type SearchPageState = "loading" | "success" | "error" | "empty";

interface UseSearchPageOptions {
  readonly forcedState?: SearchPageState;
}

interface UseSearchPageResult {
  readonly viewState: SearchPageState;
  readonly corpusLabel: string;
  readonly isAuthenticated: boolean;
  readonly searchPlaceholder: string;
  readonly emptyText: string;
  readonly emptyHintSuffix: string | null;
  readonly results: readonly SearchPageResult[];
  readonly error: string | null;
  readonly retry: () => void;
  readonly query: string;
  readonly setQuery: (value: string) => void;
  readonly handleSubmit: (e: FormEvent<HTMLFormElement>) => void;
}

export type SearchPageResult = SSEResult & {
  readonly citationHref?: string;
  readonly citationTarget?: "_blank";
};

const EMPTY_ERROR = SEARCH_ERROR_COPY.unavailable;

function presentResults(
  results: readonly SSEResult[],
  isAuthenticated: boolean
): readonly SearchPageResult[] {
  return results.map((result) => {
    const sourceUrl = trustedCitationUrl(result.source_url);
    if (!sourceUrl) return result;

    return {
      ...result,
      citationHref: isAuthenticated
        ? sourceUrl
        : buildCitationGatewayHref(sourceUrl, result.source_title),
      citationTarget: isAuthenticated ? "_blank" : undefined,
    };
  });
}

export function useSearchPage({
  forcedState,
}: Readonly<UseSearchPageOptions> = {}): UseSearchPageResult {
  const { isAuthenticated } = useAuth();
  const live = useSearchView();

  const corpusLabel = isAuthenticated
    ? "Personal documents + public corpus"
    : "Public corpus — EUR-Lex";

  const searchPlaceholder = isAuthenticated
    ? "Search your documents…"
    : "Search EU legal documents…";

  const emptyText = isAuthenticated
    ? "Search across your uploaded documents and the public EU corpus."
    : "Search public EU legal documents from EUR-Lex and official sources.";

  const emptyHintSuffix = isAuthenticated
    ? null
    : "to include your uploaded documents in search results.";

  return useMemo(() => {
    if (!forcedState) {
      return {
        viewState: live.status,
        corpusLabel,
        isAuthenticated,
        searchPlaceholder,
        emptyText,
        emptyHintSuffix,
        results: presentResults(live.results, isAuthenticated),
        error: live.error,
        retry: live.retry,
        query: live.query,
        setQuery: live.setQuery,
        handleSubmit: live.handleSubmit,
      };
    }

    const noop = () => {};
    const noopSubmit = (e: FormEvent<HTMLFormElement>) => e.preventDefault();

    switch (forcedState) {
      case "loading":
        return {
          viewState: "loading" as const,
          corpusLabel,
          isAuthenticated,
          searchPlaceholder,
          emptyText,
          emptyHintSuffix,
          results: [],
          error: null,
          retry: noop,
          query: "residence permit extension",
          setQuery: noop,
          handleSubmit: noopSubmit,
        };
      case "error":
        return {
          viewState: "error" as const,
          corpusLabel,
          isAuthenticated,
          searchPlaceholder,
          emptyText,
          emptyHintSuffix,
          results: [],
          error: EMPTY_ERROR,
          retry: noop,
          query: "residence permit",
          setQuery: noop,
          handleSubmit: noopSubmit,
        };
      case "success":
        return {
          viewState: "success" as const,
          corpusLabel,
          isAuthenticated,
          searchPlaceholder,
          emptyText,
          emptyHintSuffix,
          results: presentResults(SEARCH_SAMPLE_RESULTS, isAuthenticated),
          error: null,
          retry: noop,
          query: "residence permit extension Germany",
          setQuery: noop,
          handleSubmit: noopSubmit,
        };
      case "empty":
      default:
        return {
          viewState: "empty" as const,
          corpusLabel,
          isAuthenticated,
          searchPlaceholder,
          emptyText,
          emptyHintSuffix,
          results: [],
          error: null,
          retry: noop,
          query: "",
          setQuery: noop,
          handleSubmit: noopSubmit,
        };
    }
  }, [
    forcedState,
    corpusLabel,
    isAuthenticated,
    searchPlaceholder,
    emptyText,
    emptyHintSuffix,
    live,
  ]);
}
