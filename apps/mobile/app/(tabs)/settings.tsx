import { View, Text, Switch, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuthState, useGDPRConsent } from "../../src/hooks";

export default function SettingsScreen() {
  const { isAuthenticated, logout } = useAuthState();
  const { hasConsent, grantConsent, revokeConsent } = useGDPRConsent();

  return (
    <SafeAreaView className="flex-1 bg-white">
      <View className="flex-1 px-4 pt-4">
        <Text className="text-2xl font-bold text-gray-900 mb-6">Settings</Text>

        <View className="mb-6">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            Account
          </Text>
          <View className="border border-gray-200 rounded-lg p-4">
            <Text className="font-medium text-gray-900">
              {isAuthenticated ? "Signed in" : "Not signed in"}
            </Text>
          </View>
        </View>

        <View className="mb-6">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            Privacy
          </Text>
          <View className="flex-row items-center justify-between border border-gray-200 rounded-lg p-4">
            <Text className="text-gray-900">GDPR Consent</Text>
            <Switch
              value={hasConsent}
              onValueChange={(value) => (value ? grantConsent() : revokeConsent())}
              trackColor={{ false: "#D1D5DB", true: "#005796" }}
            />
          </View>
        </View>

        <View className="mb-6">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            About
          </Text>
          <View className="border border-gray-200 rounded-lg p-4">
            <Text className="text-gray-900">EvidenceEU v0.1.0</Text>
            <Text className="text-sm text-gray-500 mt-1">
              Cross-border document intelligence
            </Text>
          </View>
        </View>

        {isAuthenticated && (
          <Pressable
            onPress={logout}
            className="bg-error rounded-lg p-4 items-center"
          >
            <Text className="text-white font-semibold">Sign Out</Text>
          </Pressable>
        )}
      </View>
    </SafeAreaView>
  );
}
