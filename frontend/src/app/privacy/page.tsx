"use client";

import { useT } from "@/hooks/useT";

export default function PrivacyPage() {
  const { t } = useT();

  return (
    <div className="legal-page">
      <main className="legal-page__content">
        <h1 className="legal-page__title">{t("page.privacy.title")}</h1>
        <section className="legal-page__section">
          <h2>1. Data Controller</h2>
          <p>
            EvidenceEU operates as a multilingual document intelligence platform. As a data
            controller under Article 4(7) GDPR, we process personal data only to the extent
            necessary for providing our services.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>2. What We Collect</h2>
          <p>
            We collect only the data you explicitly provide: uploaded documents, account credentials
            (email, name), and usage metadata (page views, feature interactions). We do not collect
            browsing history, location data, or sensitive personal data beyond what you upload.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>3. Purpose & Legal Basis</h2>
          <p>
            Data is processed for document translation, OCR extraction, and secure exchange under
            Article 6(1)(a) (consent) and Article 6(1)(f) (legitimate interest — service
            improvement, security monitoring).
          </p>
        </section>
        <section className="legal-page__section">
          <h2>4. Data Retention</h2>
          <p>
            Uploaded documents are processed ephemerally — deleted immediately after translation or
            exchange completes. Account data is retained until account deletion. Usage metadata is
            retained for 90 days.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>5. Your Rights</h2>
          <p>
            Under Articles 15–22 GDPR, you have the right to access, rectify, erase, restrict, and
            port your data. Contact us at privacy@evidenceeu.app to exercise these rights.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>6. Third-Party Processors</h2>
          <p>
            We use Cloudflare Workers AI for LLM inference and Cloudflare D1 for structured storage.
            Both act as data processors under Article 28 GDPR. No data is transferred outside the
            EEA.
          </p>
        </section>
      </main>
    </div>
  );
}
