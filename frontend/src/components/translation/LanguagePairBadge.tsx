import { ArrowRight } from "lucide-react";
import styles from "./LanguagePairBadge.module.css";
import { Badge } from "@/components/atoms";
import { formatLanguageCode } from "@/lib/language-codes";
import { useT } from "@/hooks/useT";

interface LanguagePairBadgeProps {
  readonly sourceLang: string;
  readonly targetLang: string;
  readonly className?: string;
}

export function LanguagePairBadge({
  sourceLang,
  targetLang,
  className = "",
}: Readonly<LanguagePairBadgeProps>) {
  const { t } = useT();

  return (
    <div
      className={`${styles.pair} ${className}`}
      data-testid="language-pair-badge"
      aria-label={`${t("translation.language_pair")} ${formatLanguageCode(sourceLang)} ${t(
        "translation.to"
      )} ${formatLanguageCode(targetLang)}`}
    >
      <Badge variant="info" data-testid="language-pair-source">
        {formatLanguageCode(sourceLang)}
      </Badge>
      <ArrowRight className={styles.arrow} aria-hidden="true" />
      <Badge variant="success" data-testid="language-pair-target">
        {formatLanguageCode(targetLang)}
      </Badge>
    </div>
  );
}
