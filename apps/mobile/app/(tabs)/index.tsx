import { View, Text, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useDocuments } from "../../src/hooks";
import { useConnectivity } from "../../src/hooks";

export default function DocumentsScreen() {
  const { documents, selectedId } = useDocuments();
  const { isConnected } = useConnectivity();

  return (
    <SafeAreaView className="flex-1 bg-white">
      <View className="flex-1 px-4 pt-4">
        <View className="flex-row items-center justify-between mb-4">
          <Text className="text-2xl font-bold text-gray-900">Documents</Text>
          {!isConnected && (
            <Text className="text-sm text-warning">Offline</Text>
          )}
        </View>

        {documents.length === 0 ? (
          <View className="flex-1 items-center justify-center">
            <Text className="text-gray-500 text-center">
              No documents yet.{"\n"}Tap + to upload a document.
            </Text>
            <Pressable className="mt-4 bg-primary px-6 py-3 rounded-lg">
              <Text className="text-white font-semibold">Upload Document</Text>
            </Pressable>
          </View>
        ) : (
          <View>
            {documents.map((doc) => (
              <View
                key={doc.id}
                className={`p-4 border-b border-gray-100 ${selectedId === doc.id ? "bg-blue-50" : ""}`}
              >
                <Text className="font-medium text-gray-900">{doc.name}</Text>
                <Text className="text-sm text-gray-500">
                  {(doc.size / 1024).toFixed(1)} KB · {doc.status}
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}
