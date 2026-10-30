"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { UploadResponse } from "@/lib/api-generated";
import { UPLOAD_HISTORY, type UploadHistoryItem } from "@/data/mockData";
import { averageConfidence } from "@/lib/upload-confidence";

interface UseUploadHistoryResult {
  readonly history: readonly UploadHistoryItem[];
  readonly recordUpload: (filename: string, result: UploadResponse, targetLang: string) => void;
}

export function useUploadHistory(): UseUploadHistoryResult {
  const [history, setHistory] = useState<readonly UploadHistoryItem[]>([]);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("evidenceeu_upload_history");
      if (stored) {
        setHistory(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }, []);

  const recordUpload = useCallback(
    (filename: string, result: UploadResponse, targetLang: string) => {
      const item: UploadHistoryItem = {
        id: result.doc_id,
        filename,
        uploadedAt: new Date().toISOString(),
        pageCount: result.page_count,
        avgConfidence: averageConfidence(result.pages),
        targetLang,
      };
      setHistory((prev) => {
        const next = [item, ...prev.filter((entry) => entry.id !== item.id)].slice(0, 8);
        try {
          sessionStorage.setItem("evidenceeu_upload_history", JSON.stringify(next));
        } catch {}
        return next;
      });
    },
    []
  );

  return useMemo(() => ({ history, recordUpload }), [history, recordUpload]);
}
