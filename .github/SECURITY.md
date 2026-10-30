# Security Policy

Thank you for helping us keep EvidenceEU secure!

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x (production) | Yes |

## Reporting Security Issues

**Please do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

**We do not accept AI-generated security reports.** AI vulnerability scanners frequently produce hallucinated findings that reference non-existent code or misapply CVE descriptions. These waste volunteer time and delay responses to genuine reports. Reports identified as AI-generated will be closed without review.

Instead, please send an email to **security@evidence-eu.dev** with:

- The type of issue (e.g., prompt injection, data exfiltration, XSS, SSRF)
- Full paths of source files related to the vulnerability
- The location of the affected code (tag, branch, commit, or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact assessment, including how an attacker might exploit the issue

We will acknowledge your report within **48 hours** and aim to provide a resolution timeline within **7 business days** for confirmed vulnerabilities.

## Scope

### In Scope

- Backend API (FastAPI on Cloudflare Python Worker)
- Proxy Worker (Cloudflare Worker)
- Frontend (Next.js on Cloudflare Pages)
- OCR pipeline (Mistral / Tesseract fallback)
- RAG pipeline (Hindsight / Vectorize)
- Translation service (m2m100 / Mistral Large via AI Gateway)
- GDPR consent middleware
- Prompt injection defenses (3-layer hardening)
- Authentication and session handling
- D1 database queries (SQL injection)

### Out of Scope

- Cloudflare infrastructure (Workers, D1, KV, Vectorize platform-level issues)
- Third-party LLM provider vulnerabilities (Mistral, Meta, Cloudflare AI)
- Social engineering attacks against team members
- Physical security

## Disclosure Policy

We follow coordinated disclosure:

1. **Report** the vulnerability privately via email.
2. **Acknowledge** receipt within 48 hours.
3. **Validate** and assess severity within 7 business days.
4. **Fix** critical vulnerabilities within 30 days; others within 90 days.
5. **Disclose** publicly after the fix is deployed, crediting the reporter (unless anonymity is requested).

We will not take legal action against researchers who follow this policy and act in good faith.

## Security Hardening

EvidenceEU already implements multiple defense layers:

- **REM-8 CI gate:** Blocks direct LLM API URLs outside `app/integrations/cloudflare/gateway.py` (enforced on every push)
- **33 prompt injection tests:** OWASP LLM01:2025 compliance (`backend/tests/security/`)
- **GDPRConsentMiddleware:** HTTP 451 on missing consent headers
- **Ephemeral processing:** Pyodide/WASM sandbox — no disk writes architecturally possible
- **AI Gateway proxy:** All LLM calls route through Cloudflare AI Gateway (never direct)

For the full threat model and defense architecture, see [docs/testing/ai-safety-posture.md](../docs/testing/ai-safety-posture.md).

## Contact

**Email:** security@evidence-eu.dev

*This is a placeholder. Replace with a dedicated security contact once available.*
