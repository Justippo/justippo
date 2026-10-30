const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");

// SDK 52+ auto-detects monorepos and configures Metro.
// No manual watchFolders or nodeModulesPaths needed.
// See: https://docs.expo.dev/guides/monorepos/
const config = getDefaultConfig(__dirname);

module.exports = withNativeWind(config, { input: "./global.css" });
