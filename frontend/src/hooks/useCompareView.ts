"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useCompareState } from "./useCompareState";
import { useIsClient } from "./useIsClient";
import {
  COMPARE_SAMPLE_BLOCKS,
  COMPARE_SAMPLE_FILENAME,
  COMPARE_SAMPLE_SOURCE_TEXT,
  COMPARE_SAMPLE_TARGET_TEXT,
} from "@/data/mockData";
import type { DiffBlock } from "@/lib/diff";

export type CompareViewState = "loading" | "success" | "error" | "empty";
export type CompareViewMode = "unified" | "side-by-side";

interface UseCompareViewOptions {
  readonly forcedState?: CompareViewState;
}

interface CompareViewResult {
  readonly viewState: CompareViewState;
  readonly viewMode: CompareViewMode;
  readonly blocks: readonly DiffBlock[];
  readonly filename: string | null;
  readonly error: string | null;
  readonly reset: () => void;
  readonly onToggleViewMode: () => void;
}

const FORCED_ERROR_MESSAGE = "Comparison could not be completed. Please try again.";

/**
 * Controller hook for CompareView: loads source/target text from sessionStorage
 * after hydration and runs the client-side diff, or serves forced Storybook states.
 */
export function useCompareView({
  forcedState,
}: Readonly<UseCompareViewOptions> = {}): CompareViewResult {
  const { status, blocks, compare, reset } = useCompareState();
  const isClient = useIsClient();
  const [viewMode, setViewMode] = useState<CompareViewMode>("unified");

  const onToggleViewMode = useCallback(() => {
    setViewMode((prev) => (prev === "unified" ? "side-by-side" : "unified"));
  }, []);

  useEffect(() => {
    if (forcedState || !isClient || status !== "empty") {
      return;
    }

    try {
      const raw = sessionStorage.getItem("evidence-eu-compare-data");
      if (!raw) {
        return;
      }

      const data = JSON.parse(raw) as {
        blocks?: readonly { sourceText: string; targetText?: string }[];
        filename?: string;
      };

      if (!data.blocks || data.blocks.length === 0) {
        return;
      }

      const source = data.blocks.map((block) => block.sourceText).join("\n\n");
      const target = data.blocks.map((block) => block.targetText ?? block.sourceText).join("\n\n");
      compare(source, target);
    } catch {
      // Stay in empty state when session data is invalid.
    }
  }, [forcedState, isClient, status, compare]);

  return useMemo(() => {
    if (forcedState) {
      return {
        viewState: forcedState,
        viewMode,
        blocks: forcedState === "success" ? COMPARE_SAMPLE_BLOCKS : [],
        filename: forcedState === "success" ? COMPARE_SAMPLE_FILENAME : null,
        error: forcedState === "error" ? FORCED_ERROR_MESSAGE : null,
        reset,
        onToggleViewMode,
      };
    }

    const liveViewState: CompareViewState = status === "empty" ? "empty" : status;

    return {
      viewState: liveViewState,
      viewMode,
      blocks,
      filename: liveViewState === "success" ? COMPARE_SAMPLE_FILENAME : null,
      error: liveViewState === "error" ? FORCED_ERROR_MESSAGE : null,
      reset,
      onToggleViewMode,
    };
  }, [forcedState, status, blocks, reset, viewMode, onToggleViewMode]);
}
