import { View, Text, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export default function SearchScreen() {
  return (
    <SafeAreaView className="flex-1 bg-white">
      <View className="flex-1 px-4 pt-4">
        <Text className="text-2xl font-bold text-gray-900 mb-4">
          Search Documents
        </Text>

        <TextInput
          className="border border-gray-300 rounded-lg p-3 text-gray-900 mb-4"
          placeholder="Search your documents..."
          placeholderTextColor="#9CA3AF"
        />

        <View className="flex-1 items-center justify-center">
          <Text className="text-gray-500 text-center">
            Enter a search query to find information{"\n"}across your documents.
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}
