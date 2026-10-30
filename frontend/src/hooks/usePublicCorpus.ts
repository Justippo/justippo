"use client";

import { useMemo } from "react";
import { PUBLIC_CORPUS_DOCUMENTS, PUBLIC_CORPUS_META } from "@/data/mockData";
import type { PublicCorpusDocument } from "@/data/mockData";

export type PublicCorpusState = "loading" | "success" | "error" | "empty";

interface UsePublicCorpusOptions {
  readonly forcedState?: PublicCorpusState;
}

interface UsePublicCorpusResult {
  readonly viewState: PublicCorpusState;
  readonly meta: typeof PUBLIC_CORPUS_META;
  readonly documents: readonly PublicCorpusDocument[];
  readonly errorMessage: string | null;
}

export function usePublicCorpus({
  forcedState,
}: Readonly<UsePublicCorpusOptions> = {}): UsePublicCorpusResult {
  const viewState: PublicCorpusState = forcedState ?? "success";

  return useMemo(() => {
    if (viewState === "loading") {
      return {
        viewState,
        meta: PUBLIC_CORPUS_META,
        documents: [],
        errorMessage: null,
      };
    }

    if (viewState === "error") {
      return {
        viewState,
        meta: PUBLIC_CORPUS_META,
        documents: [],
        errorMessage: "The public corpus catalogue is temporarily unavailable. Please try again.",
      };
    }

    if (viewState === "empty") {
      return {
        viewState,
        meta: PUBLIC_CORPUS_META,
        documents: [],
        errorMessage: null,
      };
    }

    return {
      viewState,
      meta: PUBLIC_CORPUS_META,
      documents: PUBLIC_CORPUS_DOCUMENTS,
      errorMessage: null,
    };
  }, [viewState]);
}
