# Production Component Generation from Stitch Reference

**Purpose:** Detailed instructions for AI agents to convert Stitch design references into production React components.

**Tool:** AI coding agent (AdaL, Zed IDE, or equivalent) — the agentic coding environment for this repo. The agent reads `AGENTS.md` automatically.

**Source of Truth:** Stitch project `16375579204261083556` (105 screens)
**Screenshots:** `docs/stitch-reference/generated/` (105 PNG files)
**Stitch MCP:** `stitch-proxy` MCP server — reads Stitch project/screens for design reference. (See Agent Setup below for wiring.)
**Production Destination:** `frontend/src/components/` (organized by domain)

---

## Agent Setup (MCP Servers & Skills)

These are configured in Zed's `~/.zed/settings.json` under the evidence-eu project's `context_servers` (see ADR-014) and via Zed's skill system for skills. They must be available before running the workflow below.

### MCP servers
| Server | Purpose | Key |
|--------|---------|-----|
| `stitch-proxy` | Read Stitch project/screens (design source of truth) | `STITCH_API_KEY` |
| `hindsight` | Memory bank (retain/recall/reflect) | `Authorization: Bearer {token}` |
| `github` | Manage Issues/PRs from the agent | `GITHUB_TOKEN` |

AdaL MCP config (in `~/.adal/settings.json` — per-project `mcpServers` section):
- `stitch-proxy` — read Stitch design source of truth
- `hindsight` — memory bank for architecture decisions and context
- `github` — manage Issues/PRs

### Skills
EvidenceEU's project conventions live in `frontend/AGENTS.md` and `AGENTS.md` (root). For capstone docs, the `document-skills` suite (pdf/docx/pptx) is available via the agent skill system.

---

## How to Use This Guide

1. **Ensure MCP servers are live** — confirm `stitch-proxy` and `hindsight` are connected
2. **Point to this guide** — tell the agent: "Read `docs/reference/production-component-guide.md` and build the Upload flow components"
3. **Reference Stitch screenshots** — point to the PNG files in `docs/stitch-reference/generated/` for visual reference
4. **Refine into EvidenceEU architecture** — adapt the Stitch reference into `frontend/src/components/{domain}/` following Atomic Design, `Readonly<T>` props, logic in `src/hooks/`, theme-mapped Tailwind. Cherry-pick patterns; do not copy wholesale.
5. **Iterate & verify** — `bun run test`, add Storybook stories, verify against design tokens

**Example prompt:**
```
Read docs/reference/production-component-guide.md. Build the Upload flow (screens 01-15).
Use the screenshots in docs/stitch-reference/generated/screen-01-upload-idle.png through screen-15-upload-batch-complete.png as visual reference.
Refine into our architecture: Atomic Design (atoms → molecules → organisms), Readonly<T> props,
logic in src/hooks/, theme-mapped Tailwind (no hardcoded hex). Destination: frontend/src/components/upload/.
```

---

## Screen Inventory (105 Screens)

### Upload Flow (15 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 01 | Upload Idle | `screen-01-upload-idle.png` | Default drop zone state |
| 02 | Upload Dragover | `screen-02-upload-dragover.png` | File hovering over drop zone |
| 03 | Upload File Selected | `screen-03-upload-file-selected.png` | File ready to upload |
| 04 | Upload Processing | `screen-04-upload-processing.png` | OCR extracting text |
| 05 | Upload Success | `screen-05-upload-success.png` | Upload complete |
| 06 | Upload Error | `screen-06-upload-error.png` | Upload failed |
| 07 | Upload Multiple | `screen-07-upload-multiple.png` | Multiple files selected |
| 08 | Upload History | `screen-08-upload-history.png` | Recent uploads table |
| 09 | Upload Unsupported | `screen-09-upload-unsupported.png` | Wrong file format |
| 10 | Upload Quota | `screen-10-upload-quota.png` | Daily limit reached |
| 11 | Upload Network Error | `screen-11-upload-network-error.png` | Connection lost |
| 12 | Upload OCR | `screen-12-upload-ocr.png` | OCR processing with confidence |
| 13 | Upload Preview | `screen-13-upload-preview.png` | Document preview after upload |
| 14 | Upload GDPR | `screen-14-upload-gdpr.png` | GDPR consent form |
| 15 | Upload Batch Complete | `screen-15-upload-batch-complete.png` | Batch upload summary |

### Search Flow (11 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 16 | Search Empty | `screen-16-search-empty.png` | No query entered |
| 17 | Search Results | `screen-17-search-results.png` | Results list with filters |
| 18 | Search Loading | `screen-18-search-loading.png` | Searching... |
| 19 | Search No Results | `screen-19-search-no-results.png` | No matches found |
| 20 | Search Error | `screen-20-search-error.png` | Search failed |
| 21 | Search Advanced Filters | `screen-21-search-advanced-filters.png` | Filter sidebar |
| 22 | Search Suggestions | `screen-22-search-suggestions.png` | Autocomplete dropdown |
| 23 | Search Highlighted | `screen-23-search-highlighted.png` | Highlighted matching terms |
| 24 | Search History | `screen-24-search-history.png` | Recent searches |
| 25 | Search Cross-Document | `screen-25-search-cross-document.png` | Multi-document results |
| 26 | Search RAG Streaming | `screen-26-search-rag-streaming.png` | Streaming response |

### Translation Flow (13 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 27 | Translation Ready | `screen-27-translation-ready.png` | Document loaded, ready |
| 28 | Translation Progress | `screen-28-translation-progress.png` | Translating... |
| 29 | Translation Complete | `screen-29-translation-complete.png` | Translation done |
| 30 | Translation Error | `screen-30-translation-error.png` | Translation failed |
| 31 | Translation Language Selection | `screen-31-translation-language-selection.png` | Language picker modal |
| 32 | Translation Glossary | `screen-32-translation-glossary.png` | Terminology sidebar |
| 33 | Translation History | `screen-33-translation-history.png` | Previous translations |
| 34 | Translation Quality | `screen-34-translation-quality.png` | BLEU score, confidence |
| 35 | Translation Export | `screen-35-translation-export.png` | Export options modal |
| 36 | Translation Batch | `screen-36-translation-batch.png` | Multiple documents |
| 37 | Translation Diff | `screen-37-translation-diff.png` | Side-by-side diff |
| 38 | Translation Terminology | `screen-38-translation-terminology.png` | Term validation |
| 39 | Translation Sharing | `screen-39-translation-sharing.png` | Share modal |

### Compare Flow (15 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 40 | Compare Side-by-Side | `screen-40-compare-side-by-side.png` | Two panels |
| 41 | Compare Inline Diff | `screen-41-compare-inline-diff.png` | Merged view |
| 42 | Compare Document Selector | `screen-42-compare-document-selector.png` | Document picker |
| 43 | Compare Change Summary | `screen-43-compare-change-summary.png` | Change stats |
| 44 | Compare Terminology | `screen-44-compare-terminology.png` | Term comparison |
| 45 | Compare Export | `screen-45-compare-export.png` | Export options |
| 46 | Compare Historical | `screen-46-compare-historical.png` | Version history |
| 47 | Compare Quality | `screen-47-compare-quality.png` | Quality assessment |
| 48 | Compare Collaboration | `screen-48-compare-collaboration.png` | Comments |
| 49 | Compare Merge | `screen-49-compare-merge.png` | Merge view |
| 50 | Compare Search | `screen-50-compare-search.png` | Search within |
| 51 | Compare Shortcuts | `screen-51-compare-shortcuts.png` | Keyboard shortcuts |
| 52 | Compare Dark Mode | `screen-52-compare-dark-mode.png` | Dark theme |
| 53 | Compare Loading | `screen-53-compare-loading.png` | Loading state |
| 54 | Compare Error | `screen-54-compare-error.png` | Error state |

### Chat Flow (15 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 55 | Chat Logged Out | `screen-55-chat-logged-out.png` | Public chat |
| 56 | Chat Conversation | `screen-56-chat-conversation.png` | Active conversation |
| 57 | Chat Loading | `screen-57-chat-loading.png` | Thinking... |
| 58 | Chat Error | `screen-58-chat-error.png` | Error occurred |
| 59 | Chat Document Context | `screen-59-chat-document-context.png` | Document attached |
| 60 | Chat Search Integration | `screen-60-chat-search-integration.png` | Search results panel |
| 61 | Chat Translation Integration | `screen-61-chat-translation-integration.png` | Translation panel |
| 62 | Chat History | `screen-62-chat-history.png` | Conversation list |
| 63 | Chat Sharing | `screen-63-chat-sharing.png` | Share modal |
| 64 | Chat Feedback | `screen-64-chat-feedback.png` | Thumbs up/down |
| 65 | Chat Settings | `screen-65-chat-settings.png` | Model settings |
| 66 | Chat Typing | `screen-66-chat-typing.png` | Typing indicator |
| 67 | Chat Message Actions | `screen-67-chat-message-actions.png` | Context menu |
| 68 | Chat Attachments | `screen-68-chat-attachments.png` | File attachments |
| 69 | Chat Dark Mode | `screen-69-chat-dark-mode.png` | Dark theme |

### Exchange Flow (2 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 70 | Exchange Create Room | `screen-70-exchange-create-room.png` | Room creation form |
| 71 | Exchange Active Room | `screen-71-exchange-active-room.png` | Active room |

### Matrix Login Modal (10 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 72 | Matrix Login Default | `screen-72-matrix-login-default.png` | Login form |
| 73 | Matrix Login Error | `screen-73-matrix-login-error.png` | Invalid credentials |
| 74 | Matrix Login Loading | `screen-74-matrix-login-loading.png` | Authenticating... |
| 75 | Matrix Register | `screen-75-matrix-register.png` | Registration form |
| 76 | Matrix Forgot Password | `screen-76-matrix-forgot-password.png` | Password reset |
| 77 | Matrix Reset Success | `screen-77-matrix-reset-success.png` | Check your email |
| 78 | Matrix SSO | `screen-78-matrix-sso.png` | Google/Microsoft/GitHub |
| 79 | Matrix 2FA | `screen-79-matrix-2fa.png` | Two-factor auth |
| 80 | Matrix GDPR Consent | `screen-80-matrix-gdpr-consent.png` | Privacy consent |
| 81 | Matrix Login Mobile | `screen-81-matrix-login-mobile.png` | Mobile layout |

### Settings Flow (10 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 82 | Settings Profile | `screen-82-settings-profile.png` | Profile & security |
| 83 | Settings Privacy | `screen-83-settings-privacy.png` | GDPR toggles |
| 84 | Settings Notifications | `screen-84-settings-notifications.png` | Notification prefs |
| 85 | Settings Appearance | `screen-85-settings-appearance.png` | Theme, font, language |
| 86 | Settings Integrations | `screen-86-settings-integrations.png` | Connected services |
| 87 | Settings Billing | `screen-87-settings-billing.png` | Plan & usage |
| 88 | Settings Team | `screen-88-settings-team.png` | Team management |
| 89 | Settings API | `screen-89-settings-api.png` | API keys & docs |
| 90 | Settings Audit | `screen-90-settings-audit.png` | Audit log |
| 91 | Settings Success | `screen-91-settings-success.png` | Saved notification |

### Mobile Screens (14 screens)

| # | Screen | File | Description |
|---|--------|------|-------------|
| 92 | Mobile Upload Idle | `screen-92-mobile-upload-idle.png` | Mobile upload drop zone |
| 93 | Mobile Upload File Selected | `screen-93-mobile-upload-file-selected.png` | Mobile file selected |
| 94 | Mobile Upload Processing | `screen-94-mobile-upload-processing.png` | Mobile processing |
| 95 | Mobile Upload Success | `screen-95-mobile-upload-success.png` | Mobile success |
| 96 | Mobile Upload Error | `screen-96-mobile-upload-error.png` | Mobile error |
| 97 | Mobile Upload Dragover | `screen-97-mobile-upload-dragover.png` | Mobile dragover |
| 98 | Mobile Upload Unsupported | `screen-98-mobile-upload-unsupported.png` | Mobile unsupported |
| 99 | Mobile Search Empty | `screen-99-mobile-search-empty.png` | Mobile search empty |
| 100 | Mobile Search Results | `screen-100-mobile-search-results.png` | Mobile search results |
| 101 | Mobile Search Loading | `screen-101-mobile-search-loading.png` | Mobile search loading |
| 102 | Mobile Search No Results | `screen-102-mobile-search-no-results.png` | Mobile no results |
| 103 | Mobile Search Error | `screen-103-mobile-search-error.png` | Mobile search error |
| 104 | Mobile Exchange Create | `screen-104-mobile-exchange-create.png` | Mobile exchange create |
| 105 | Mobile Exchange Active | `screen-105-mobile-exchange-active.png` | Mobile exchange active |

---

## Production Component Guide

### Architecture Rules (Non-Negotiable)

#### 1. Atomic Design Hierarchy

```
src/components/{domain}/
├── atoms/          # Smallest UI elements (Button, Input, Badge, Icon)
├── molecules/      # Combinations (FileCard, SearchBar, TranslationPanel)
├── organisms/      # Complex sections (UploadForm, SearchResults, CompareView)
├── templates/      # Page layouts (UploadTemplate, SearchTemplate)
├── index.ts        # Barrel exports
└── __tests__/      # Component tests
```

#### 2. Type Safety

Every component MUST have a `Readonly<T>` props interface:

```typescript
// ✅ CORRECT
interface UploadFormProps {
  readonly file: File | null;
  readonly onUpload: (file: File) => void;
  readonly onCancel: () => void;
  readonly isProcessing?: boolean;
}

// ❌ WRONG — no interface, any props
function UploadForm({ file, onUpload, onCancel, isProcessing }: any) {
```

#### 3. Logic Isolation

Event handlers and side effects go in `src/hooks/`:

```typescript
// ✅ CORRECT — logic in hook
src/hooks/useUploadForm.ts
src/hooks/useFileValidation.ts
src/hooks/useDragAndDrop.ts

// ❌ WRONG — logic in component body
function UploadForm() {
  const [isDragging, setIsDragging] = useState(false);
  const handleDragEnter = () => setIsDragging(true);
  // ... 50 lines of logic
```

#### 4. Data Decoupling

Static content goes in `src/data/mockData.ts`:

```typescript
// ✅ CORRECT
src/data/mockData.ts
export const SUPPORTED_FILE_TYPES = ['PDF', 'DOCX', 'PNG'];
export const MAX_FILE_SIZE_MB = 15;

// ❌ WRONG — hardcoded in component
const SUPPORTED = ['PDF', 'DOCX', 'PNG']; // inside component
```

#### 5. Style Mapping

**NEVER hardcode hex values.** Use theme-mapped Tailwind classes:

```typescript
// ✅ CORRECT — theme-mapped
className="bg-primary text-on-primary"
className="bg-error-container text-on-error-container"

// ❌ WRONG — hardcoded hex
className="bg-[#005796] text-white"
className="bg-[#D4351C] text-white"
```

---

## Design Token Mapping

Stitch uses Material Design color roles. Map to Tailwind classes:

| Stitch Token | Hex | Tailwind Class |
|--------------|-----|----------------|
| primary | #005796 | `bg-primary` |
| on-primary | #ffffff | `text-on-primary` |
| primary-container | #1d70b8 | `bg-primary-container` |
| on-primary-container | #e9f1ff | `text-on-primary-container` |
| secondary | #5e5e5e | `text-secondary` |
| secondary-container | #e1dfdf | `bg-secondary-container` |
| on-secondary-container | #626262 | `text-on-secondary-container` |
| tertiary | #824600 | `text-tertiary` |
| tertiary-container | #a55a00 | `bg-tertiary-container` |
| error | #D4351C | `bg-error` |
| error-container | #ffdad6 | `bg-error-container` |
| on-error | #ffffff | `text-on-error` |
| on-error-container | #93000a | `text-on-error-container` |
| warning | #F47738 | `bg-warning` |
| success | #00703C | `bg-success` |
| surface | #faf9f8 | `bg-surface` |
| surface-dim | #dadad9 | `bg-surface-dim` |
| surface-container-lowest | #ffffff | `bg-surface-container-lowest` |
| surface-container-low | #f4f3f2 | `bg-surface-container-low` |
| surface-container | #efeeed | `bg-surface-container` |
| surface-container-high | #e9e8e7 | `bg-surface-container-high` |
| surface-container-highest | #e3e2e1 | `bg-surface-container-highest` |
| on-surface | #1a1c1c | `text-on-surface` |
| on-surface-variant | #414751 | `text-on-surface-variant` |
| outline | #717782 | `text-outline` |
| outline-variant | #c1c7d2 | `border-outline-variant` |
| focus | #FFDD00 | `ring-focus` |

### Typography Scale

| Stitch Token | CSS | Tailwind |
|--------------|-----|----------|
| headline-xl | 36px/44px 700 | `text-headline-xl` |
| headline-lg | 24px/32px 700 | `text-headline-lg` |
| headline-md | 19px/28px 700 | `text-headline-md` |
| body-lg | 19px/28px 400 | `text-body-lg` |
| body-md | 16px/24px 400 | `text-body-md` |
| label-md | 16px/24px 700 | `text-label-md` |
| label-sm | 14px/20px 400 | `text-label-sm` |
| code | 14px/20px 400 | `font-mono text-code` |

### Spacing

| Stitch Unit | Value | Tailwind |
|-------------|-------|----------|
| unit | 4px | `p-1` / `m-1` |
| xs | 8px | `p-2` / `m-2` |
| sm | 12px | `p-3` / `m-3` |
| md | 16px | `p-4` / `m-4` |
| lg | 24px | `p-6` / `m-6` |
| xl | 32px | `p-8` / `m-8` |
| container-max | 1280px | `max-w-container-max` |

---

## Per-Feature Prompt Templates

### Feature: Upload Flow

**Screens:** 01-15 (15 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Upload flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-01-upload-idle.png — Default drop zone
- screen-02-upload-dragover.png — File hovering
- screen-03-upload-file-selected.png — File ready to upload
- screen-04-upload-processing.png — OCR extracting
- screen-05-upload-success.png — Upload complete
- screen-06-upload-error.png — Upload failed
- screen-07-upload-multiple.png — Multiple files
- screen-08-upload-history.png — Recent uploads
- screen-09-upload-unsupported.png — Wrong format
- screen-10-upload-quota.png — Limit reached
- screen-11-upload-network-error.png — Connection lost
- screen-12-upload-ocr.png — OCR with confidence
- screen-13-upload-preview.png — Document preview
- screen-14-upload-gdpr.png — GDPR consent
- screen-15-upload-batch-complete.png — Batch summary

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useUploadForm.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/upload/
├── atoms/
│   ├── FileIcon.tsx
│   ├── ProgressIndicator.tsx
│   └── ConfidenceBadge.tsx
├── molecules/
│   ├── FileCard.tsx
│   ├── DragDropZone.tsx
│   └── UploadProgressBar.tsx
├── organisms/
│   ├── UploadForm.tsx
│   ├── UploadIdle.tsx
│   ├── UploadDragover.tsx
│   ├── UploadFileSelected.tsx
│   ├── UploadUploading.tsx
│   ├── UploadProcessing.tsx
│   ├── UploadComplete.tsx
│   └── UploadError.tsx
├── index.ts
└── __tests__/
    └── UploadForm.test.tsx

TOKEN MAPPING:
- Primary: bg-primary (#005796)
- Error: bg-error (#D4351C)
- Success: bg-success (#00703C)
- Surface: bg-surface (#faf9f8)
- On-surface: text-on-surface (#1a1c1c)

VALIDATION:
- Run: node scripts/validate.js (AST checks)
- No hardcoded hex values
- All props use Readonly<T> interfaces
- Logic extracted to hooks
- Static data in mockData.ts
```

### Feature: Search Flow

**Screens:** 16-26 (11 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Search flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-16-search-empty.png — No query
- screen-17-search-results.png — Results list
- screen-18-search-loading.png — Searching...
- screen-19-search-no-results.png — No matches
- screen-20-search-error.png — Search failed
- screen-21-search-advanced-filters.png — Filter sidebar
- screen-22-search-suggestions.png — Autocomplete
- screen-23-search-highlighted.png — Highlighted terms
- screen-24-search-history.png — Recent searches
- screen-25-search-cross-document.png — Multi-document
- screen-26-search-rag-streaming.png — Streaming response

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useSearch.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/search/
├── atoms/
│   ├── SearchIcon.tsx
│   ├── ResultCard.tsx
│   └── CitationBadge.tsx
├── molecules/
│   ├── SearchBar.tsx
│   ├── ResultItem.tsx
│   └── StreamingIndicator.tsx
├── organisms/
│   ├── SearchEmpty.tsx
│   ├── SearchResults.tsx
│   ├── SearchLoading.tsx
│   ├── SearchNoResults.tsx
│   ├── SearchError.tsx
│   ├── SearchAdvancedFilters.tsx
│   ├── SearchSuggestions.tsx
│   ├── SearchHighlighted.tsx
│   ├── SearchHistory.tsx
│   ├── SearchCrossDocument.tsx
│   └── SearchRAGStreaming.tsx
├── index.ts
└── __tests__/
    └── SearchBar.test.tsx
```

### Feature: Translation Flow

**Screens:** 27-39 (13 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Translation flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-27-translation-ready.png — Ready to translate
- screen-28-translation-progress.png — Translating...
- screen-29-translation-complete.png — Translation done
- screen-30-translation-error.png — Translation failed
- screen-31-translation-language-selection.png — Language picker
- screen-32-translation-glossary.png — Terminology sidebar
- screen-33-translation-history.png — Previous translations
- screen-34-translation-quality.png — Quality metrics
- screen-35-translation-export.png — Export options
- screen-36-translation-batch.png — Multiple documents
- screen-37-translation-diff.png — Side-by-side diff
- screen-38-translation-terminology.png — Term validation
- screen-39-translation-sharing.png — Share modal

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useTranslation.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/translation/
├── atoms/
│   ├── LanguageBadge.tsx
│   ├── ProgressIndicator.tsx
│   └── QualityScore.tsx
├── molecules/
│   ├── TranslationPanel.tsx
│   ├── LanguageSelector.tsx
│   └── GlossarySidebar.tsx
├── organisms/
│   ├── TranslationReady.tsx
│   ├── TranslationInProgress.tsx
│   ├── TranslationComplete.tsx
│   ├── TranslationError.tsx
│   ├── TranslationLanguageSelection.tsx
│   ├── TranslationGlossary.tsx
│   ├── TranslationHistory.tsx
│   ├── TranslationQuality.tsx
│   ├── TranslationExport.tsx
│   ├── TranslationBatch.tsx
│   ├── TranslationDiff.tsx
│   ├── TranslationTerminology.tsx
│   └── TranslationSharing.tsx
├── index.ts
└── __tests__/
    └── TranslationPanel.test.tsx
```

### Feature: Compare Flow

**Screens:** 40-54 (15 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Compare flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-40-compare-side-by-side.png — Two panels
- screen-41-compare-inline-diff.png — Merged view
- screen-42-compare-document-selector.png — Document picker
- screen-43-compare-change-summary.png — Change stats
- screen-44-compare-terminology.png — Term comparison
- screen-45-compare-export.png — Export options
- screen-46-compare-historical.png — Version history
- screen-47-compare-quality.png — Quality assessment
- screen-48-compare-collaboration.png — Comments
- screen-49-compare-merge.png — Merge view
- screen-50-compare-search.png — Search within
- screen-51-compare-shortcuts.png — Keyboard shortcuts
- screen-52-compare-dark-mode.png — Dark theme
- screen-53-compare-loading.png — Loading state
- screen-54-compare-error.png — Error state

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useCompare.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/compare/
├── atoms/
│   ├── DiffHighlight.tsx
│   ├── LineNumber.tsx
│   └── ComparisonBadge.tsx
├── molecules/
│   ├── DiffLine.tsx
│   ├── SideBySidePanel.tsx
│   └── InlineDiffView.tsx
├── organisms/
│   ├── CompareSideBySide.tsx
│   ├── CompareInlineDiff.tsx
│   ├── CompareDocumentSelector.tsx
│   ├── CompareChangeSummary.tsx
│   ├── CompareTerminology.tsx
│   ├── CompareExport.tsx
│   ├── CompareHistorical.tsx
│   ├── CompareQuality.tsx
│   ├── CompareCollaboration.tsx
│   ├── CompareMerge.tsx
│   ├── CompareSearch.tsx
│   ├── CompareShortcuts.tsx
│   ├── CompareDarkMode.tsx
│   ├── CompareLoading.tsx
│   └── CompareError.tsx
├── index.ts
└── __tests__/
    └── CompareSideBySide.test.tsx
```

### Feature: Chat Flow

**Screens:** 55-69 (15 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Chat flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-55-chat-logged-out.png — Public chat
- screen-56-chat-conversation.png — Active conversation
- screen-57-chat-loading.png — Thinking...
- screen-58-chat-error.png — Error occurred
- screen-59-chat-document-context.png — Document attached
- screen-60-chat-search-integration.png — Search results panel
- screen-61-chat-translation-integration.png — Translation panel
- screen-62-chat-history.png — Conversation list
- screen-63-chat-sharing.png — Share modal
- screen-64-chat-feedback.png — Thumbs up/down
- screen-65-chat-settings.png — Model settings
- screen-66-chat-typing.png — Typing indicator
- screen-67-chat-message-actions.png — Context menu
- screen-68-chat-attachments.png — File attachments
- screen-69-chat-dark-mode.png — Dark theme

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useChat.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/chat/
├── atoms/
│   ├── MessageBubble.tsx
│   ├── CitationLink.tsx
│   └── AttachmentIcon.tsx
├── molecules/
│   ├── ChatInput.tsx
│   ├── MessageList.tsx
│   └── CitationPanel.tsx
├── organisms/
│   ├── ChatEmpty.tsx
│   ├── ChatConversation.tsx
│   ├── ChatLoading.tsx
│   ├── ChatError.tsx
│   ├── ChatDocumentContext.tsx
│   ├── ChatSearchIntegration.tsx
│   ├── ChatTranslationIntegration.tsx
│   ├── ChatHistory.tsx
│   ├── ChatSharing.tsx
│   ├── ChatFeedback.tsx
│   ├── ChatSettings.tsx
│   ├── ChatTyping.tsx
│   ├── ChatMessageActions.tsx
│   ├── ChatAttachments.tsx
│   └── ChatDarkMode.tsx
├── index.ts
└── __tests__/
    └── ChatInput.test.tsx
```

### Feature: Exchange Flow

**Screens:** 70-71 (2 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Exchange flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-70-exchange-create-room.png — Room creation form
- screen-71-exchange-active-room.png — Active room

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useExchange.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/exchange/
├── atoms/
│   ├── ParticipantAvatar.tsx
│   └── RoomStatus.tsx
├── molecules/
│   ├── RoomForm.tsx
│   └── ParticipantList.tsx
├── organisms/
│   ├── ExchangeCreateRoom.tsx
│   └── ExchangeActiveRoom.tsx
├── index.ts
└── __tests__/
    └── ExchangeCreateRoom.test.tsx
```

### Feature: Matrix Login Modal

**Screens:** 72-81 (10 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Matrix Login Modal.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-72-matrix-login-default.png — Login form
- screen-73-matrix-login-error.png — Invalid credentials
- screen-74-matrix-login-loading.png — Authenticating...
- screen-75-matrix-register.png — Registration form
- screen-76-matrix-forgot-password.png — Password reset
- screen-77-matrix-reset-success.png — Check your email
- screen-78-matrix-sso.png — Google/Microsoft/GitHub
- screen-79-matrix-2fa.png — Two-factor auth
- screen-80-matrix-gdpr-consent.png — Privacy consent
- screen-81-matrix-login-mobile.png — Mobile layout

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useMatrixAuth.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/matrix-login/
├── atoms/
│   ├── ErrorCode.tsx
│   ├── SocialButton.tsx
│   └── ConsentCheckbox.tsx
├── molecules/
│   ├── LoginForm.tsx
│   ├── RegisterForm.tsx
│   └── TwoFactorForm.tsx
├── organisms/
│   ├── MatrixLoginDefault.tsx
│   ├── MatrixLoginError.tsx
│   ├── MatrixLoginLoading.tsx
│   ├── MatrixRegister.tsx
│   ├── MatrixForgotPassword.tsx
│   ├── MatrixResetSuccess.tsx
│   ├── MatrixSSO.tsx
│   ├── Matrix2FA.tsx
│   ├── MatrixGDPRConsent.tsx
│   └── MatrixLoginMobile.tsx
├── index.ts
└── __tests__/
    └── LoginForm.test.tsx
```

### Feature: Settings Flow

**Screens:** 82-91 (10 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for the Settings flow.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-82-settings-profile.png — Profile & security
- screen-83-settings-privacy.png — GDPR toggles
- screen-84-settings-notifications.png — Notification prefs
- screen-85-settings-appearance.png — Theme, font, language
- screen-86-settings-integrations.png — Connected services
- screen-87-settings-billing.png — Plan & usage
- screen-88-settings-team.png — Team management
- screen-89-settings-api.png — API keys & docs
- screen-90-settings-audit.png — Audit log
- screen-91-settings-success.png — Saved notification

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useSettings.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)

COMPONENT STRUCTURE:
src/components/settings/
├── atoms/
│   ├── ToggleSwitch.tsx
│   ├── SettingLabel.tsx
│   └── SuccessToast.tsx
├── molecules/
│   ├── SettingsForm.tsx
│   ├── ProfileForm.tsx
│   └── NotificationPrefs.tsx
├── organisms/
│   ├── SettingsProfile.tsx
│   ├── SettingsPrivacy.tsx
│   ├── SettingsNotifications.tsx
│   ├── SettingsAppearance.tsx
│   ├── SettingsIntegrations.tsx
│   ├── SettingsBilling.tsx
│   ├── SettingsTeam.tsx
│   ├── SettingsAPI.tsx
│   ├── SettingsAudit.tsx
│   └── SettingsSuccess.tsx
├── index.ts
└── __tests__/
    └── SettingsForm.test.tsx
```

### Feature: Mobile Screens

**Screens:** 92-105 (14 screens)

**Prompt for Gemini:**

```
Convert the Stitch design references into production React components for Mobile screens.

SCREENSHOTS (attach from docs/stitch-reference/generated/):
- screen-92-mobile-upload-idle.png — Mobile upload drop zone
- screen-93-mobile-upload-file-selected.png — Mobile file selected
- screen-94-mobile-upload-processing.png — Mobile processing
- screen-95-mobile-upload-success.png — Mobile success
- screen-96-mobile-upload-error.png — Mobile error
- screen-97-mobile-upload-dragover.png — Mobile dragover
- screen-98-mobile-upload-unsupported.png — Mobile unsupported
- screen-99-mobile-search-empty.png — Mobile search empty
- screen-100-mobile-search-results.png — Mobile search results
- screen-101-mobile-search-loading.png — Mobile search loading
- screen-102-mobile-search-no-results.png — Mobile no results
- screen-103-mobile-search-error.png — Mobile search error
- screen-104-mobile-exchange-create.png — Mobile exchange create
- screen-105-mobile-exchange-active.png — Mobile exchange active

ARCHITECTURE RULES:
1. Atomic Design: atoms → molecules → organisms
2. Type-safe: Readonly<T> props interfaces
3. Logic in src/hooks/useMobile*.ts
4. Static data in src/data/mockData.ts
5. Theme-mapped Tailwind (no hardcoded hex)
6. Mobile-first responsive design
7. Bottom navigation pattern

COMPONENT STRUCTURE:
src/components/mobile/
├── atoms/
│   ├── BottomNav.tsx
│   ├── MobileCard.tsx
│   └── MobileButton.tsx
├── molecules/
│   ├── MobileUploadForm.tsx
│   ├── MobileSearchBar.tsx
│   └── MobileExchangeForm.tsx
├── organisms/
│   ├── MobileUploadIdle.tsx
│   ├── MobileUploadFileSelected.tsx
│   ├── MobileUploadProcessing.tsx
│   ├── MobileUploadSuccess.tsx
│   ├── MobileUploadError.tsx
│   ├── MobileUploadDragover.tsx
│   ├── MobileUploadUnsupported.tsx
│   ├── MobileSearchEmpty.tsx
│   ├── MobileSearchResults.tsx
│   ├── MobileSearchLoading.tsx
│   ├── MobileSearchNoResults.tsx
│   ├── MobileSearchError.tsx
│   ├── MobileExchangeCreate.tsx
│   └── MobileExchangeActive.tsx
├── index.ts
└── __tests__/
    └── MobileUpload.test.tsx
```

---

## AST Validation Rules

Before marking any component as done, run validation:

```bash
node scripts/validate.js
```

### Checks Performed

| Category | Rule | Detection |
|----------|------|-----------|
| Color Tokens | No hardcoded hex values | AST string literal scanning |
| Type Safety | All props use `Readonly<T>` | AST declaration checks |
| Architecture | Logic in hooks, not components | AST function scanning |
| Cleanup | No placeholder names | AST identifier scanning |
| Dark Mode | `dark:` applied to color classes | Tailwind class scanning |

### Common Violations

```typescript
// ❌ VIOLATION: Hardcoded hex
className="bg-[#005796]"

// ✅ FIX: Use theme-mapped class
className="bg-primary"

// ❌ VIOLATION: No props interface
function MyComponent({ file, onSubmit }: any) {

// ✅ FIX: Add Readonly interface
interface MyComponentProps {
  readonly file: File;
  readonly onSubmit: (file: File) => void;
}
function MyComponent({ file, onSubmit }: MyComponentProps) {

// ❌ VIOLATION: Logic in component
function MyComponent() {
  const [isDragging, setIsDragging] = useState(false);
  const handleDrag = () => { /* 20 lines */ };
}

// ✅ FIX: Extract to hook
// src/hooks/useDragAndDrop.ts
export function useDragAndDrop() {
  const [isDragging, setIsDragging] = useState(false);
  const handleDrag = () => { /* 20 lines */ };
  return { isDragging, handleDrag };
}
```

---

## File References

| Purpose | Location | Notes |
|---------|----------|-------|
| Stitch project | `16375579204261083556` | Design source of truth |
| Screenshots | `docs/stitch-reference/generated/` | 105 PNG files |
| Design tokens | `frontend/src/app/tokens.css` | Stitch tokens merged |
| Existing components | `frontend/src/components/mobile/` | 10 mobile components (missing states) |
| Existing pages | `frontend/src/app/` | Compare, Upload, Search, etc. |
| Frontend conventions | `frontend/AGENTS.md` | Component organization, testing |

---

## Workflow

1. **Read Stitch Screenshots** — Open the PNG files listed in the prompt
2. **Map tokens** — Use the token mapping table above
3. **Generate components** — Follow Atomic Design hierarchy
4. **Extract logic** — Move to `src/hooks/`
5. **Extract data** — Move to `src/data/mockData.ts`
6. **Validate** — Run `node scripts/validate.js`
7. **Test** — Run `bun run test`
8. **Storybook** — Add stories for visual verification

---

## Quality Checklist

Before submitting any component:

- [ ] `Readonly<T>` props interface defined
- [ ] Logic extracted to `src/hooks/`
- [ ] Static data in `src/data/mockData.ts`
- [ ] No hardcoded hex values (AST validated)
- [ ] Theme-mapped Tailwind classes used
- [ ] WCAG 2.1 AA contrast ratios met
- [ ] Keyboard navigation works
- [ ] Screen reader labels present
- [ ] Unit tests pass
- [ ] Storybook story added
