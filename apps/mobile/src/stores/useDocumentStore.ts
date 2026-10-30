import { create } from "zustand";

export interface Document {
  id: string;
  name: string;
  size: number;
  mimeType: string;
  createdAt: string;
  status: "uploading" | "processing" | "ready" | "error";
  progress?: number;
}

export interface DocumentState {
  documents: Document[];
  selectedId: string | null;
  isUploading: boolean;
  error: string | null;
  addDocument: (doc: Document) => void;
  updateDocument: (id: string, updates: Partial<Document>) => void;
  removeDocument: (id: string) => void;
  setSelectedId: (id: string | null) => void;
  setUploading: (uploading: boolean) => void;
  setError: (error: string | null) => void;
  clearAll: () => void;
}

export const useDocumentStore = create<DocumentState>()((set) => ({
  documents: [],
  selectedId: null,
  isUploading: false,
  error: null,

  addDocument: (doc) =>
    set((state) => ({ documents: [...state.documents, doc] })),

  updateDocument: (id, updates) =>
    set((state) => ({
      documents: state.documents.map((d) =>
        d.id === id ? { ...d, ...updates } : d,
      ),
    })),

  removeDocument: (id) =>
    set((state) => ({
      documents: state.documents.filter((d) => d.id !== id),
      selectedId: state.selectedId === id ? null : state.selectedId,
    })),

  setSelectedId: (id) => set({ selectedId: id }),
  setUploading: (isUploading) => set({ isUploading }),
  setError: (error) => set({ error }),
  clearAll: () => set({ documents: [], selectedId: null }),
}));
