import type { CreateClientConfig } from "./gen/client.gen";
import { API_BASE } from "@/lib/config";

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: API_BASE,
  credentials: "include",
});
