"use client";

import { useT } from "@/hooks/useT";

export default function TermsPage() {
  const { t } = useT();

  return (
    <div className="legal-page">
      <main className="legal-page__content">
        <h1 className="legal-page__title">{t("page.terms.title")}</h1>
        <section className="legal-page__section">
          <h2>1. Acceptance of Terms</h2>
          <p>
            By using EvidenceEU, you agree to these Terms of Service. If you do not agree, do not
            use the platform.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>2. Description of Service</h2>
          <p>
            EvidenceEU provides document translation, OCR extraction, semantic search, and secure
            exchange for cross-border document users in the European Union.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>3. User Obligations</h2>
          <p>
            You agree not to upload malicious content, attempt to circumvent security measures, or
            use the platform for unlawful purposes. You are responsible for the accuracy of
            documents you submit.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>4. Limitation of Liability</h2>
          <p>
            EvidenceEU provides machine translations and OCR results as-is, without warranty of
            accuracy or legal validity. Translations are for reference only and do not constitute
            legal advice. Always verify critical documents with a qualified professional.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>5. Service Availability</h2>
          <p>
            We strive for 99.9% uptime but do not guarantee uninterrupted service. Planned
            maintenance is scheduled outside business hours CET.
          </p>
        </section>
        <section className="legal-page__section">
          <h2>6. Governing Law</h2>
          <p>
            These terms are governed by the laws of Ireland (as an EU member state) and the General
            Data Protection Regulation (EU) 2016/679.
          </p>
        </section>
      </main>
    </div>
  );
}
