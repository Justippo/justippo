export const LANDING_SECTIONS = [
  {
    id: "hero",
    headline: "Cross-border documents, understood.",
    subheadline:
      "Upload, translate, and search legal documents across EU languages — with formatting preserved and AI-powered accuracy.",
  },
  {
    id: "upload",
    headline: "Upload & Extract",
    description:
      "Drop any PDF, DOCX, or scanned image. Our OCR pipeline extracts text with 98%+ confidence, preserving document structure.",
    stat: "98%",
    statLabel: "OCR Confidence",
  },
  {
    id: "translate",
    headline: "Translate Instantly",
    description:
      "Professional-grade translation across English, German, and French. Legal terminology handled by specialised glossaries.",
    stat: "3",
    statLabel: "EU Languages",
  },
  {
    id: "search",
    headline: "Search & Discover",
    description:
      "Ask questions in natural language. RAG-powered search returns cited answers from your document corpus in real time.",
    stat: "<3s",
    statLabel: "p95 Latency",
  },
] as const;

export const LANDING_HERO = {
  headline: "Document intelligence for a borderless Europe.",
  subheadline:
    "Search, translate, and exchange cross-border documents with EU-grade compliance and formatting preserved.",
  primaryCta: "Get started free",
  primaryHref: "/register",
  secondaryCta: "See how it works",
  secondaryHref: "#how-it-works",
} as const;

export const LANDING_PROBLEM = {
  headline: "Cross-border documents shouldn't be this hard",
  points: [
    "40M+ people live and work across EU borders — yet their documents stay trapped in single-language silos.",
    "Legal complexity multiplies with every jurisdiction. Generic tools miss terminology, tables, and signatures.",
    "DeepL breaks tables. English-only incumbents ignore multilingual corpora. Neither was built for regulated EU work.",
  ],
} as const;

export const LANDING_SOLUTION_PILLARS = [
  {
    id: "search",
    title: "Search",
    description: "Query in German, find answers from French regulations.",
    icon: "Search" as const,
  },
  {
    id: "translation",
    title: "Translation",
    description: "Upload a PDF, get it back with tables and signatures intact.",
    icon: "Globe" as const,
  },
  {
    id: "exchange",
    title: "Exchange",
    description: "Share documents securely across borders.",
    icon: "Shield" as const,
  },
] as const;

export const LANDING_TRUST_ITEMS = [
  {
    id: "compliance",
    title: "GDPR-native processing",
    description: "Edge processing on EU infrastructure with consent on every request.",
    icon: "Lock" as const,
  },
  {
    id: "documents",
    title: "Formatting preserved",
    description:
      "OCR and translation pipelines keep tables, signatures, and legal structure intact.",
    icon: "FileText" as const,
  },
  {
    id: "teams",
    title: "Built for professionals",
    description: "Designed for migrants, legal teams, and HR workflows crossing EU borders.",
    icon: "Users" as const,
  },
] as const;

export const LANDING_CTA = {
  headline: "Start for free. No credit card required.",
  buttonLabel: "Create your account",
  href: "/register",
} as const;

export const LANDING_NARRATIVE_STEPS = [
  { id: "challenge", label: "The challenge" },
  { id: "capabilities", label: "What EvidenceEU does" },
  { id: "trust", label: "Trust by design" },
  { id: "start", label: "Start now" },
] as const;

export const CHAT_MESSAGES = [
  {
    id: "msg-1",
    role: "user" as const,
    content: "What are the requirements for extending a residence permit in Germany?",
    timestamp: "2026-07-09T10:00:00Z",
  },
  {
    id: "msg-2",
    role: "assistant" as const,
    content:
      "According to Section 8 of the German Residence Act (Aufenthaltsgesetz), a residence permit can be extended if the conditions for its issuance still apply. You must apply at least 6 weeks before expiry at your local Ausländerbehörde.",
    timestamp: "2026-07-09T10:00:05Z",
    sources: [
      { title: "AufenthG §8", url: "https://www.gesetze-im-internet.de/aufenthg_2004/__8.html" },
    ],
  },
  {
    id: "msg-3",
    role: "user" as const,
    content: "What documents do I need to bring?",
    timestamp: "2026-07-09T10:01:00Z",
  },
  {
    id: "msg-4",
    role: "assistant" as const,
    content:
      "Typically you need: (1) valid passport, (2) current residence permit, (3) proof of employment or income, (4) health insurance certificate, (5) rental contract or registration certificate (Meldebescheinigung), and (6) biometric passport photo. Requirements may vary by permit type.",
    timestamp: "2026-07-09T10:01:08Z",
    sources: [],
  },
] as const;

export const PUBLIC_CORPUS_META = {
  title: "EU Public Document Corpus",
  description:
    "Indexed regulations, directives, and official guidance from EUR-Lex and member-state sources. Available to all visitors without an account.",
  source: "EUR-Lex",
  languages: ["EN", "DE", "FR"] as const,
} as const;

export interface PublicCorpusDocument {
  readonly id: string;
  readonly title: string;
  readonly jurisdiction: string;
  readonly language: string;
  readonly category: string;
}

export const PUBLIC_CORPUS_DOCUMENTS: readonly PublicCorpusDocument[] = [
  {
    id: "doc-gdpr",
    title: "Regulation (EU) 2016/679 (General Data Protection Regulation)",
    jurisdiction: "European Union",
    language: "EN",
    category: "Regulation",
  },
  {
    id: "doc-aufenthg",
    title: "Aufenthaltsgesetz (German Residence Act) — §8 Extension",
    jurisdiction: "Germany",
    language: "DE",
    category: "National law",
  },
  {
    id: "doc-labor-fr",
    title: "Code du travail — Contrat de travail à durée indéterminée",
    jurisdiction: "France",
    language: "FR",
    category: "Labour law",
  },
  {
    id: "doc-mobility",
    title: "Directive 2014/66/EU on intra-corporate transferees",
    jurisdiction: "European Union",
    language: "EN",
    category: "Directive",
  },
] as const;

/** Seeded query for capstone demo — guaranteed results on live deploy (§1.4). */
export const SEARCH_SEEDED_QUERY = "residence permit extension Germany";

export const SEARCH_ERROR_COPY = {
  unavailable: "Search is temporarily unavailable — please try again.",
  retrying: "Search is temporarily unavailable — retrying…",
} as const;

export const SEARCH_SAMPLE_RESULTS = [
  {
    id: "chunk-demo-001",
    text: "Die Verlängerung eines Aufenthaltstitels richtet sich nach §8 AufenthG. Der Antrag muss mindestens 6 Wochen vor Ablauf der Gültigkeit gestellt werden.",
    type: "world",
    chunk_id: "chunk-demo-001",
    entities: ["Aufenthaltstitel", "§8 AufenthG"],
    rank: 1,
  },
  {
    id: "chunk-demo-002",
    text: "Section 18 of the German Residence Act (Aufenthaltsgesetz) grants residence permits for qualified professional employment. Holders are entitled to work without a separate work permit.",
    type: "world",
    chunk_id: "chunk-demo-002",
    entities: ["Aufenthaltsgesetz", "Section 18"],
    rank: 2,
  },
] as const;

export const CHAT_EMPTY_PROMPT = {
  heading: "Ask a legal question",
  placeholder: "What would you like to know about EU law?",
  corpusLabel: "Public corpus — EUR-Lex",
  signInPrompt: "Sign in to ask questions using the EUR-Lex public corpus.",
} as const;

export const CHAT_AUTH_PROMPT = {
  heading: "Ask a legal question",
  placeholder: "What would you like to know about EU law?",
  corpusLabel: "Public corpus — EUR-Lex",
  inputHint: "Answers use verified EUR-Lex sources.",
} as const;

export interface UploadHistoryItem {
  readonly id: string;
  readonly filename: string;
  readonly uploadedAt: string;
  readonly pageCount: number;
  readonly avgConfidence: number;
  readonly targetLang: string;
}

export const UPLOAD_HISTORY: readonly UploadHistoryItem[] = [
  {
    id: "hist-1",
    filename: "residence-permit.pdf",
    uploadedAt: "2026-07-11T14:22:00Z",
    pageCount: 4,
    avgConfidence: 0.94,
    targetLang: "de",
  },
  {
    id: "hist-2",
    filename: "employment-contract.docx",
    uploadedAt: "2026-07-10T09:15:00Z",
    pageCount: 12,
    avgConfidence: 0.81,
    targetLang: "en",
  },
  {
    id: "hist-3",
    filename: "tax-assessment-scan.png",
    uploadedAt: "2026-07-08T16:40:00Z",
    pageCount: 2,
    avgConfidence: 0.62,
    targetLang: "fr",
  },
] as const;

export const UPLOAD_SAMPLE_RESULT = {
  doc_id: "doc-sample-001",
  status: "processed",
  ephemeral: true,
  page_count: 3,
  target_language: "en",
  pages: [
    {
      page: 1,
      text: "Antrag auf Verlängerung der Aufenthaltserlaubnis gemäß § 8 Aufenthaltsgesetz.",
      confidence: 0.96,
    },
    {
      page: 2,
      text: "Der Antragsteller legt Nachweise über Erwerbstätigkeit und Krankenversicherung vor. Zusätzlich sind Meldebescheinigung, aktueller Reisepass und biometrisches Passfoto erforderlich. Die Ausländerbehörde prüft die Voraussetzungen gemäß den geltenden Verwaltungsvorschriften.",
      confidence: 0.78,
    },
    {
      page: 3,
      text: "Unterschrift und Datum der zuständigen Ausländerbehörde.",
      confidence: 0.58,
    },
  ],
  classification: {
    document_type: "residence_permit",
    language_code: "de",
    quality_score: 0.77,
    confidence: 0.77,
  },
} as const;

export const UPLOAD_PREVIEW_CHAR_LIMIT = 120;

export const UPLOAD_ERROR_COPY = {
  unavailable: "Upload could not be completed. Check your connection and try again.",
} as const;

export const UPLOAD_LOW_QUALITY_WARNING =
  "Scan quality is below recommended thresholds — review extracted text carefully.";

export function formatUploadPreviewNotice(charLimit: number): string {
  return `Preview limited to first ${charLimit} characters per page.`;
}

export const TRANSLATION_SAMPLE_FILENAME = "residence-permit-application.pdf";

export const TRANSLATION_ERROR_COPY = {
  unavailable: "Translation could not be completed. Check your connection and try again.",
  timeout: "Translation took too long. Please try again.",
} as const;

export const TRANSLATION_TRUNCATION_NOTICE = "Preview limited to the first pages of this document.";

export const TRANSLATION_SAMPLE_SOURCE_PAGES = [
  {
    page: 1,
    text: "Antrag auf Verlängerung der Aufenthaltserlaubnis gemäß § 8 Aufenthaltsgesetz.",
  },
  {
    page: 2,
    text: "Der Antragsteller legt Nachweise über Erwerbstätigkeit und Krankenversicherung vor. Zusätzlich sind Meldebescheinigung, aktueller Reisepass und biometrisches Passfoto erforderlich. Die Ausländerbehörde prüft die Voraussetzungen gemäß den geltenden Verwaltungsvorschriften.",
  },
  {
    page: 3,
    text: "Unterschrift und Datum der zuständigen Ausländerbehörde.",
  },
] as const;

export const TRANSLATION_SAMPLE_RESULT = {
  job_id: "job-sample-translation-001",
  status: "completed",
  translated_pages: [
    {
      page: 1,
      text: "Application for extension of residence permit pursuant to Section 8 of the Residence Act.",
    },
    {
      page: 2,
      text: "The applicant submits proof of employment and health insurance. In addition, a registration certificate, current passport, and biometric passport photo are required. The immigration authority reviews the requirements in accordance with applicable administrative regulations.[truncated]",
    },
    {
      page: 3,
      text: "Signature and date of the competent immigration authority.",
    },
  ],
} as const;

export const PDF_REFERENCE_SAMPLE_RESULT = {
  request_id: "request-reference-001",
  status: "done" as const,
  ephemeral: true as const,
  output_mode: "reference" as const,
  original_unchanged: true as const,
  form_filling_supported: false as const,
  source_language: "de" as const,
  target_language: "en" as const,
  translated_pdf_b64: "JVBERi0xLjcKJSVFT0Y=",
  translated_pdf_content_type: "application/pdf" as const,
  detected_source_language: "de",
  layout_preserved: true,
  pages_processed: 2,
  classification: {
    document_type: "residence_application",
    language_code: "de",
    quality_score: 0.94,
    geographic_relevance: ["Germany", "European"],
    safety_flags: [],
    confidence: 0.91,
  },
  document_explanation: {
    document_type: "residence_application",
    language: "en",
    requirements: [
      { text: "Proof of residence", kind: "field" as const, page_number: 1 },
      { text: "You must attach a current passport copy.", kind: "instruction" as const },
    ],
    explanation:
      "The retrieved EU source describes residence rights and supporting conditions [SOURCE 1].",
    legal_context_status: "grounded" as const,
    citations: [
      {
        source_number: 1,
        title: "Directive 2004/38/EC",
        url: "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32004L0038",
        excerpt: "Article 7 describes residence rights and supporting conditions.",
        language: "en",
        document_id: "eurlex-32004L0038-en",
      },
    ],
    warnings: [],
  },
  warnings: ["REFERENCE_COPY_ONLY"],
} as const;

export const COMPARE_SAMPLE_FILENAME = "residence-permit-application.pdf";

export const COMPARE_SAMPLE_SOURCE_TEXT =
  "EU-Aufenthaltstitel-Antragsformular.\n\nName: Johann Doe.\n\nNationalität: Deutsch.";

export const COMPARE_SAMPLE_TARGET_TEXT =
  "EU-Aufenthaltstitel-Antragsformular.\n\nName: Jean Doe.\n\nNationalité: Française.";

export const COMPARE_SAMPLE_BLOCKS = [
  {
    type: "unchanged" as const,
    sourceText: "EU-Aufenthaltstitel-Antragsformular.",
  },
  {
    type: "modified" as const,
    sourceText: "Name: Johann Doe.\n\nNationalität: Deutsch.",
    targetText: "Name: Jean Doe.\n\nNationalité: Française.",
  },
];

export const EXCHANGE_ROOM_NAME_PLACEHOLDER = "e.g. Residence permit review";
export const EXCHANGE_PARTICIPANT_PLACEHOLDER = "@name:organisation.eu";

export const EXCHANGE_ERROR_COPY = {
  unavailable: "Unable to create the exchange room. Check your connection and try again.",
  authenticationRequired:
    "Your Matrix session has expired or is unavailable. Sign in with Matrix to continue.",
  exchangeDisabled:
    "Secure document exchange is not available right now. You can return to the dashboard and try again later.",
  configurationError:
    "The Matrix service is not configured. Contact your administrator to enable document exchange.",
  timeout:
    "Matrix is taking too long to respond. This may be due to a slow connection. Please try again.",
  providerUnavailable:
    "The Matrix service could not create the room. Your entries are preserved so you can try again.",
  roomForbidden:
    "Your Matrix account is not permitted to create rooms. Contact your Matrix administrator.",
  invitationForbidden:
    "The participant's Matrix server rejected the invitation. Ask them to verify their account and invitation settings.",
  participantNotFound:
    "The Matrix participant could not be found. Check the complete Matrix ID and try again.",
  invitationFailed:
    "The room could not invite this participant. Check their Matrix ID or try again later.",
  rateLimited: "Matrix is limiting room requests. Please wait before trying again.",
  roomNameRequired: "Enter a room name to continue.",
  participantRequired: "Enter a participant ID to continue.",
  participantInvalid: "Use a participant ID in the format @name:organisation.eu.",
} as const;

export interface ExchangeParticipant {
  readonly id: string;
  readonly name: string;
  readonly role: string;
}

export const EXCHANGE_SAMPLE_ROOM = {
  id: "room-eu-2024-0891",
  name: "Residence permit review",
  status: "active" as const,
  createdAt: "2026-07-10T14:32:01Z",
  documentName: "residence-permit-application.pdf",
  encryptionLabel: "End-to-end encrypted · GDPR-native",
  participants: [
    { id: "p1", name: "Mihai C.", role: "Owner" },
    { id: "p2", name: "Member 2", role: "Member" },
  ] satisfies readonly ExchangeParticipant[],
} as const;

export const SETTINGS_SECTIONS = [
  { id: "profile", label: "Profile & security", icon: "User" as const },
  { id: "compliance", label: "Compliance", icon: "Shield" as const },
  { id: "accessibility", label: "Accessibility", icon: "Accessibility" as const },
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]["id"];

export const SETTINGS_GDPR_DOMAINS = [
  {
    id: "domain-1",
    title: "Ephemeral processing",
    description: "Document bytes stay in memory only — no server-side persistence.",
    status: "pass" as const,
  },
  {
    id: "domain-2",
    title: "AI Gateway routing",
    description: "All model calls route through the Cloudflare AI Gateway.",
    status: "pass" as const,
  },
  {
    id: "domain-3",
    title: "GDPR consent middleware",
    description: "Protected endpoints require explicit consent headers.",
    status: "pass" as const,
  },
  {
    id: "domain-4",
    title: "Feature flag gate security",
    description: "Optional integrations are disabled unless explicitly enabled.",
    status: "pass" as const,
  },
  {
    id: "domain-5",
    title: "Secrets hygiene",
    description: "API keys and tokens are injected at deploy time, never committed.",
    status: "pass" as const,
  },
  {
    id: "domain-6",
    title: "Dependency license audit",
    description: "Third-party licenses are reviewed on every dependency change.",
    status: "pass" as const,
  },
  {
    id: "domain-7",
    title: "Input validation",
    description: "Language codes and document identifiers are validated at the API boundary.",
    status: "pass" as const,
  },
  {
    id: "domain-8",
    title: "Translation pipeline boundary",
    description: "Layout-preserving translation runs in an isolated sidecar over HTTP.",
    status: "pass" as const,
  },
] as const;

export type SettingsGdprDomain = (typeof SETTINGS_GDPR_DOMAINS)[number];

export const SETTINGS_LANGUAGE_OPTIONS = [
  { code: "en", label: "English" },
  { code: "de", label: "German" },
  { code: "fr", label: "French" },
] as const;

export const OFFLINE_BANNER_MESSAGE = "You're viewing sample data.";

export const DASHBOARD_STATUS_BADGES = {
  online: "Online",
  unavailable: "Temporarily unavailable",
  languages: "EN · DE · FR",
} as const;

export const DASHBOARD_COPY = {
  privacyTitle: "Private by design",
  privacyDescription:
    "Documents and search queries are processed ephemerally and are not retained as workspace history.",
  emptyTitle: "Your workspace is ready",
  emptyDescription: "Translate a document to begin a new private processing session.",
  emptyAction: "Translate your first document",
} as const;

export const DASHBOARD_ERROR_COPY = {
  unavailable: "Unable to load dashboard data. Please try again.",
} as const;

export const NOT_FOUND_COPY = {
  title: "Page not found",
  description:
    "The page you requested does not exist or may have moved. Check the address or return to the workspace.",
  homeLabel: "Go to home",
  homeHref: "/",
} as const;

export const ERROR_PAGE_COPY = {
  title: "Something went wrong",
  description:
    "An unexpected error occurred. You can try again or return to the home page while we investigate.",
  retryLabel: "Try again",
  homeLabel: "Go to home",
  homeHref: "/",
} as const;
