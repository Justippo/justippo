import { useEffect } from "react";
import { useConnectivityStore } from "../stores/useConnectivityStore";

/**
 * Bridge hook — auto-subscribes to NetInfo on mount.
 * Returns { isConnected, isInternetReachable }.
 */
export function useConnectivity() {
  const { isConnected, isInternetReachable, subscribe } =
    useConnectivityStore();

  useEffect(() => {
    const unsubscribe = subscribe();
    return unsubscribe;
  }, [subscribe]);

  return { isConnected, isInternetReachable };
}
