"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { useSearch } from "./useSearch";
import { useIsClient } from "./useIsClient";

type SearchHook = ReturnType<typeof useSearch>;

interface SearchViewState {
  readonly results: SearchHook["results"];
  readonly status: SearchHook["status"];
  readonly error: SearchHook["error"];
  readonly retry: SearchHook["retry"];
  readonly query: string;
  readonly setQuery: (value: string) => void;
  readonly handleSubmit: (e: FormEvent<HTMLFormElement>) => void;
}

/**
 * Controller hook for SearchView: composes useSearch, seeds the query from
 * the `?q=` URL param after hydration, and exposes the submit handler.
 */
export function useSearchView(): SearchViewState {
  const { results, status, error, retry, search } = useSearch();
  const searchParams = useSearchParams();
  const isClient = useIsClient();
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (isClient) {
      const q = searchParams?.get("q") ?? null;
      if (q) {
        setQuery(q);
        search(q);
      }
    }
  }, [isClient, searchParams, search]);

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (query.trim()) {
      search(query);
    }
  };

  return { results, status, error, retry, query, setQuery, handleSubmit };
}
