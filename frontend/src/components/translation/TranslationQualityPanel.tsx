import { CheckCircle2, CircleAlert } from "lucide-react";
import type { TranslationQualityReport } from "@/lib/api-generated";
import { Badge } from "@/components/atoms";
import { useT } from "@/hooks/useT";

interface TranslationQualityPanelProps {
  readonly report: TranslationQualityReport;
  readonly glossaryTermsApplied: number;
}

export function TranslationQualityPanel({
  report,
  glossaryTermsApplied,
}: Readonly<TranslationQualityPanelProps>) {
  const { t } = useT();

  return (
    <section
      className="mt-lg rounded-lg border border-outline-variant bg-surface-container-lowest p-md"
      aria-labelledby="translation-quality-heading"
      data-testid="translation-quality-report"
    >
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <h2 id="translation-quality-heading" className="text-headline-md text-on-surface">
          {t("translation.quality.title")}
        </h2>
        <Badge variant={report.status === "pass" ? "success" : "warning"}>
          {report.status === "pass"
            ? t("translation.quality.passed")
            : t("translation.quality.review")}
        </Badge>
      </div>
      <p className="mt-xs text-body-sm text-on-surface-variant">
        {report.translated_section_count} {t("translation.quality.of")}{" "}
        {report.source_section_count} {t("translation.quality.sections_translated")}
        {report.failed_section_count > 0
          ? `; ${report.failed_section_count} ${t("translation.quality.failed")}`
          : ""}
        .
      </p>
      <ul className="mt-md flex list-none flex-col gap-sm p-0">
        {(report.checks ?? []).map((check) => {
          const Icon = check.status === "pass" ? CheckCircle2 : CircleAlert;
          return (
            <li key={check.code} className="flex gap-sm text-body-sm text-on-surface">
              <Icon
                className={
                  check.status === "pass" ? "shrink-0 text-success" : "shrink-0 text-warning"
                }
                size={20}
                aria-hidden="true"
              />
              <span>{check.message}</span>
            </li>
          );
        })}
      </ul>
      <p className="mt-md text-body-sm text-on-surface-variant">
        {t("translation.quality.terminology")}:{" "}
        {report.terminology_review_status === "applied"
          ? `${glossaryTermsApplied} ${t(
              glossaryTermsApplied === 1
                ? "translation.quality.correction"
                : "translation.quality.corrections"
            )} ${t("translation.quality.applied")}`
          : report.terminology_review_status === "checked_no_changes"
            ? t("translation.quality.no_changes")
            : glossaryTermsApplied > 0
              ? `${glossaryTermsApplied} ${t(
                  glossaryTermsApplied === 1
                    ? "translation.quality.correction"
                    : "translation.quality.corrections"
                )} ${t("translation.quality.applied_partial")}`
              : t("translation.quality.not_checked")}
      </p>
    </section>
  );
}
