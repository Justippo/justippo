import { create } from "zustand";
import NetInfo, { NetInfoState } from "@react-native-community/netinfo";

export interface ConnectivityState {
  isConnected: boolean;
  isInternetReachable: boolean | null;
  subscribe: () => () => void;
}

export const useConnectivityStore = create<ConnectivityState>()((set) => ({
  isConnected: true,
  isInternetReachable: true,

  subscribe: () => {
    const unsubscribe = NetInfo.addEventListener((state: NetInfoState) => {
      set({
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
      });
    });
    return unsubscribe;
  },
}));
