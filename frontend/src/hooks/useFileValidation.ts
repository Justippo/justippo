"use client";

import { useCallback, useState } from "react";

const MAX_SIZE_BYTES = 15 * 1024 * 1024;
const MAX_PDF_SIZE_BYTES = 4 * 1024 * 1024;
const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
];

interface FileValidation {
  readonly fileError: string | null;
  readonly validate: (file: File) => boolean;
}

/**
 * Validates an uploaded file against the size and MIME-type limits, tracking the
 * current error message. Returns true when the file is acceptable.
 */
export function useFileValidation(): FileValidation {
  const [fileError, setFileError] = useState<string | null>(null);

  const validate = useCallback((file: File): boolean => {
    let err: string | null = null;
    if (file.type === "application/pdf" && file.size > MAX_PDF_SIZE_BYTES) {
      err = `PDF size is ${(file.size / 1024 / 1024).toFixed(1)} MB, which is above the 4 MB limit for translation.`;
    } else if (file.size > MAX_SIZE_BYTES) {
      err = `File size is ${Math.round(file.size / 1024 / 1024)} MB, which is above the 15 MB limit.`;
    } else if (!ALLOWED_TYPES.includes(file.type)) {
      err = `"${file.name}" is not a supported file type. Please upload PDF, DOCX, PNG, or JPEG.`;
    }
    setFileError(err);
    return err === null;
  }, []);

  return { fileError, validate };
}
