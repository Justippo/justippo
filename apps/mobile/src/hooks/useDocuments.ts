import { useDocumentStore, DocumentState } from "../stores/useDocumentStore";

/**
 * Bridge hook — provides document management.
 * Matches the pattern expected by MOBILE_GAP-annotated components.
 */
export function useDocuments(): DocumentState {
  return useDocumentStore();
}
