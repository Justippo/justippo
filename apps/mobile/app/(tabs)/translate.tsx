import { View, Text, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export default function TranslateScreen() {
  return (
    <SafeAreaView className="flex-1 bg-white">
      <View className="flex-1 px-4 pt-4">
        <Text className="text-2xl font-bold text-gray-900 mb-4">Translate</Text>

        <View className="mb-4">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            Source Language
          </Text>
          <View className="border border-gray-300 rounded-lg p-3">
            <Text className="text-gray-900">English</Text>
          </View>
        </View>

        <View className="mb-4">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            Target Language
          </Text>
          <View className="border border-gray-300 rounded-lg p-3">
            <Text className="text-gray-900">German</Text>
          </View>
        </View>

        <View className="flex-1 mb-4">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            Document Text
          </Text>
          <TextInput
            className="flex-1 border border-gray-300 rounded-lg p-3 text-gray-900"
            multiline
            placeholder="Paste document text here..."
            placeholderTextColor="#9CA3AF"
          />
        </View>

        <View className="flex-1">
          <Text className="text-sm font-medium text-gray-700 mb-2">
            Translation
          </Text>
          <View className="flex-1 border border-gray-200 rounded-lg p-3 bg-gray-50">
            <Text className="text-gray-500">
              Translation will appear here...
            </Text>
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}
