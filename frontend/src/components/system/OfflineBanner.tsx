import styles from "./OfflineBanner.module.css";
import { OFFLINE_BANNER_MESSAGE } from "@/data/mockData";

interface OfflineBannerProps {
  readonly className?: string;
  readonly message?: string;
}

export function OfflineBanner({
  className = "",
  message = OFFLINE_BANNER_MESSAGE,
}: Readonly<OfflineBannerProps>) {
  return (
    <div className={`${styles.banner} ${className}`} role="status" data-testid="offline-banner">
      {message}
    </div>
  );
}
