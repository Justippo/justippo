export type ConfidenceBadgeVariant = "success" | "warning" | "error";

export function getConfidenceBadgeVariant(confidence: number): ConfidenceBadgeVariant {
  if (confidence >= 0.8) {
    return "success";
  }
  if (confidence >= 0.5) {
    return "warning";
  }
  return "error";
}

export function formatConfidencePercent(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

export function averageConfidence(
  pages: readonly { readonly confidence: number | null }[]
): number {
  const scored = pages.filter((page) => page.confidence != null);
  if (scored.length === 0) {
    return 0;
  }
  const total = scored.reduce((sum, page) => sum + (page.confidence ?? 0), 0);
  return total / scored.length;
}
