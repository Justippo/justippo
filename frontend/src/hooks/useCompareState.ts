"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { computeDiff, type DiffBlock } from "@/lib/diff";

type CompareStatus = "empty" | "loading" | "success" | "error";

interface CompareState {
  readonly status: CompareStatus;
  readonly blocks: readonly DiffBlock[];
  readonly compare: (source: string, target: string) => void;
  readonly reset: () => void;
}

export function useCompareState(): CompareState {
  const [status, setStatus] = useState<CompareStatus>("empty");
  const [blocks, setBlocks] = useState<DiffBlock[]>([]);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const compare = useCallback((source: string, target: string) => {
    setStatus("loading");
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      try {
        const result = computeDiff(source, target);
        if (mountedRef.current) {
          setBlocks(result);
          setStatus("success");
        }
      } catch {
        if (mountedRef.current) {
          setStatus("error");
        }
      }
    }, 0);
  }, []);

  const reset = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setStatus("empty");
    setBlocks([]);
  }, []);

  return { status, blocks, compare, reset };
}
