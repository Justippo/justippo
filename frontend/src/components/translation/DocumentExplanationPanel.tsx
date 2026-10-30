import { CheckCircle2 } from "lucide-react";
import type { DocumentExplanation } from "@/lib/api-generated";
import { useT } from "@/hooks/useT";

interface DocumentExplanationPanelProps {
  readonly explanation: DocumentExplanation;
  readonly warnings: readonly string[];
}

export function DocumentExplanationPanel({
  explanation,
  warnings,
}: Readonly<DocumentExplanationPanelProps>) {
  const { t } = useT();

  return (
    <>
      {warnings.length > 0 && (
        <section className="space-y-xs" aria-label={t("translation.explanation.notices")}>
          {warnings.map((warning) => (
            <p
              key={warning}
              className="rounded-md border border-warning bg-surface-container-lowest p-sm text-label-sm text-warning"
            >
              {warning}
            </p>
          ))}
        </section>
      )}

      <div className="grid gap-md lg:grid-cols-2">
        <section className="rounded-lg border border-outline-variant bg-surface-container-lowest p-lg">
          <h2 className="flex items-center gap-xs text-headline-md text-on-surface">
            <CheckCircle2 className="text-success" size={20} aria-hidden="true" />
            {t("translation.explanation.requirements_title")}
          </h2>
          {explanation.requirements.length > 0 ? (
            <ul className="mt-md space-y-sm">
              {explanation.requirements.map((requirement) => (
                <li
                  key={`${requirement.kind}-${requirement.page_number}-${requirement.text}`}
                  className="border-l-2 border-primary pl-sm text-body-md text-on-surface"
                >
                  {requirement.text}
                  {requirement.page_number && (
                    <span className="ml-xs text-label-sm text-on-surface-variant">
                      {t("translation.upload.page")} {requirement.page_number}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-md text-body-md text-on-surface-variant">
              {t("translation.explanation.no_requirements")}
            </p>
          )}
        </section>

        <section className="rounded-lg border border-outline-variant bg-surface-container-lowest p-lg">
          <h2 className="text-headline-md text-on-surface">
            {t("translation.explanation.eu_context")}
          </h2>
          {explanation.explanation ? (
            <p className="mt-md whitespace-pre-wrap text-body-md text-on-surface">
              {explanation.explanation}
            </p>
          ) : (
            <p className="mt-md text-body-md text-on-surface-variant">
              {t("translation.explanation.no_summary")}
            </p>
          )}
          {explanation.citations.length > 0 && (
            <ol className="mt-md space-y-sm">
              {explanation.citations.map((citation) => (
                <li key={citation.url} className="text-body-md text-on-surface">
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-bold text-primary underline focus:outline focus:outline-2 focus:outline-focus"
                  >
                    {t("translation.explanation.source")} {citation.source_number}: {citation.title}
                  </a>
                  <p className="mt-xs text-label-sm text-on-surface-variant">{citation.excerpt}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </>
  );
}
