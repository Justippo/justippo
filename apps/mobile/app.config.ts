import { ExpoConfig } from "expo/config";

const config: ExpoConfig = {
  name: "EvidenceEU",
  slug: "evidence-eu",
  owner: "chindris-mihai-alexandru",
  version: "0.1.0",
  orientation: "portrait",
  scheme: "evidenceeu",
  userInterfaceStyle: "automatic",
  platforms: ["ios", "android", "web"],
  web: {
    bundler: "metro",
    output: "single",
  },
  ios: {
    supportsTablet: true,
    bundleIdentifier: "eu.evidence.evidenceeu",
  },
  android: {
    adaptiveIcon: {
      backgroundColor: "#005796",
    },
    package: "eu.evidence.evidenceeu",
  },
  plugins: ["expo-router", "expo-secure-store"],
  extra: {
    eas: {
      projectId: "5d43a3c5-eb32-417b-9337-7e328653d1d6",
    },
  },
};

export default config;
