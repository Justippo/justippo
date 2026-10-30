---
name: Wireframe / Design Task
about: Track a wireframe or design task with Figma link
title: "[WIREFRAME] "
labels: wireframe, design
assignees: ''
---

## Wireframe / Design Task

### Figma Link
<!-- REQUIRED: Paste the Figma frame link here (right-click frame → Copy link to selection) -->
<!-- Example: https://www.figma.com/make/y2NlJgKlsZtU5HbqL23gw3/EvidenceEU?node-id=123-456 -->

### Description
<!-- What does this wireframe show? What user flow does it represent? -->

### Requirements Coverage
<!-- Which functional requirements does this wireframe address? -->
- [ ] FR-XX: 

### Auth State
<!-- Is this wireframe for logged-in or logged-out users? -->
- [ ] Logged-out (public)
- [ ] Logged-in (authenticated)
- [ ] Both states

### Annotations
<!-- REQUIRED: Add annotations explaining behavior, interactions, and states -->
<!-- See example below -->

#### Example Annotations:
```
Frame: Upload / Idle
- Button "Upload Document" → opens file picker
- Accepted formats: PDF, DOCX, TXT
- Max file size: 10MB
- Error state: red border + toast message
- Loading state: spinner replaces button text
- Success state: redirects to /documents/{id}
```

### Acceptance Criteria
- [ ] Wireframe reviewed by team
- [ ] Annotations added
- [ ] Linked to GitHub issue
- [ ] Ready for implementation

### Labels
<!-- Add relevant labels -->
- `wireframe` (required)
- `phase-2` (if Phase 2)
