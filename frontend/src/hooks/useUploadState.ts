"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { uploadDocument, type UploadResponse } from "@/lib/api-generated";
import { saveUploadSession } from "@/lib/upload-session";

type UploadStatus = "empty" | "loading" | "success" | "error";

interface UploadState {
  readonly status: UploadStatus;
  readonly result: UploadResponse | null;
  readonly error: string | null;
  readonly upload: (file: File, targetLang: string) => void;
  readonly reset: () => void;
}

export function useUploadState(): UploadState {
  const [status, setStatus] = useState<UploadStatus>("empty");
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const upload = useCallback(async (file: File, targetLang: string) => {
    setStatus("loading");
    setError(null);
    try {
      const res = await uploadDocument(file, targetLang);
      if (mountedRef.current) {
        setResult(res);
        setStatus("success");
        saveUploadSession(file, res, targetLang);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Upload failed");
        setStatus("error");
      }
    }
  }, []);

  const reset = useCallback(() => {
    setStatus("empty");
    setResult(null);
    setError(null);
  }, []);

  return { status, result, error, upload, reset };
}
