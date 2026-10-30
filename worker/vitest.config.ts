import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // For standard unmocked fetch tests we don't need the pool.
    // We will directly instantiate the fetch event.
  },
});
