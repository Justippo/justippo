# Wireframe Annotations Guide

**For the Translation/UX lead:** How to add annotations to the EvidenceEU wireframes in Figma.

---

## What Are Annotations?

Annotations are **notes on the wireframe** that explain what each element does. Without them, a developer looks at a picture and guesses. With them, they know exactly what to build.

---

## What to Annotate

For each frame, add notes covering:

### 1. Behavior
- What happens when the user clicks/interacts with this element?
- Example: "Clicking 'Upload Document' opens file picker"

### 2. States
- What are the different visual states?
- Example: "Idle → Loading → Success → Error"
- Show: idle, hover, active, disabled, loading, error, empty, success

### 3. Auth Gating
- Is this element visible to logged-out users?
- Example: "This button only visible when logged in"

### 4. Error Handling
- What happens when something goes wrong?
- Example: "If file > 10MB, show toast: 'File too large'"

### 5. Navigation
- Where does this element take the user?
- Example: "Takes user to /documents/{id}"

### 6. Requirements Mapping
- Which functional requirement does this address?
- Example: "Maps to FR-07: Document Upload"

---

## Annotation Format

Use this template for each frame:

```
Frame: [Frame Name]
- [Element]: [Behavior]
- [Element]: [Behavior]
- State: [Idle] → [Loading] → [Success] → [Error]
- Auth: [Logged-in only / Logged-out only / Both]
- Error: [What happens on error]
- Navigation: [Where it goes]
- Maps to: FR-XX
```

---

## Example

```
Frame: Upload / Idle
- Button "Upload Document" → opens file picker
- Accepted formats: PDF, DOCX, TXT
- Max file size: 10MB
- Error state: red border + toast message
- Loading state: spinner replaces button text
- Success state: redirects to /documents/{id}
- Auth: Logged-in only
- Maps to: FR-07: Document Upload
```

---

## How to Add Annotations in Figma

1. Select the frame
2. Add a text layer below or beside the frame
3. Use the annotation format above
4. Use a consistent color (e.g., blue for annotations)
5. Link to the relevant GitHub issue

---

## Frames That Need Annotations

| Frame | Status | Auth | Maps to | Notes |
|-------|--------|------|---------|-------|
| 01 Current UI Reference | Not started | Both | — | Document current state before redesign |
| 02 Landing / Hero | Not started | Logged-out | FR-01 | Public-facing hero, trust logos, CTA |
| 03 Search / Empty | Not started | Both | FR-02 | Empty state with search bar |
| 04 Search / Results | Not started | Both | FR-02 | SSE streaming, source citations |
| 05 Upload / Idle | Not started | Logged-in | FR-07 | File picker, accepted formats |
| 06 Upload / Processing | Not started | Logged-in | FR-07 | Loading states, progress |
| 07 Viewer / Side-by-side | Not started | Logged-in | FR-08 | Bilingual view, EN/DE/FR |
| 08 Compare / Diff | Not started | Logged-in | FR-09 | LCS diff highlighting |
| 09 Exchange / Matrix | Not started | Logged-in | FR-10 | E2EE flow, Matrix protocol |
| 10 Chat Empty | Not started | Both | FR-14 | Chat-first interface, empty state |
| 11 Chat Response | Not started | Both | FR-14 | AI response rendering, citations |
| 12 Chat Upload | Not started | Logged-in | FR-14 | Upload from chat context |
| 13 Matrix Login Modal | Not started | Logged-out | FR-10 | Auth flow, Matrix registration |

---

## Detailed Annotation Templates

### 01 Current UI Reference
```
Frame: 01 Current UI Reference
- Purpose: Document the current state before redesign
- Auth: Both (logged-in and logged-out views)
- Maps to: — (baseline documentation)
```

### 02 Landing / Hero
```
Frame: 02 Landing / Hero
- Headline: "Multilingual Document Intelligence for Cross-Border Europe"
- Subheadline: [Your text]
- CTA Button 1: "Get Started" → /register
- CTA Button 2: "See Demo" → /demo
- Trust logos: EU institutions, law firms
- Auth: Logged-out only
- Maps to: FR-01: Platform Discovery
```

### 03 Search / Empty
```
Frame: 03 Search / Empty
- Search bar: Prominent, centered
- Language dropdown: EN/DE/FR selector
- Placeholder text: "Search documents in any language..."
- Empty state: "No results found" / "Start typing to search"
- Auth: Both
- Maps to: FR-02: Multilingual Search
```

### 04 Search / Results
```
Frame: 04 Search / Results
- Results list: Document cards with title, language, snippet
- SSE streaming: Real-time results as they arrive
- Source citations: Links to original documents
- Language badges: Show document language
- Auth: Both
- Maps to: FR-02: Multilingual Search
```

### 05 Upload / Idle
```
Frame: 05 Upload / Idle
- Button "Upload Document" → opens file picker
- Accepted formats: PDF, DOCX, TXT
- Max file size: 10MB
- Drag-and-drop zone: Dotted border
- Auth: Logged-in only
- Maps to: FR-07: Document Upload
```

### 06 Upload / Processing
```
Frame: 06 Upload / Processing
- Loading spinner: Replaces button text
- Progress bar: "Processing document..."
- Status messages: "OCR complete" / "Translating..."
- Auth: Logged-in only
- Maps to: FR-07: Document Upload
```

### 07 Viewer / Side-by-side
```
Frame: 07 Viewer / Side-by-side
- Left panel: Original document
- Right panel: Translated document
- Language toggle: EN/DE/FR
- Sync scrolling: Both panels scroll together
- Auth: Logged-in only
- Maps to: FR-08: Bilingual Viewer
```

### 08 Compare / Diff
```
Frame: 08 Compare / Diff
- Diff highlighting: LCS algorithm
- Color coding: Added (green) / Removed (red) / Changed (yellow)
- Mode toggle: Side-by-side vs inline
- Auth: Logged-in only
- Maps to: FR-09: Document Comparison
```

### 09 Exchange / Matrix
```
Frame: 09 Exchange / Matrix
- Recipient selector: Search users
- File attachment: Select translated documents
- E2EE indicator: Lock icon, "End-to-end encrypted"
- Send button: "Send Securely"
- Auth: Logged-in only
- Maps to: FR-10: Secure Exchange
```

### 10 Chat Empty
```
Frame: 10 Chat Empty
- Chat input: "Ask about your documents..."
- Suggested prompts: "Summarize this document" / "Compare these files"
- Auth: Both
- Maps to: FR-14: Chat Interface
```

### 11 Chat Response
```
Frame: 11 Chat Response
- AI response: Markdown-rendered answer
- Source citations: Clickable links to documents
- Copy button: Copy response to clipboard
- Auth: Both
- Maps to: FR-14: Chat Interface
```

### 12 Chat Upload
```
Frame: 12 Chat Upload
- Attachment button: Paperclip icon
- File preview: Thumbnail of uploaded document
- Drag-and-drop: Into chat area
- Auth: Logged-in only
- Maps to: FR-14: Chat Interface
```

### 13 Matrix Login Modal
```
Frame: 13 Matrix Login Modal
- Email input: "Email or username"
- Password input: "Password"
- Login button: "Sign In"
- Register link: "Create account"
- E2EE indicator: "End-to-end encrypted"
- Auth: Logged-out only
- Maps to: FR-10: Secure Exchange
```

---

## Tips

- **Be specific:** "Clicking X opens Y" not "Button works"
- **Cover all states:** Idle, hover, loading, error, empty, success
- **Link to requirements:** Map each frame to FR-XX
- **Note auth state:** Logged-in vs logged-out visibility
- **Include error messages:** Exact text the user sees
- **Use consistent color:** Blue for annotations in Figma
