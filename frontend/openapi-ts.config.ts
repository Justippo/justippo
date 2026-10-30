import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../docs/api/openapi.json",
  output: "src/lib/api-generated/gen",
  plugins: [
    {
      name: "@hey-api/typescript",
      enums: "javascript",
    },
    {
      name: "@hey-api/sdk",
      asClass: false,
    },
    {
      name: "@hey-api/client-fetch",
      runtimeConfigPath: "../client-config",
    },
  ],
});
