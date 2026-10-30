# EvidenceEU Stitch Screen Generation Prompts

**Purpose:** Complete prompts for generating all 88 screens in Stitch web UI.
**Project:** EvidenceEU Enterprise Design System
**Design System:** Create this FIRST in Stitch before generating any screens.

---

## Design System (Create First)

### Colors

> **Token reconciliation (2026-07-14):** Primary is **`#005796`** (EvidenceEU's own blue — between EU #004494 and GOV.UK #1d70b8). All functional colors now use EU ECL values, not GOV.UK copies.

| Token | Hex | Description |
|-------|-----|-------------|
| Primary | #005796 | EvidenceEU brand blue |
| Primary Container | #1b5e9e | Darker EU blue (WCAG AA compliant) |
| On Primary | #ffffff | White text on primary |
| On Primary Container | #e9f1ff | Light blue text |
| Secondary | #5e5e5e | Gray |
| Secondary Container | #e1dfdf | Light gray |
| Tertiary | #824600 | Brown |
| Tertiary Container | #a55a00 | Lighter brown |
| Error | #DA2130 | EU ECL error red |
| Error Container | #ffdad6 | Light red |
| Warning | #8B4A0B | EU ECL warning orange (darkened for AA) |
| Success | #467A39 | EU ECL success green |
| Surface | #faf9f8 | Background |
| Surface Dim | #dadad9 | Dimmed background |
| Surface Container Low | #f4f3f2 | Card background |
| Surface Container | #efeeed | Elevated surface |
| Surface Container High | #e9e8e7 | Higher elevation |
| On Surface | #1a1c1c | Primary text |
| On Surface Variant | #414751 | Secondary text |
| Outline | #717782 | Borders |
| Outline Variant | #c1c7d2 | Light borders |
| Focus | #FFD617 | EU ECL yellow focus ring |

### Typography

| Token | Size | Weight | Use |
|-------|------|--------|-----|
| Headline XL | 36px/44px | 700 | Page titles |
| Headline LG | 24px/32px | 700 | Section headers |
| Headline MD | 19px/28px | 700 | Card titles |
| Body LG | 19px/28px | 400 | Body text |
| Body MD | 16px/24px | 400 | Default body |
| Label MD | 16px/24px | 700 | Buttons |
| Label SM | 14px/20px | 400 | Captions |
| Code | 14px/20px | 400 | Code blocks |

### Spacing

| Token | Value |
|-------|-------|
| unit | 4px |
| xs | 8px |
| sm | 12px |
| md | 16px |
| lg | 24px |
| xl | 32px |
| container-max | 1280px |

### Fonts

- **Headlines:** Public Sans
- **Body:** Public Sans
- **Code:** Courier Prime

---

## Prompt Template

Use this template for every screen generation:

```
Design a [SCREEN NAME] for EvidenceEU — a multilingual document intelligence platform for cross-border users in Europe.

Design System:
- Primary: #005796
- Error: #D4351C
- Warning: #F47738
- Success: #00703C
- Surface: #faf9f8
- On Surface: #1a1c1c
- Font: Public Sans

Layout:
[DESCRIBE LAYOUT]

Key Elements:
[LIST ELEMENTS]

State:
[DESCRIBE STATE]
```

---

## Desktop Screens (74 screens)

### Upload Flow (17 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 1 | Upload Idle | "Design an upload document page for EvidenceEU. Show a large dashed drop zone with 'Drag & drop your document here' text, a 'Browse files' button, and info badge showing 'PDF, DOCX, PNG · Max 15 MB'. Include the top navigation bar with EvidenceEU logo, Dashboard, Documents, Workflows, Analytics links. Include left sidebar with Home, Chat, Library, Cases, Settings navigation. State: idle, no file selected." |
| 2 | Upload Dragover | "Design an upload document page for EvidenceEU in dragover state. Show a highlighted blue drop zone with 'Drop your document here' text, dashed border turning solid blue. Include top navigation and left sidebar. State: user is dragging a file over the drop zone." |
| 3 | Upload File Selected | "Design an upload document page for EvidenceEU with file selected. Show a green confirmation card with file name, size, and 'Ready to upload' status. Include 'Upload for Analysis' primary button and 'Cancel' secondary button. Include top navigation and left sidebar. State: file selected, ready to upload." |
| 4 | Upload Uploading | "Design an upload document page for EvidenceEU during upload. Show an indeterminate progress bar with 'Uploading...' text, filename, and spinner. Include top navigation and left sidebar. State: upload in progress." |
| 5 | Upload Processing OCR | "Design an upload document page for EvidenceEU during OCR processing. Show a spinner with 'Extracting text...' message, estimated wait time '3-8s', and progress indicator. Include top navigation and left sidebar. State: OCR processing after upload." |
| 6 | Upload Complete | "Design an upload document page for EvidenceEU after successful upload. Show a success card with confidence badge '0.984', language chip 'EN', page count '5 pages', and preview text snippet. Include 'View Document' and 'Translate' action buttons. Include top navigation and left sidebar. State: upload complete, document processed." |
| 7 | Upload Error | "Design an upload document page for EvidenceEU with upload error. Show a red error card with error message 'File too large' and 'Retry' button. Include top navigation and left sidebar. State: upload failed." |
| 8 | Upload Idle (Audited) | "Design an upload document page for EvidenceEU with improved visual hierarchy. Show a large dashed drop zone with 'Drag & drop your document here' text, a 'Browse files' button, and info badge. Include top navigation and left sidebar. State: idle, audited version with better spacing." |
| 9 | Upload Idle (Audited v2) | "Design an upload document page for EvidenceEU with refined layout. Show a large dashed drop zone with 'Drag & drop your document here' text, a 'Browse files' button, and info badge. Include top navigation and left sidebar. State: idle, second audited version." |
| 10 | Upload Dragover (Audited) | "Design an upload document page for EvidenceEU in dragover state with improved styling. Show a highlighted drop zone with 'Drop your document here' text. Include top navigation and left sidebar. State: dragover, audited version." |
| 11 | Upload Dragover (Audited v2) | "Design an upload document page for EvidenceEU in dragover state with refined design. Show a highlighted drop zone with 'Drop your document here' text. Include top navigation and left sidebar. State: dragover, second audited version." |
| 12 | Upload Uploading (Audited) | "Design an upload document page for EvidenceEU during upload with improved progress indicator. Show progress bar with 'Uploading...' text. Include top navigation and left sidebar. State: uploading, audited version." |
| 13 | Upload Uploading (Audited v2) | "Design an upload document page for EvidenceEU during upload with refined design. Show progress bar with 'Uploading...' text. Include top navigation and left sidebar. State: uploading, second audited version." |
| 14 | Upload Processing OCR (Audited) | "Design an upload document page for EvidenceEU during OCR processing with improved spinner. Show spinner with 'Extracting text...' message. Include top navigation and left sidebar. State: OCR processing, audited version." |
| 15 | Upload Processing OCR (Audited v2) | "Design an upload document page for EvidenceEU during OCR processing with refined design. Show spinner with 'Extracting text...' message. Include top navigation and left sidebar. State: OCR processing, second audited version." |
| 16 | Upload Error (Audited) | "Design an upload document page for EvidenceEU with upload error and improved error card. Show red error card with error message and 'Retry' button. Include top navigation and left sidebar. State: upload error, audited version." |
| 17 | Upload Error (Audited v2) | "Design an upload document page for EvidenceEU with upload error and refined design. Show red error card with error message and 'Retry' button. Include top navigation and left sidebar. State: upload error, second audited version." |

### Search Flow (11 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 18 | Search Empty | "Design a search page for EvidenceEU with empty state. Show a large search bar with placeholder 'Search your documents...', suggestion chips below ('Recent searches', 'Popular queries'), and empty state message 'Start typing to search your legal corpus'. Include top navigation and left sidebar. State: no query entered." |
| 19 | Search Query Entered | "Design a search page for EvidenceEU with query entered. Show search bar with 'contract liability' query, loading spinner below, and 'Searching...' text. Include top navigation and left sidebar. State: query entered, search in progress." |
| 20 | Search Streaming First Result | "Design a search page for EvidenceEU with first result streaming in. Show search bar with query, first result card appearing with title, snippet, and citation badge. Include streaming indicator (animated dots). Include top navigation and left sidebar. State: first result streaming via SSE." |
| 21 | Search Results Complete | "Design a search page for EvidenceEU with complete results. Show search bar with query, 3-5 result cards with titles, snippets, citation badges, and relevance scores. Include top navigation and left sidebar. State: search complete, results displayed." |
| 22 | Search Error | "Design a search page for EvidenceEU with search error. Show search bar with query, red error banner 'Search failed. Please try again.' with retry button. Include top navigation and left sidebar. State: search error." |
| 23 | Search No Results | "Design a search page for EvidenceEU with no results. Show search bar with query, 'No results found' message, and suggestion chips ('Try different keywords', 'Check spelling'). Include top navigation and left sidebar. State: no results for query." |
| 24 | Search Query Entered (Audited) | "Design a search page for EvidenceEU with query entered and improved loading state. Show search bar with query, loading spinner, and 'Searching...' text. Include top navigation and left sidebar. State: query entered, audited version." |
| 25 | Search Results Complete (Audited) | "Design a search page for EvidenceEU with complete results and improved layout. Show search bar with query, result cards with better spacing. Include top navigation and left sidebar. State: search complete, audited version." |
| 26 | Search Streaming First Result (Audited) | "Design a search page for EvidenceEU with first result streaming and improved styling. Show search bar with query, first result card with streaming indicator. Include top navigation and left sidebar. State: streaming, audited version." |
| 27 | Search Streaming First Result (Audited v2) | "Design a search page for EvidenceEU with first result streaming and refined design. Show search bar with query, first result card with streaming indicator. Include top navigation and left sidebar. State: streaming, second audited version." |
| 28 | Search Results Complete (Audited v2) | "Design a search page for EvidenceEU with complete results and refined layout. Show search bar with query, result cards with improved design. Include top navigation and left sidebar. State: search complete, second audited version." |

### Translation Flow (13 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 29 | Translation Ready To Translate | "Design a translation page for EvidenceEU ready to translate. Show source document panel with text, language selector dropdown (EN/DE/FR), and 'Translate' button. Include top navigation and left sidebar. State: document loaded, ready to translate." |
| 30 | Translation Translating | "Design a translation page for EvidenceEU during translation. Show source panel with text, target panel with streaming translation, progress indicator, and 'Translating...' text. Include top navigation and left sidebar. State: translation in progress." |
| 31 | Translation Complete DE to EN | "Design a translation page for EvidenceEU with German to English translation complete. Show source panel with German text, target panel with English translation, confidence badge, and 'Copy' button. Include top navigation and left sidebar. State: translation complete." |
| 32 | Translation Complete EN to FR | "Design a translation page for EvidenceEU with English to French translation complete. Show source panel with English text, target panel with French translation, confidence badge, and 'Copy' button. Include top navigation and left sidebar. State: translation complete." |
| 33 | Translation Truncated Warning | "Design a translation page for EvidenceEU with truncation warning. Show source panel with long text, target panel with truncated translation, yellow warning banner 'Document truncated. First 2000 characters translated.' Include top navigation and left sidebar. State: document too long, truncated." |
| 34 | Translation Failed | "Design a translation page for EvidenceEU with translation failed. Show source panel with text, red error card 'Translation failed. Please try again.' with retry button. Include top navigation and left sidebar. State: translation error." |
| 35 | Translation Ready To Translate (Audited) | "Design a translation page for EvidenceEU ready to translate with improved layout. Show source panel, language selector, and 'Translate' button with better spacing. Include top navigation and left sidebar. State: ready to translate, audited version." |
| 36 | Translation Translating (Audited) | "Design a translation page for EvidenceEU during translation with improved progress indicator. Show source and target panels with streaming translation. Include top navigation and left sidebar. State: translating, audited version." |
| 37 | Translation Complete DE to EN (Audited) | "Design a translation page for EvidenceEU with German to English translation complete and improved layout. Show source and target panels with better spacing. Include top navigation and left sidebar. State: translation complete, audited version." |
| 38 | Translation Truncated Warning (Audited) | "Design a translation page for EvidenceEU with truncation warning and improved styling. Show source and target panels with warning banner. Include top navigation and left sidebar. State: truncated, audited version." |
| 39 | Translation Failed (Audited) | "Design a translation page for EvidenceEU with translation failed and improved error card. Show source panel with error card. Include top navigation and left sidebar. State: translation failed, audited version." |
| 40 | Translation Complete DE to EN (Audited v2) | "Design a translation page for EvidenceEU with German to English translation complete and refined design. Show source and target panels. Include top navigation and left sidebar. State: translation complete, second audited version." |
| 41 | Translation Complete EN to FR (Audited) | "Design a translation page for EvidenceEU with English to French translation complete and improved layout. Show source and target panels. Include top navigation and left sidebar. State: translation complete, audited version." |

### Compare Flow (15 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 42 | Compare Side By Side | "Design a comparison page for EvidenceEU with side-by-side view. Show two panels: original document on left, translated document on right. Include language labels (EN/DE), scroll sync indicator, and diff highlights. Include top navigation and left sidebar. State: side-by-side comparison." |
| 43 | Compare Inline Diff | "Design a comparison page for EvidenceEU with inline diff view. Show single panel with interleaved original and translated text, color-coded additions (green) and deletions (red). Include line numbers and diff stats. Include top navigation and left sidebar. State: inline diff comparison." |
| 44 | Compare Source Only | "Design a comparison page for EvidenceEU with source only view. Show single panel with original document text, no translations visible. Include language label (EN) and 'Show Translation' toggle. Include top navigation and left sidebar. State: source only view." |
| 45 | Compare Modified Block Expanded | "Design a comparison page for EvidenceEU with modified block expanded. Show single panel with collapsed/expanded sections, modified blocks highlighted in yellow. Include expand/collapse controls. Include top navigation and left sidebar. State: modified blocks expanded." |
| 46 | Compare Side By Side (Audited) | "Design a comparison page for EvidenceEU with side-by-side view and improved layout. Show two panels with better spacing. Include top navigation and left sidebar. State: side-by-side, audited version." |
| 47 | Compare Side By Side (Audited v2) | "Design a comparison page for EvidenceEU with side-by-side view and refined design. Show two panels. Include top navigation and left sidebar. State: side-by-side, second audited version." |
| 48 | Compare Side By Side (Audited v3) | "Design a comparison page for EvidenceEU with side-by-side view and further refined design. Show two panels. Include top navigation and left sidebar. State: side-by-side, third audited version." |
| 49 | Compare Side By Side (Audited v4) | "Design a comparison page for EvidenceEU with side-by-side view and final refined design. Show two panels. Include top navigation and left sidebar. State: side-by-side, fourth audited version." |
| 50 | Compare Inline Diff (Audited) | "Design a comparison page for EvidenceEU with inline diff view and improved styling. Show single panel with interleaved text. Include top navigation and left sidebar. State: inline diff, audited version." |
| 51 | Compare Inline Diff (Audited v2) | "Design a comparison page for EvidenceEU with inline diff view and refined design. Show single panel with interleaved text. Include top navigation and left sidebar. State: inline diff, second audited version." |
| 52 | Compare Source Only (Audited) | "Design a comparison page for EvidenceEU with source only view and improved layout. Show single panel with original text. Include top navigation and left sidebar. State: source only, audited version." |
| 53 | Compare Modified Block Expanded (Audited) | "Design a comparison page for EvidenceEU with modified block expanded and improved styling. Show single panel with highlighted blocks. Include top navigation and left sidebar. State: modified block, audited version." |
| 54 | Compare Side By Side (Mobile) | "Design a mobile comparison page for EvidenceEU with tabbed view. Show tabs: 'Original', 'Translated', 'Diff'. Include swipe gesture hint. State: mobile side-by-side comparison." |
| 55 | Compare Inline Diff (Mobile) | "Design a mobile comparison page for EvidenceEU with inline diff view. Show single panel with interleaved text. Include top navigation. State: mobile inline diff." |
| 56 | Compare Source Only (Mobile) | "Design a mobile comparison page for EvidenceEU with source only view. Show single panel with original text. Include top navigation. State: mobile source only." |

### Chat Flow (6 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 57 | Chat Empty Logged Out | "Design a chat page for EvidenceEU for logged-out users. Show centered chat interface with 'Ask a legal question' heading, search bar with placeholder 'What would you like to know?', and public corpus badge 'Powered by EUR-Lex'. Include top navigation with 'Login' button. State: empty chat, logged out." |
| 58 | Chat Empty Logged In | "Design a chat page for EvidenceEU for logged-in users. Show centered chat interface with 'Ask a legal question' heading, search bar with placeholder 'What would you like to know?', and personal corpus badge 'Your documents + EUR-Lex'. Include top navigation with user avatar. State: empty chat, logged in." |
| 59 | Chat With Response | "Design a chat page for EvidenceEU with a response. Show user message 'What are the requirements for cross-border data transfer?', AI response with cited answer, source references panel with document links, and confidence badge. Include top navigation. State: chat with response." |
| 60 | Chat Document Upload Inline | "Design a chat page for EvidenceEU with inline document upload. Show chat interface with attachment button, file preview card in message area, and upload progress indicator. Include top navigation. State: uploading document within chat." |
| 61 | Chat Data Components | "Design a chat page for EvidenceEU with data components. Show chat interface with embedded data cards: citation card with document reference, translation card with language pair, comparison card with diff preview. Include top navigation. State: chat with data components." |
| 62 | Chat (Mobile) | "Design a mobile chat page for EvidenceEU. Show chat interface with message bubbles, input bar at bottom with attachment button, and send button. Include bottom navigation. State: mobile chat view." |

### Exchange Flow (2 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 63 | Exchange Create Room | "Design an exchange page for EvidenceEU to create a room. Show form with room name input, participant list, 'Create Room' button, and room settings. Include top navigation and left sidebar. State: creating exchange room." |
| 64 | Exchange Send Document | "Design an exchange page for EvidenceEU to send a document. Show room interface with file upload area, document preview, recipient selector, and 'Send' button. Include top navigation and left sidebar. State: sending document in exchange." |

### Matrix Login Modal (7 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 65 | Matrix Login Default | "Design a Matrix login modal for EvidenceEU. Show modal with 'Sign in to EvidenceEU' heading, email/password inputs, 'Sign in' button, and 'Create account' link. Include GDPR consent checkbox. State: default login state." |
| 66 | Matrix Login Homeserver Entry | "Design a Matrix login modal for EvidenceEU with homeserver entry. Show modal with 'Enter your homeserver' input, 'Continue' button, and 'Use EvidenceEU account' option. State: homeserver entry." |
| 67 | Matrix Login EvidenceEU Account | "Design a Matrix login modal for EvidenceEU with self-hosted account. Show modal with 'Sign in with EvidenceEU' heading, email/password inputs, and 'Sign in' button. State: EvidenceEU account login." |
| 68 | Matrix Login GDPR Consent Missing | "Design a Matrix login modal for EvidenceEU with GDPR consent error. Show modal with red warning 'Please accept the GDPR consent checkbox' and highlighted checkbox. State: GDPR consent missing." |
| 69 | Matrix Login Redirect Back | "Design a Matrix login modal for EvidenceEU with redirect. Show modal with 'Redirecting you back...' message and spinner. State: redirecting after login." |
| 70 | Matrix Login Audited State | "Design a Matrix login modal for EvidenceEU with improved layout. Show modal with better spacing and visual hierarchy. State: login, audited version." |
| 71 | Matrix Login Audited State v2 | "Design a Matrix login modal for EvidenceEU with refined design. Show modal with polished styling. State: login, second audited version." |

### Settings Flow (10 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 72 | Settings Profile & Security | "Design a settings page for EvidenceEU with profile and security. Show form with user info fields, password change section, 2FA toggle, and 'Save' button. Include top navigation and left sidebar. State: profile and security settings." |
| 73 | Settings Compliance & Governance | "Design a settings page for EvidenceEU with compliance and governance. Show GDPR settings, data retention options, audit log access, and compliance badges. Include top navigation and left sidebar. State: compliance settings." |
| 74 | Settings Data Mapping | "Design a settings page for EvidenceEU with data mapping. Show document field mappings, translation memory settings, and glossary configuration. Include top navigation and left sidebar. State: data mapping settings." |
| 75 | Settings Accessibility & UI | "Design a settings page for EvidenceEU with accessibility and UI. Show theme toggle (light/dark), font size slider, high contrast option, and screen reader settings. Include top navigation and left sidebar. State: accessibility settings." |
| 76 | Settings Profile & Security (Audited) | "Design a settings page for EvidenceEU with profile and security and improved layout. Show form with better spacing. Include top navigation and left sidebar. State: profile settings, audited version." |
| 77 | Settings Profile & Security (Audited v2) | "Design a settings page for EvidenceEU with profile and security and refined design. Show form. Include top navigation and left sidebar. State: profile settings, second audited version." |
| 78 | Settings Compliance & Governance (Audited) | "Design a settings page for EvidenceEU with compliance and improved layout. Show GDPR settings. Include top navigation and left sidebar. State: compliance settings, audited version." |
| 79 | Settings Data Mapping (Audited) | "Design a settings page for EvidenceEU with data mapping and improved layout. Show field mappings. Include top navigation and left sidebar. State: data mapping, audited version." |
| 80 | Settings Accessibility & UI (Audited) | "Design a settings page for EvidenceEU with accessibility and improved layout. Show theme and font settings. Include top navigation and left sidebar. State: accessibility, audited version." |
| 81 | Settings Accessibility & UI (Audited v2) | "Design a settings page for EvidenceEU with accessibility and refined design. Show theme and font settings. Include top navigation and left sidebar. State: accessibility, second audited version." |

### Reference Screens (4 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 82 | Cover & Traceability | "Design a cover page for EvidenceEU project documentation. Show project title 'EvidenceEU', subtitle 'Multilingual Document Intelligence Platform', team members, repository links, and flow coverage map. State: project cover." |
| 83 | Current UI Reference | "Design a reference page showing EvidenceEU current UI. Show screenshots of implemented features: upload, search, translation, comparison. Include version numbers and status badges. State: UI reference." |
| 84 | Design Tokens | "Design a reference page showing EvidenceEU design tokens. Show color palette, typography scale, spacing units, and component catalog. Include hex values and usage examples. State: design tokens reference." |
| 85 | Core Components | "Design a reference page showing EvidenceEU core components. Show button variants, input fields, cards, badges, and navigation elements. Include states (default, hover, active, disabled). State: component catalog." |

---

## Mobile Screens (14 screens)

### Upload Mobile (2 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 86 | Mobile Upload Idle | "Design a mobile upload page for EvidenceEU. Show full-width drop zone with 'Drag & drop your document here' text, 'Browse files' button, and file type info. Include bottom navigation with Home, Search, Upload, Profile icons. State: mobile upload idle." |
| 87 | Mobile Upload Complete | "Design a mobile upload page for EvidenceEU after successful upload. Show success card with confidence badge, language chip, and 'View Document' button. Include bottom navigation. State: mobile upload complete." |

### Search Mobile (1 screen)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 88 | Mobile Search Results | "Design a mobile search page for EvidenceEU with results. Show search bar at top, result cards with titles and snippets, and pagination. Include bottom navigation. State: mobile search results." |

### Chat Mobile (2 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 89 | Mobile Chat Empty | "Design a mobile chat page for EvidenceEU with empty state. Show centered 'Ask a legal question' heading, search bar, and suggestion chips. Include bottom navigation. State: mobile chat empty." |
| 90 | Mobile Chat With Response | "Design a mobile chat page for EvidenceEU with response. Show user message, AI response with citations, and input bar at bottom. Include bottom navigation. State: mobile chat with response." |

### Compare Mobile (4 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 91 | Mobile Compare Tabs | "Design a mobile comparison page for EvidenceEU with tabs. Show tabs: 'Original', 'Translated', 'Diff'. Content area with document text. Include bottom navigation. State: mobile compare with tabs." |
| 92 | Mobile Compare Tabs (Audited) | "Design a mobile comparison page for EvidenceEU with tabs and improved styling. Show tabs with better spacing. Include bottom navigation. State: mobile compare, audited version." |
| 93 | Mobile Compare Tabs (Audited v2) | "Design a mobile comparison page for EvidenceEU with tabs and refined design. Show tabs. Include bottom navigation. State: mobile compare, second audited version." |
| 94 | Mobile Compare Tabs (Audited v3) | "Design a mobile comparison page for EvidenceEU with tabs and further refined design. Show tabs. Include bottom navigation. State: mobile compare, third audited version." |

### Translation Mobile (2 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 95 | Mobile Translation Viewer Tabs | "Design a mobile translation page for EvidenceEU with tabs. Show tabs: 'Source', 'Translation', 'Both'. Content area with text. Include bottom navigation. State: mobile translation with tabs." |
| 96 | Mobile Translation Viewer Tabs (Audited v2) | "Design a mobile translation page for EvidenceEU with tabs and refined design. Show tabs. Include bottom navigation. State: mobile translation, second audited version." |

### Matrix Login Mobile (3 screens)

| # | Screen Name | Prompt |
|---|-------------|--------|
| 97 | Mobile Matrix Login Modal | "Design a mobile Matrix login modal for EvidenceEU. Show full-screen modal with 'Sign in' heading, email/password inputs, 'Sign in' button, and GDPR checkbox. State: mobile login." |
| 98 | Mobile Matrix Login Modal (Audited) | "Design a mobile Matrix login modal for EvidenceEU with improved layout. Show full-screen modal with better spacing. State: mobile login, audited version." |
| 99 | Mobile Matrix Login Modal (Audited v2) | "Design a mobile Matrix login modal for EvidenceEU with refined design. Show full-screen modal. State: mobile login, second audited version." |

---

## Generation Workflow

### Step 1: Create Design System in Stitch

1. Open Stitch web UI
2. Create new project: "EvidenceEU Enterprise Design System"
3. Go to Design System settings
4. Add colors from the color table above
5. Add typography from the typography table above
6. Save design system

### Step 2: Generate Screens in Sessions

**Session 1: Upload Flow (7 screens)**
- Generate screens 1-7 (Upload Idle through Upload Error)
- Verify quality in web UI
- Take screenshots for reference

**Session 2: Upload Flow Audited (10 screens)**
- Generate screens 8-17 (Upload audited versions)
- Verify quality
- Compare with Session 1

**Session 3: Search Flow (11 screens)**
- Generate screens 18-28 (Search flow)
- Verify quality

**Session 4: Translation Flow (13 screens)**
- Generate screens 29-41 (Translation flow)
- Verify quality

**Session 5: Compare Flow (15 screens)**
- Generate screens 42-56 (Compare flow)
- Verify quality

**Session 6: Chat + Exchange + Matrix Login (15 screens)**
- Generate screens 57-71 (Chat, Exchange, Matrix Login)
- Verify quality

**Session 7: Settings + Reference (14 screens)**
- Generate screens 72-85 (Settings, Reference)
- Verify quality

**Session 8: Mobile Screens (14 screens)**
- Generate screens 86-99 (Mobile screens)
- Verify quality

### Step 3: Verify and Organize

After each session:
1. Verify all screens in web UI
2. Check for consistency
3. Organize canvas by feature
4. Take screenshots for reference

---

## Quality Checklist

After all screens generated:

- [ ] All 88 screens present
- [ ] Design system applied consistently
- [ ] No duplicate screens
- [ ] Canvas organized by feature
- [ ] Mobile screens below desktop counterparts
- [ ] All states represented (idle, loading, error, success)
- [ ] Auth vs. unauth states visible
- [ ] Traceability annotations present
