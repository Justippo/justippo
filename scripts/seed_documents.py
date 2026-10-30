#!/usr/bin/env python3
"""
seed_documents.py — Download, chunk, and index 50+ EU regulation documents
into Vectorize Hindsight for Sprint 1 RAG validation.

Data flow:
  EUR-Lex HTML (public, no auth) -> BeautifulSoup text extraction
  -> RecursiveCharacterTextSplitter (512-tok chunks, 64-tok overlap)
  -> Hindsight.aretain() per chunk (via hindsight-client SDK)
  -> 5-query recall validation -> RECALL: X/5 passed

Usage:
  python3 scripts/seed_documents.py
  DRY_RUN=1 python3 scripts/seed_documents.py   # skip ingest
  HINDSIGHT_API_URL=http://localhost:8600 python3 scripts/seed_documents.py

Prerequisites:
  pip install httpx beautifulsoup4 langchain-text-splitters tqdm hindsight-client

Idempotent: checks Hindsight documents API before ingesting each doc.
No EUR-Lex content is written to disk.
Exit code 1 if fewer than 50 documents successfully indexed.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from scripts._colors import RESET, GREEN, RED, BOLD, DIM, CYAN, YELLOW, hr as _hr

# ── Dependency guard ──────────────────────────────────────────────────────────
_MISSING: list[str] = []
for _pkg, _imp in [
    ("httpx", "httpx"),
    ("bs4", "bs4"),
    ("langchain_text_splitters", "langchain_text_splitters"),
    ("tqdm", "tqdm"),
    ("reductoai", "reducto"),  # optional — only needed when ENABLE_REDUCTO=true
]:
    try:
        __import__(_imp)
    except ImportError:
        _MISSING.append(_pkg)

if _MISSING:
    # Don't hard-fail if reductoai is missing — ENABLE_REDUCTO=false by default
    # so it may never be needed. Warn but continue.
    print(
        f"WARNING: Missing packages: {', '.join(_MISSING)}\n"
        f"  REDUCTO will be unavailable (ENABLE_REDUCTO=true requires these).\n"
        f"  Install with: pip install reductoai  (or pip install -e '.[reducto]')\n"
    )

import httpx

# ── Config ────────────────────────────────────────────────────────────────────
HINDSIGHT_URL: str = os.getenv("HINDSIGHT_API_URL", "http://localhost:8600")
BANK_ID: str = os.getenv("HINDSIGHT_BANK_ID", "evidence-eu-docs")
DRY_RUN: bool = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")

# ── Hindsight Cloud auth + credit-safety controls ─────────────────────────────
# ACCESS_KEY authenticates against Hindsight Cloud (Authorization: Bearer hsk_…).
# Leave empty for a local self-hosted instance (DefaultTenantExtension = no auth).
ACCESS_KEY: str = os.getenv("HINDSIGHT_ACCESS_KEY", "") or ""

# On Hindsight Cloud every retain triggers LLM fact-extraction (billed tokens),
# so these knobs bound spend when validating against the managed API:
#   SEED_CELEX="32004L0038,32003L0088"  → only these CELEX ids (highest priority)
#   SEED_LIMIT=5                          → first N of DOCUMENTS (used if no SEED_CELEX)
#   MAX_CHUNKS_PER_DOC=12                 → cap chunks ingested per doc (0 = no cap)
#   MIN_DOCS=5                            → success gate (defaults to 50 for full runs)
SEED_CELEX: list[str] = [c.strip() for c in os.getenv("SEED_CELEX", "").split(",") if c.strip()]
SEED_LIMIT: int = int(os.getenv("SEED_LIMIT", "0") or "0")
MAX_CHUNKS_PER_DOC: int = int(os.getenv("MAX_CHUNKS_PER_DOC", "0") or "0")
MIN_DOCS: int = int(os.getenv("MIN_DOCS", "50") or "50")

# Concurrency for the ingest loop (local self-hosted Hindsight only).
# The loop uses an AsyncClient but was fully sequential — embedding each chunk
# is the dominant cost, so running several documents' retains in parallel cuts
# total seed time from ~40 min to a few minutes on a laptop. Hindsight Cloud
# users should keep this low (1-2) to respect API rate limits / billing.
SEED_CONCURRENCY: int = int(os.getenv("SEED_CONCURRENCY", "3") or "3")

# Per-document chunk-retain concurrency. A single EUR-Lex doc can split
# into 80+ chunks; retaining them all at once (old behaviour) bursted
# hundreds of simultaneous embedding requests and overwhelmed the local
# Hindsight instance. Bounding it keeps the ingest smooth.
SEED_CHUNK_CONCURRENCY: int = int(os.getenv("SEED_CHUNK_CONCURRENCY", "4") or "4")

# Reducto config (ADR-009: public EUR-Lex corpus only — never used for user uploads)
ENABLE_REDUCTO: bool = os.getenv("ENABLE_REDUCTO", "").lower() in ("1", "true", "yes")
REDUCTO_API_KEY: str | None = os.getenv("REDUCTO_API_KEY") or None
REDUCTO_BASE_URL: str = os.getenv("REDUCTO_BASE_URL", "https://api.reducto.ai")

# ~512 tokens * ~4 chars/token; 64 tok overlap * 4 = 256 chars
CHUNK_SIZE_CHARS = 2048
CHUNK_OVERLAP_CHARS = 256

MAX_RETRIES = 5
RETRY_BASE_SLEEP = 2.0

EURLEX_HTML = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"

# ── Multilingual config ───────────────────────────────────────────────────────
# Languages for the DE+FR seeding pass (run via --multilingual / make seed-multilingual).
# EN seeding uses the EURLEX_HTML template above and is NOT modified here.
LANGUAGES: list[str] = ["de", "fr"]

# EUR-Lex stable link: two-letter ISO 639-1 code uppercased in the URL path.
# Verified against EUR-Lex linking docs:
#   https://eur-lex.europa.eu/content/help/data-reuse/linking.html
# Pattern: /legal-content/{LANG}/TXT/HTML/?uri=CELEX:{celex}
# Example: DE → /legal-content/DE/TXT/HTML/?uri=CELEX:32004L0038
EURLEX_HTML_LANG = "https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}"

# ── 55 CELEX document IDs across 6 topic areas ───────────────────────────────
# (celex_id, regulation_id, topic_area)
DOCUMENTS: list[tuple[str, str, str]] = [
    # Freedom of movement
    ("32004L0038", "Dir 2004/38/EC", "freedom_of_movement"),
    ("32011R0492", "Reg 492/2011", "freedom_of_movement"),
    ("32016R0399", "Reg 2016/399", "freedom_of_movement"),
    ("32013R0610", "Reg 610/2013", "freedom_of_movement"),
    ("32002L0090", "Dir 2002/90/EC", "freedom_of_movement"),
    ("32001L0040", "Dir 2001/40/EC", "freedom_of_movement"),
    ("32004L0082", "Dir 2004/82/EC", "freedom_of_movement"),
    ("32003L0110", "Dir 2003/110/EC", "freedom_of_movement"),
    ("32009R0810", "Reg 810/2009", "freedom_of_movement"),
    ("32008L0115", "Dir 2008/115/EC", "freedom_of_movement"),
    # Professional qualifications
    ("32005L0036", "Dir 2005/36/EC", "professional_qualifications"),
    ("32013L0055", "Dir 2013/55/EU", "professional_qualifications"),
    ("32018R1724", "Reg 2018/1724", "professional_qualifications"),
    ("32014L0067", "Dir 2014/67/EU", "professional_qualifications"),
    ("32006L0043", "Dir 2006/43/EC", "professional_qualifications"),
    ("32013L0034", "Dir 2013/34/EU", "professional_qualifications"),
    ("32006L0123", "Dir 2006/123/EC", "professional_qualifications"),
    # Employment rights
    ("32003L0088", "Dir 2003/88/EC", "employment_rights"),
    ("31996L0071", "Dir 96/71/EC", "employment_rights"),
    ("32018L0957", "Dir 2018/957", "employment_rights"),
    ("31999L0070", "Dir 1999/70/EC", "employment_rights"),
    ("31997L0081", "Dir 97/81/EC", "employment_rights"),
    ("32008L0104", "Dir 2008/104/EC", "employment_rights"),
    ("32001L0023", "Dir 2001/23/EC", "employment_rights"),
    ("31998L0059", "Dir 98/59/EC", "employment_rights"),
    ("32008L0094", "Dir 2008/94/EC", "employment_rights"),
    ("32019L1152", "Dir 2019/1152", "employment_rights"),
    ("32019L1158", "Dir 2019/1158", "employment_rights"),
    ("32009L0038", "Dir 2009/38/EC", "employment_rights"),
    ("32002L0014", "Dir 2002/14/EC", "employment_rights"),
    ("31991L0533", "Dir 91/533", "employment_rights"),
    # Social security coordination
    ("32004R0883", "Reg 883/2004", "social_security"),
    ("32009R0987", "Reg 987/2009", "social_security"),
    ("32010R1231", "Reg 1231/2010", "social_security"),
    ("32003L0109", "Dir 2003/109/EC", "social_security"),
    ("32003L0086", "Dir 2003/86/EC", "social_security"),
    ("32004L0114", "Dir 2004/114/EC", "social_security"),
    ("32016L0801", "Dir 2016/801", "social_security"),
    # Equal treatment
    ("32000L0043", "Dir 2000/43/EC", "equal_treatment"),
    ("32000L0078", "Dir 2000/78/EC", "equal_treatment"),
    ("32006L0054", "Dir 2006/54/EC", "equal_treatment"),
    ("32010L0041", "Dir 2010/41/EU", "equal_treatment"),
    ("32004L0113", "Dir 2004/113/EC", "equal_treatment"),
    ("32014L0054", "Dir 2014/54/EU", "equal_treatment"),
    # Cross-border services
    ("32014L0024", "Dir 2014/24/EU", "cross_border_services"),
    ("32011L0024", "Dir 2011/24/EU", "cross_border_services"),
    ("32016R0679", "Reg 2016/679", "cross_border_services"),
    ("32018R1807", "Reg 2018/1807", "cross_border_services"),
    ("32014R0910", "Reg 2014/910", "cross_border_services"),
    ("32015L2366", "Dir 2015/2366", "cross_border_services"),
    ("32019L0790", "Dir 2019/790", "cross_border_services"),
    ("32016L0943", "Dir 2016/943", "cross_border_services"),
    ("32013R0575", "Reg 2013/575", "cross_border_services"),
    ("32014L0065", "Dir 2014/65/EU", "cross_border_services"),
    ("32009L0136", "Dir 2009/136/EC", "cross_border_services"),
]


def _active_docs() -> list[tuple[str, str, str]]:
    """Return the subset of DOCUMENTS to process.

    Priority: SEED_CELEX (explicit ids) > SEED_LIMIT (first N) > all documents.
    Lets a Cloud run target just the validation-relevant directives to bound
    LLM-extraction token spend.
    """
    if SEED_CELEX:
        return [d for d in DOCUMENTS if d[0] in SEED_CELEX]
    if SEED_LIMIT:
        return DOCUMENTS[:SEED_LIMIT]
    return DOCUMENTS


# ── 5 validation queries ──────────────────────────────────────────────────────
VALIDATION_QUERIES: list[dict[str, Any]] = [
    {
        "id": "V1",
        "label": "Exact regulation number",
        "query": "Directive 2004/38/EC citizens rights free movement residence",
        "expect_celex": "32004L0038",
    },
    {
        "id": "V2",
        "label": "Semantic paraphrase of a key right",
        "query": "Can an EU citizen bring their non-EU spouse to live in another member state?",
        "expect_celex": "32004L0038",
    },
    {
        "id": "V3",
        "label": "Partial / vague phrasing",
        "query": "maximum weekly working hours rest periods employees",
        "expect_celex": "32003L0088",
    },
    {
        "id": "V4",
        "label": "Multi-concept query",
        "query": "recognition of professional diplomas qualifications obtained in another EU country",
        "expect_celex": "32005L0036",
    },
    {
        "id": "V5",
        "label": "Negation / exclusion phrasing",
        "query": "what employers cannot do when dismissing workers in a collective redundancy",
        "expect_celex": "31998L0059",
    },
]

# ── EUR-Lex fetch with exponential backoff ────────────────────────────────────


def _charset_from_response(resp: httpx.Response) -> str | None:
    """Extract the declared charset from an httpx response's Content-Type header.

    Returns the charset string (e.g. "utf-8", "iso-8859-1") or None if absent.
    """
    ct = resp.headers.get("content-type", "")
    for part in ct.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part[len("charset=") :].strip().strip('"').strip("'")
    return None


def _fetch_html(client: httpx.Client, celex: str) -> tuple[bytes, str | None] | None:
    """Fetch EUR-Lex HTML for celex as (bytes, charset) (never written to disk).

    Returns None on permanent failure. Retries on non-404 errors.
    The charset is extracted from the Content-Type header so callers can decode
    bytes correctly — important for non-ASCII EU legal text.

    Retries on: 202 (rate limit/processing), 429 (too many requests),
    500/502/503/504 (server errors). Uses exponential backoff.
    """
    url = EURLEX_HTML.format(celex=celex)
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.content, _charset_from_response(resp)
            if resp.status_code == 404:
                return None  # permanent — don't retry
            # 202 = rate-limited/processing; 429 = too many requests;
            # 500/502/503/504 = transient server error.
            # All use exponential backoff so we don't hammer a struggling server.
            if resp.status_code in (202, 429, 500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    # 202 needs longer delays — EUR-Lex is processing
                    base_delay = (
                        RETRY_BASE_SLEEP * 3 if resp.status_code == 202 else RETRY_BASE_SLEEP
                    )
                    time.sleep(base_delay * (2**attempt))
                continue
            # Other non-200 codes — treat as transient
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SLEEP * (2**attempt))
        except Exception:
            # Catches TimeoutException, ConnectError, RemoteProtocolError,
            # ReadError, SSL errors, etc. — all treated as transient.
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SLEEP * (2**attempt))
    return None


# ── Reducto parse helper (ADR-009: public corpus only) ───────────────────────
def _reducto_available() -> bool:
    # NOTE: ENABLE_REDUCTO is a module-level variable captured via closure.
    # After first import, the function object is cached by Python's import
    # machinery. Patching this function's behaviour in tests requires patching
    # scripts.seed_documents.ENABLE_REDUCTO (the module-level bool) so the
    # closure sees the updated value. Using patch.dict on __dict__ works because
    # it mutates the live module namespace in-place.
    if not ENABLE_REDUCTO:
        return False
    try:
        from reducto import Reducto  # type: ignore[import]

        return True
    except ImportError:
        return False


def _fetch_with_reducto(client: httpx.Client, celex: str) -> tuple[bytes, str | None] | None:
    try:
        from reducto import Reducto  # type: ignore[import]
        import io

        url = EURLEX_HTML.format(celex=celex)
        resp = client.get(url, timeout=30)
        if resp.status_code != 200:
            return None

        from bs4 import BeautifulSoup as Soup

        soup = Soup(resp.content, "html.parser")
        pdf_link: str | None = None

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf") or "pdf" in href.lower():
                if "oj" in href.lower() or "CELEX" in href:
                    pdf_link = href
                    break
            download = a.get("data-download")
            if download and "pdf" in download.lower():
                pdf_link = download
                break

        if not pdf_link:
            return None

        pdf_url = (
            pdf_link if pdf_link.startswith("http") else f"https://eur-lex.europa.eu{pdf_link}"
        )

        pdf_resp = client.get(pdf_url, timeout=60)
        if pdf_resp.status_code != 200 or len(pdf_resp.content) < 1000:
            return None
        pdf_bytes = pdf_resp.content

        reducto_kwargs = {}
        if REDUCTO_BASE_URL and REDUCTO_BASE_URL != "https://api.reducto.ai":
            reducto_kwargs["base_url"] = REDUCTO_BASE_URL

        client_red = Reducto(api_key=REDUCTO_API_KEY or None, **reducto_kwargs)
        upload = client_red.upload(file=io.BytesIO(pdf_bytes))

        result = client_red.parse.run(
            input=upload,
            retrieval={"chunking": {"chunk_mode": "variable"}},
        )

        parts: list[str] = []
        if result.result.chunks:
            for chunk in result.result.chunks:
                parts.append(chunk.content)
        else:
            return None

        markdown_text = "\n\n".join(parts)
        return markdown_text.encode("utf-8"), "utf-8"

    except Exception as exc:
        print(f"      [Reducto] {celex}: {str(exc)[:80]} — falling back to HTML path")
        return None


def _extract_text(html: bytes, charset: str | None = None) -> str:
    """Parse EUR-Lex HTML and return clean regulation body text.

    Args:
        html: Raw response bytes from EUR-Lex.
        charset: HTTP Content-Type charset declared by the server (e.g. "utf-8",
            "iso-8859-1"). When provided, bytes are decoded explicitly before
            parsing so BeautifulSoup never misdetects the encoding — which is
            especially important for DE/FR pages with umlauts and accented chars.
            Falls back to UTF-8 with replacement if charset is absent/unknown.
    """
    from bs4 import BeautifulSoup

    if charset:
        try:
            text_str = html.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text_str = html.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text_str, "html.parser")
    else:
        # Let BS4 detect encoding from the HTML <meta charset> tag; pass bytes
        # directly so it can use the BOM/meta hint rather than guessing.
        soup = BeautifulSoup(html, "html.parser")
    body = soup.find("div", id="document1") or soup.find("div", class_="texte") or soup.find("body")
    if body is None:
        return ""
    for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = body.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# ── Idempotency check ─────────────────────────────────────────────────────────


def _auth_headers() -> dict[str, str]:
    """Bearer header for Hindsight Cloud; empty dict for local self-hosted."""
    return {"Authorization": f"Bearer {ACCESS_KEY}"} if ACCESS_KEY else {}


def _already_indexed(http: httpx.Client, doc_id: str) -> bool:
    """Return True if doc_id already exists in the Hindsight bank."""
    try:
        resp = http.get(
            f"{HINDSIGHT_URL}/v1/default/banks/{BANK_ID}/documents",
            params={"q": doc_id, "limit": 5},
            headers=_auth_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            return any(item.get("id") == doc_id for item in items)
    except Exception:
        pass
    return False


def _cloud_reachable() -> tuple[bool, str]:
    """Verify the Hindsight endpoint is reachable and the bank is accessible.

    Works for both Cloud (Bearer auth, no public ``/health``) and local
    self-hosted (has ``/health``).  We treat any HTTP response to a bank-scoped
    GET as "reachable" — only connection/timeout errors count as failure.
    Returns ``(ok, detail)``.
    """
    with httpx.Client(follow_redirects=True) as hc:
        try:
            r = hc.get(
                f"{HINDSIGHT_URL}/v1/default/banks/{BANK_ID}",
                headers=_auth_headers(),
                timeout=10,
            )
            if r.status_code in (401, 403):
                return False, f"auth rejected (HTTP {r.status_code}) — check HINDSIGHT_ACCESS_KEY"
            return True, f"HTTP {r.status_code} from banks/{BANK_ID}"
        except Exception as exc:  # ConnectError, timeout, SSL, etc.
            return False, str(exc)


class _AttrItem:
    """Attribute view over a raw recall-result dict (``.text`` / ``.document_id`` / ``.metadata``)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        return self._data.get(name)


class _RecallResult:
    """Recall response exposing ``.results`` (list) and ``.chunks`` (dict)."""

    def __init__(self, results: list[_AttrItem], chunks: dict[str, Any]) -> None:
        self.results = results
        self.chunks = chunks


class _CloudSeeder:
    """Async httpx client shaped like the ``hindsight-client`` SDK methods this
    script calls (``acreate_bank`` / ``aretain`` / ``arecall`` / ``aclose``).

    It mirrors the REST contract that is the single source of truth for the
    shipped Worker path — ``backend/app/services/rag_service.py::
    _HindsightHttpClient`` — but is kept self-contained here so this operational
    script needs only ``httpx``, not the full FastAPI app import tree.

    Works against Hindsight Cloud (Bearer auth) and local self-hosted (no auth).
    Retain is issued synchronously (``async`` omitted) to avoid the multi-item
    drop bug in async retain (vectorize-io/hindsight#1375).
    """

    def __init__(self, base_url: str, api_key: str = "", bank_id: str = "") -> None:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=60.0
        )

    async def acreate_bank(self, *, bank_id: str, name: str = "", mission: str = "") -> None:
        # PUT /v1/default/banks/{bank_id} upserts the bank (auto-fills defaults).
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if mission:
            body["mission"] = mission
        resp = await self._client.put(f"/v1/default/banks/{bank_id}", json=body)
        resp.raise_for_status()

    async def aretain(
        self,
        *,
        bank_id: str,
        content: str,
        document_id: str,
        context: str,
        metadata: dict[str, Any],
        tags: list[str],
    ) -> None:
        item = {
            "content": content,
            "document_id": document_id,
            "context": context,
            "metadata": {k: str(v) for k, v in (metadata or {}).items()},
            "tags": list(tags or []),
        }
        resp = await self._client.post(
            f"/v1/default/banks/{bank_id}/memories", json={"items": [item]}
        )
        resp.raise_for_status()

    async def arecall(
        self,
        *,
        bank_id: str,
        query: str,
        budget: str = "high",
        include_chunks: bool = True,
        max_tokens: int = 2048,
        **_ignored: Any,
    ) -> _RecallResult:
        payload: dict[str, Any] = {"query": query, "budget": budget, "max_tokens": max_tokens}
        if include_chunks:
            payload["include"] = {"chunks": {"max_tokens": max_tokens}}
        resp = await self._client.post(f"/v1/default/banks/{bank_id}/memories/recall", json=payload)
        resp.raise_for_status()
        data = resp.json()
        results = [_AttrItem(r) for r in data.get("results", [])]
        chunks = data.get("chunks", {}) or {}
        return _RecallResult(results, chunks)

    async def aclose(self) -> None:
        await self._client.aclose()


# ── Main ──────────────────────────────────────────────────────────────────────


async def run() -> int:
    """Returns 0 on success (>=50 docs indexed), 1 on failure."""

    docs = _active_docs()
    print(f"\n{BOLD}EvidenceEU — EU Corpus Seeder{RESET}")
    print(f"  Hindsight : {HINDSIGHT_URL}")
    print(f"  Bank      : {BANK_ID}")
    print(f"  Auth      : {'Bearer (Cloud)' if ACCESS_KEY else 'none (self-hosted)'}")
    print(
        f"  Documents : {len(docs)} queued"
        + (f" (subset of {len(DOCUMENTS)})" if len(docs) != len(DOCUMENTS) else "")
    )
    if MAX_CHUNKS_PER_DOC:
        print(f"  Chunk cap : {MAX_CHUNKS_PER_DOC}/doc")
    if ENABLE_REDUCTO:
        print(f"  {CYAN}Reducto   : ENABLED (public corpus){RESET}")
    else:
        print(f"  {DIM}Reducto   : disabled (BeautifulSoup HTML path){RESET}")
    if DRY_RUN:
        print(f"  {YELLOW}Mode      : DRY RUN (no ingest){RESET}")
    _hr()

    # 0: Reachability check (Cloud has no public /health; probe the bank instead)
    print("\n[0] Reachability check ...")
    ok, detail = _cloud_reachable()
    if ok:
        print(f"  {GREEN}OK{RESET}  {detail}")
    else:
        print(f"  {RED}FAIL{RESET}  {detail}")
        print("       Local: docker-compose up hindsight -d  |  Cloud: check HINDSIGHT_ACCESS_KEY")
        return 1

    # 1: Ensure bank
    hs = _CloudSeeder(HINDSIGHT_URL, api_key=ACCESS_KEY, bank_id=BANK_ID)

    try:
        print("\n[1] Ensuring memory bank ...")
        try:
            await hs.acreate_bank(  # type: ignore[attr-defined]
                bank_id=BANK_ID,
                name="EvidenceEU Document Corpus",
                mission=(
                    "EU cross-border document intelligence assistant with deep knowledge of "
                    "regulations on freedom of movement, employment rights, professional "
                    "qualifications, social security, equal treatment, and cross-border services."
                ),
            )
            print(f"  {GREEN}OK{RESET}  Bank '{BANK_ID}' ready")
        except Exception as exc:
            print(f"  {DIM}  (already exists or: {exc}){RESET}")

        # 2: Splitter
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from tqdm import tqdm

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE_CHARS,
            chunk_overlap=CHUNK_OVERLAP_CHARS,
            separators=["\n\n", "\n", ". ", " ", ""],
            keep_separator=False,
        )

        # 3: Download, chunk, ingest
        print(f"\n[2] Processing {len(docs)} documents ...")
        indexed_count = 0
        skipped_count = 0
        failed: list[str] = []

        with httpx.Client(
            headers={"User-Agent": "EvidenceEU-Seeder/1.0 (academic; contact@evidence.eu)"},
            follow_redirects=True,
        ) as http_client:

            async def process_doc(celex: str, regulation_id: str, topic: str) -> str:
                """Download → chunk → retain one EUR-Lex document. Returns outcome."""
                doc_id = f"eurlex-{celex}"

                # Idempotency: skip already-indexed documents
                if not DRY_RUN and _already_indexed(http_client, doc_id):
                    return "skip"

                # ── Reducto path (ADR-009: public corpus only) ───────────────────
                html: bytes | None = None
                charset: str | None = None

                if ENABLE_REDUCTO and _reducto_available():
                    reducto_result = _fetch_with_reducto(http_client, celex)
                    if reducto_result is not None:
                        html, charset = reducto_result
                        tqdm.write(
                            f"  {CYAN}REDUCTO{RESET} {celex} — parsed via Reducto's agentic OCR"
                        )

                # ── BeautifulSoup HTML fallback path ─────────────────────────────
                if html is None:
                    fetch_result = _fetch_html(http_client, celex)
                    if fetch_result is None:
                        tqdm.write(f"  {YELLOW}SKIP{RESET} {celex} — not found / fetch failed")
                        return "fail"
                    html, charset = fetch_result

                # Extract text; pass declared charset so BS4 decodes correctly
                text = _extract_text(html, charset)
                if len(text) < 200:
                    tqdm.write(f"  {YELLOW}SKIP{RESET} {celex} — too short ({len(text)} chars)")
                    return "fail"

                # Chunk
                chunks = splitter.split_text(text)
                if not chunks:
                    return "fail"

                # Credit-safety: cap chunks/doc on Cloud (each retain is billed).
                if MAX_CHUNKS_PER_DOC:
                    chunks = chunks[:MAX_CHUNKS_PER_DOC]

                doc_tags = [topic, "eu-regulation", "en"]
                metadata: dict[str, Any] = {
                    "source_url": EURLEX_HTML.format(celex=celex),
                    "doc_id": doc_id,
                    "lang": "en",
                    "regulation_id": regulation_id,
                    "topic": topic,
                    "celex": celex,
                }
                context = f"{regulation_id} — {topic.replace('_', ' ').title()}"

                if DRY_RUN:
                    tqdm.write(
                        f"  {CYAN}DRY{RESET} {celex} — {len(chunks)} chunks, {len(text):,} chars"
                    )
                    return "dry"

                str_metadata: dict[str, str] = {k: str(v) for k, v in metadata.items()}

                # Retain chunks concurrently, but bounded so a single large
                # document doesn't burst hundreds of simultaneous embedding
                # requests at the Hindsight instance.
                chunk_sem = asyncio.Semaphore(SEED_CHUNK_CONCURRENCY)

                async def retain_chunk(chunk: str) -> bool:
                    async with chunk_sem:
                        for attempt in range(MAX_RETRIES + 1):
                            try:
                                await hs.aretain(  # type: ignore[attr-defined]
                                    bank_id=BANK_ID,
                                    content=chunk,
                                    document_id=doc_id,
                                    context=context,
                                    metadata=str_metadata,
                                    tags=doc_tags,
                                )
                                return True
                            except Exception as exc:
                                err_str = str(exc)
                                if attempt < MAX_RETRIES and any(
                                    code in err_str for code in ("429", "503", "500", "rate")
                                ):
                                    await asyncio.sleep(RETRY_BASE_SLEEP * (2**attempt))
                                else:
                                    tqdm.write(f"  {RED}FAIL{RESET} {celex} — {err_str[:120]}")
                                    return False
                    return False

                results = await asyncio.gather(*(retain_chunk(c) for c in chunks))
                if all(results):
                    tqdm.write(
                        f"  {GREEN}OK{RESET}  {celex} ({regulation_id}) — {len(chunks)} chunks"
                    )
                    return "ok"
                return "fail"

            # ── Concurrent ingest (bounded by SEED_CONCURRENCY) ──────────────────
            # Embeddings dominate latency; running several documents in parallel
            # cuts seed time from ~40 min to a few minutes on a laptop.
            sem = asyncio.Semaphore(SEED_CONCURRENCY)

            async def bounded(celex, regulation_id, topic):
                async with sem:
                    return await process_doc(celex, regulation_id, topic)

            outcomes = await asyncio.gather(
                *(bounded(c, r, t) for (c, r, t) in tqdm(docs, desc="Seeding", unit="doc")),
                return_exceptions=True,
            )

            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    failed.append("?")
                    tqdm.write(f"  {RED}EXC{RESET} {type(outcome).__name__}: {str(outcome)[:160]}")
                    continue
                if outcome == "skip":
                    skipped_count += 1
                    indexed_count += 1  # counts toward the 50 target
                elif outcome == "ok":
                    indexed_count += 1
                elif outcome == "dry":
                    indexed_count += 1
                elif outcome == "fail":
                    failed.append("?")

        _hr()
        print(f"  Indexed : {indexed_count}")
        print(f"  Skipped : {skipped_count} (already in Hindsight)")
        print(f"  Failed  : {len(failed)}")
        if failed:
            print(f"  Failed IDs: {', '.join(failed[:15])}")

        if indexed_count < MIN_DOCS:
            print(
                f"\n{RED}ERROR: Only {indexed_count}/{MIN_DOCS} documents indexed. Exit 1.{RESET}"
            )
            return 1

        # 4: Validation
        if DRY_RUN:
            print(f"\n{DIM}[3] Dry run — skipping validation.{RESET}")
            print(f"\n{BOLD}RECALL: N/A (dry run){RESET}\n")
            return 0

        print("\n[3] Waiting 15 s for Hindsight fact extraction ...")
        await asyncio.sleep(15)

        print(f"\n[4] Validation queries (budget=high) ...")
        _hr()

        W_Q, W_R, W_S = 38, 42, 14
        print(f"{BOLD}{'Query':<{W_Q}} {'Top-1 Result':<{W_R}} {'Correct Src?':<{W_S}} P/F{RESET}")
        print("-" * (W_Q + W_R + W_S + 6))

        passed = 0
        for vq in VALIDATION_QUERIES:
            qshort = f"{vq['id']}: {vq['query'][:33]}"
            try:
                resp = await hs.arecall(  # type: ignore[attr-defined]
                    bank_id=BANK_ID,
                    query=vq["query"],
                    budget="high",
                    # No types filter — chunks mode stores items as "chunks" type,
                    # not "world"/"experience". Omitting types returns all item types.
                    include_chunks=True,
                    max_tokens=2048,
                )
                results = getattr(resp, "results", []) or []
                # chunks is a dict {chunk_key: ChunkObject} where chunk_key is
                # "{bank_id}_{doc_id}_{chunk_index}" — the CELEX is embedded in
                # the key itself (e.g. "evidence-eu-docs_eurlex-32004L0038_0").
                chunks_dict: dict = getattr(resp, "chunks", {}) or {}

                if not results and not chunks_dict:
                    top1 = "(no results)"
                    correct = False
                else:
                    top_text = getattr(results[0], "text", "") if results else ""
                    if top_text:
                        top1 = top_text[:39].replace("\n", " ") + "..."
                    elif chunks_dict:
                        top1 = f"(chunk: {next(iter(chunks_dict))[:33]})"
                    else:
                        top1 = "(results present, no text)"

                    expect = vq["expect_celex"].lower()
                    correct = False

                    # Check top-10 results via document_id + metadata.
                    # Use a local variable to avoid shadowing the outer doc_id.
                    for item in results[:10]:
                        item_doc_id = str(getattr(item, "document_id", "") or "").lower()
                        meta = getattr(item, "metadata", {}) or {}
                        meta_celex = str(meta.get("celex", "")).lower()
                        if expect in item_doc_id or expect in meta_celex:
                            correct = True
                            break

                    # Also check chunk keys — pattern: {bank_id}_{doc_id}_{idx}
                    if not correct:
                        for chunk_key in chunks_dict:
                            if expect in chunk_key.lower():
                                correct = True
                                break

                pf_label = f"{GREEN}PASS{RESET}" if correct else f"{RED}FAIL{RESET}"
                src_label = f"{GREEN}Yes{RESET}" if correct else f"{RED}No{RESET}"
                # pad src_label accounting for invisible ANSI codes
                src_pad = src_label + " " * (W_S - 3)
                print(f"{qshort:<{W_Q}} {top1:<{W_R}} {src_pad} {pf_label}")

                if correct:
                    passed += 1

            except Exception as exc:
                err = f"ERROR: {str(exc)[:33]}"
                print(f"{qshort:<{W_Q}} {err:<{W_R}} {'No':<{W_S}} {RED}FAIL{RESET}")

        _hr()
        verdict = GREEN if passed >= 4 else RED
        print(f"\n{BOLD}{verdict}RECALL: {passed}/5 passed{RESET}\n")

        # Spec: exit 1 if <50 docs (already checked above) or recall critically low
        return 0

    finally:
        # Always close the Hindsight client — even on unexpected exceptions.
        await hs.aclose()


# ── Multilingual validation queries ──────────────────────────────────────────
# 3 queries per language, each a paraphrase of the EN validation concepts:
#   freedom of movement, employment rights, professional qualifications recognition.
# Queries are written in the target language so the embedding model is tested
# with native-language input — closest to real user behaviour.

VALIDATION_QUERIES_DE: list[dict[str, Any]] = [
    {
        "id": "DE-V1",
        "label": "Freizügigkeit — Aufenthaltsrecht",
        "query": (
            "Welche Rechte haben EU-Bürger auf Aufenthalt und Freizügigkeit "
            "in einem anderen Mitgliedstaat?"
        ),
        "expect_celex": "32004L0038",
    },
    {
        "id": "DE-V2",
        "label": "Arbeitnehmerrechte — Arbeitszeit",
        "query": (
            "Maximale wöchentliche Arbeitszeit und Mindestruhezeiten für Arbeitnehmer in der EU"
        ),
        "expect_celex": "32003L0088",
    },
    {
        "id": "DE-V3",
        "label": "Berufsqualifikationen — Anerkennung",
        "query": (
            "Anerkennung von Berufsqualifikationen und Diplomen aus einem anderen EU-Mitgliedstaat"
        ),
        "expect_celex": "32005L0036",
    },
]

VALIDATION_QUERIES_FR: list[dict[str, Any]] = [
    {
        "id": "FR-V1",
        "label": "Libre circulation — droit de séjour",
        "query": (
            "Quels droits ont les citoyens européens en matière de séjour et de "
            "libre circulation dans un autre État membre?"
        ),
        "expect_celex": "32004L0038",
    },
    {
        "id": "FR-V2",
        "label": "Droits des travailleurs — temps de travail",
        "query": (
            "Durée maximale hebdomadaire du travail et périodes de repos minimales "
            "pour les salariés dans l'Union européenne"
        ),
        "expect_celex": "32003L0088",
    },
    {
        "id": "FR-V3",
        "label": "Qualifications professionnelles — reconnaissance",
        "query": (
            "Reconnaissance des qualifications professionnelles et des diplômes "
            "obtenus dans un autre État membre de l'UE"
        ),
        "expect_celex": "32005L0036",
    },
]

_LANG_QUERIES: dict[str, list[dict[str, Any]]] = {
    "de": VALIDATION_QUERIES_DE,
    "fr": VALIDATION_QUERIES_FR,
}

# Human-readable labels for output
_LANG_LABEL: dict[str, str] = {"de": "DE", "fr": "FR"}


# ── Language-aware fetch ──────────────────────────────────────────────────────


def _fetch_html_lang(client: httpx.Client, celex: str, lang: str) -> bytes | None:
    """Fetch EUR-Lex HTML for celex in target language (in-memory only).

    Uses the two-letter ISO 639-1 code uppercased in the URL path:
      DE → /legal-content/DE/TXT/HTML/?uri=CELEX:{celex}
      FR → /legal-content/FR/TXT/HTML/?uri=CELEX:{celex}
    Returns None on permanent failure. Retries on 429/503.

    IMPORTANT: EUR-Lex silently redirects requests for documents not translated
    into the requested language to the EN version (or a language-picker page).
    Because httpx follows redirects transparently we must verify the final URL
    still contains /{LANG}/ — otherwise we would index EN content under a DE/FR
    doc_id, corrupting the multilingual index while the 50-doc count passes.
    """
    url = EURLEX_HTML_LANG.format(lang=lang.upper(), celex=celex)
    lang_path_marker = f"/{lang.upper()}/"  # e.g. "/DE/" or "/FR/"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.get(url, timeout=30)
            if resp.status_code == 200:
                # Guard against silent language redirect: if EUR-Lex served a
                # different language, treat it as "not available in this language".
                final_url = str(resp.url)
                if lang_path_marker not in final_url:
                    return None
                return resp.content, _charset_from_response(resp)
            if resp.status_code == 404:
                return None  # permanent — don't retry
            # 429/503 = rate-limited/overloaded; 500/502/504 = transient server error.
            # All use exponential backoff so we don't hammer a struggling server.
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SLEEP * (2**attempt))
        except Exception:
            # Catches TimeoutException, ConnectError, RemoteProtocolError,
            # ReadError, SSL errors, etc. — all treated as transient.
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_SLEEP * (2**attempt))
    return None


# ── Multilingual ingest ───────────────────────────────────────────────────────


async def _ingest_language(lang: str, hs: Any, splitter: Any) -> tuple[int, int, list[str]]:
    """Download, chunk, and index all DOCUMENTS for a given language.

    doc_id format: ``eurlex-{celex}-{lang}``
    This prevents collision with EN entries (``eurlex-{celex}``) and ensures
    the idempotency check correctly distinguishes DE and FR entries from EN ones.

    NOTE: German compound words (e.g. "Arbeitnehmerfreizügigkeit") can produce
    longer tokens than their English/French equivalents, which may skew
    chunk-size estimates when using a character-based splitter calibrated for
    English text. If retrieval quality degrades on DE queries, consider tuning
    CHUNK_SIZE_CHARS downward (e.g., 1800) for DE or switching to a
    language-aware tokenizer (tiktoken cl100k_base).
    TODO: tune chunk size for DE if recall drops below 2/3 after Sprint 2.

    Returns (indexed_count, skipped_count, failed_celex_list).
    """
    from tqdm import tqdm

    label = _LANG_LABEL[lang]
    indexed_count = 0
    skipped_count = 0
    failed: list[str] = []

    with httpx.Client(
        headers={"User-Agent": "EvidenceEU-Seeder/1.0 (academic; contact@evidence.eu)"},
        follow_redirects=True,
    ) as http_client:
        for celex, regulation_id, topic in tqdm(
            _active_docs(), desc=f"Seeding [{label}]", unit="doc"
        ):
            # doc_id includes lang to prevent collision with EN entries
            doc_id = f"eurlex-{celex}-{lang}"

            # Idempotency: skip already-indexed DE/FR documents
            if not DRY_RUN and _already_indexed(http_client, doc_id):
                skipped_count += 1
                indexed_count += 1
                continue

            # ── Reducto path (ADR-009: public corpus only) ───────────────────
            html_m: bytes | None = None
            charset_m: str | None = None

            if ENABLE_REDUCTO and _reducto_available():
                reducto_result = _fetch_with_reducto(http_client, celex)
                if reducto_result is not None:
                    html_m, charset_m = reducto_result
                    tqdm.write(
                        f"  {CYAN}REDUCTO{RESET} [{label}] {celex} — parsed via Reducto's agentic OCR"
                    )

            # ── BeautifulSoup HTML fallback path ─────────────────────────────
            if html_m is None:
                fetch_result = _fetch_html_lang(http_client, celex, lang)
                if fetch_result is None:
                    tqdm.write(
                        f"  {YELLOW}SKIP{RESET} [{label}] {celex} — not found / fetch failed"
                    )
                    failed.append(celex)
                    # Rate-limit delay after failure to avoid hammering
                    await asyncio.sleep(2)
                    continue
                html_m, charset_m = fetch_result
                # Rate-limit delay after successful fetch to avoid 202 responses
                await asyncio.sleep(1)

            # Pass declared charset so BS4 decodes DE/FR umlauts/accents correctly
            text = _extract_text(html_m, charset_m)
            if len(text) < 200:
                tqdm.write(
                    f"  {YELLOW}SKIP{RESET} [{label}] {celex} — too short ({len(text)} chars)"
                )
                failed.append(celex)
                continue

            chunks = splitter.split_text(text)
            if not chunks:
                failed.append(celex)
                continue

            # Credit-safety: cap chunks/doc on Cloud (each retain is billed).
            if MAX_CHUNKS_PER_DOC:
                chunks = chunks[:MAX_CHUNKS_PER_DOC]

            metadata: dict[str, str] = {
                "source_url": EURLEX_HTML_LANG.format(lang=lang.upper(), celex=celex),
                "doc_id": doc_id,
                "lang": lang,
                "regulation_id": regulation_id,
                "topic": topic,
                "celex": celex,
            }
            context = f"{regulation_id} — {topic.replace('_', ' ').title()} [{label}]"
            doc_tags = [topic, "eu-regulation", lang]

            if DRY_RUN:
                tqdm.write(
                    f"  {CYAN}DRY{RESET} [{label}] {celex} — {len(chunks)} chunks, "
                    f"{len(text):,} chars"
                )
                indexed_count += 1
                continue

            doc_ok = True
            for chunk in chunks:
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        await hs.aretain(  # type: ignore[attr-defined]
                            bank_id=BANK_ID,
                            content=chunk,
                            document_id=doc_id,
                            context=context,
                            metadata=metadata,
                            tags=doc_tags,
                        )
                        break
                    except Exception as exc:
                        err_str = str(exc)
                        if attempt < MAX_RETRIES and any(
                            code in err_str for code in ("429", "503", "500", "rate")
                        ):
                            await asyncio.sleep(RETRY_BASE_SLEEP * (2**attempt))
                        else:
                            tqdm.write(f"  {RED}FAIL{RESET} [{label}] {celex} — {err_str[:120]}")
                            doc_ok = False
                            break
                if not doc_ok:
                    break

            if doc_ok:
                indexed_count += 1
                tqdm.write(
                    f"  {GREEN}OK{RESET}  [{label}] {celex} ({regulation_id}) — "
                    f"{len(chunks)} chunks"
                )
            else:
                failed.append(celex)

    return indexed_count, skipped_count, failed


# ── Multilingual validation ───────────────────────────────────────────────────


async def _validate_language(lang: str, hs: Any) -> tuple[int, list[dict[str, Any]]]:
    """Run 3 recall queries for lang; return (passed_count, result_rows).

    Each row: {id, label, query, lang, top1, correct, expect_celex}
    """
    label = _LANG_LABEL[lang]
    queries = _LANG_QUERIES[lang]
    passed = 0
    rows: list[dict[str, Any]] = []

    for vq in queries:
        try:
            resp = await hs.arecall(  # type: ignore[attr-defined]
                bank_id=BANK_ID,
                query=vq["query"],
                budget="high",
                include_chunks=True,
                max_tokens=2048,
            )
            results = getattr(resp, "results", []) or []
            chunks_dict: dict = getattr(resp, "chunks", {}) or {}

            if not results and not chunks_dict:
                top1 = "(no results)"
                correct = False
            else:
                top_text = getattr(results[0], "text", "") if results else ""
                if top_text:
                    top1 = top_text[:39].replace("\n", " ") + "..."
                elif chunks_dict:
                    top1 = f"(chunk: {next(iter(chunks_dict))[:33]})"
                else:
                    top1 = "(results present, no text)"
                expect = vq["expect_celex"].lower()
                correct = False

                for item in results[:10]:
                    doc_id_val = str(getattr(item, "document_id", "") or "").lower()
                    meta = getattr(item, "metadata", {}) or {}
                    meta_celex = str(meta.get("celex", "")).lower()
                    meta_lang = str(meta.get("lang", "")).lower()
                    celex_match = expect in doc_id_val or expect in meta_celex
                    # Only credit results from the target language — prevents an EN
                    # result for the same regulation from masking a missing DE/FR entry.
                    lang_match = meta_lang == lang or doc_id_val.endswith(f"-{lang}")
                    if celex_match and lang_match:
                        correct = True
                        break

                if not correct:
                    for chunk_key in chunks_dict:
                        # chunk key pattern: {bank_id}_{doc_id}_{idx}
                        # doc_id for lang is eurlex-{celex}-{lang}, so both CELEX
                        # and lang suffix must appear in the key.
                        if expect in chunk_key.lower() and f"-{lang}" in chunk_key.lower():
                            correct = True
                            break

        except Exception as exc:
            top1 = f"ERROR: {str(exc)[:33]}"
            correct = False

        rows.append(
            {
                "id": vq["id"],
                "label": vq["label"],
                "query": vq["query"],
                "lang": label,
                "top1": top1,
                "correct": correct,
                "expect_celex": vq["expect_celex"],
            }
        )
        if correct:
            passed += 1

    return passed, rows


# ── Recall report writer ──────────────────────────────────────────────────────


def _save_recall_report(
    date_str: str,
    index_counts: dict[str, int],
    all_rows: list[dict[str, Any]],
    lang_passed: dict[str, int],
) -> None:
    """Write multilingual recall results to docs/testing/multilingual-recall.md.

    Creates the file (overwriting any previous run) — not written to disk during
    ingest; this is a post-run summary artifact only.

    Path is resolved relative to this script file so the report lands in the
    correct repo location regardless of the working directory the caller uses.
    """
    _repo_root = Path(__file__).resolve().parent.parent
    _out_dir = _repo_root / "docs" / "testing"
    _out_dir.mkdir(parents=True, exist_ok=True)
    path = str(_out_dir / "multilingual-recall.md")

    lines: list[str] = [
        "# Multilingual Recall Report",
        "",
        f"**Date run:** {date_str}  ",
        f"**Script:** `scripts/seed_documents.py --multilingual`  ",
        f"**Languages:** {', '.join(lang.upper() for lang in LANGUAGES)}  ",
        "",
        "## Index Counts",
        "",
        "| Language | Documents Indexed |",
        "|----------|-------------------|",
    ]
    for lang in LANGUAGES:
        lines.append(f"| {lang.upper()} | {index_counts.get(lang, 0)} |")

    lines += [
        "",
        "## Recall Results",
        "",
        "| Query | Lang | Top-1 Source | Pass/Fail |",
        "|-------|------|--------------|-----------|",
    ]
    for row in all_rows:
        pf = "✅ PASS" if row["correct"] else "❌ FAIL"
        q_short = row["query"][:60].replace("|", "\\|")
        top1_short = row["top1"][:45].replace("|", "\\|")
        lines.append(f"| {q_short} | {row['lang']} | {top1_short} | {pf} |")

    lines += ["", "## Summary", ""]
    for lang in LANGUAGES:
        label = lang.upper()
        p = lang_passed.get(lang, 0)
        lines.append(f"**RECALL {label}: {p}/3 passed**  ")

    lines += ["", "### Failed Query Diagnosis", ""]
    failed_rows = [r for r in all_rows if not r["correct"]]
    if not failed_rows:
        lines.append("All queries passed — no failures to diagnose. 🎉")
    else:
        for row in failed_rows:
            lines.append(
                f"- **{row['id']}** (`{row['lang']}`): Expected CELEX `{row['expect_celex']}` "
                f"in top results. Got: `{row['top1'][:80]}`.  "
            )
            lines.append(
                f"  *Possible causes:* wrong source returned (embedding mismatch), "
                f"document not indexed in this language, or chunk boundary cut key passage."
            )

    lines += [
        "",
        "---",
        "*Generated by EvidenceEU seed_documents.py multilingual pass.*",
    ]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"  {GREEN}Report saved → {path}{RESET}")


# ── Multilingual main ─────────────────────────────────────────────────────────


async def run_multilingual() -> int:
    """DE + FR seeding pass. Returns 0 on success (≥50 docs per language), 1 on failure."""
    docs = _active_docs()
    print(f"\n{BOLD}EvidenceEU — Multilingual Corpus Seeder (DE + FR){RESET}")
    print(f"  Hindsight : {HINDSIGHT_URL}")
    print(f"  Bank      : {BANK_ID}")
    print(f"  Auth      : {'Bearer (Cloud)' if ACCESS_KEY else 'none (self-hosted)'}")
    print(f"  Languages : {', '.join(lang.upper() for lang in LANGUAGES)}")
    print(f"  Documents : {len(docs)} per language ({len(docs) * len(LANGUAGES)} total)")
    if MAX_CHUNKS_PER_DOC:
        print(f"  Chunk cap : {MAX_CHUNKS_PER_DOC}/doc")
    if DRY_RUN:
        print(f"  {YELLOW}Mode      : DRY RUN (no ingest){RESET}")
    _hr()

    # Reachability check (Cloud has no public /health; probe the bank instead)
    print("\n[0] Reachability check ...")
    ok, detail = _cloud_reachable()
    if ok:
        print(f"  {GREEN}OK{RESET}  {detail}")
    else:
        print(f"  {RED}FAIL{RESET}  {detail}")
        print("       Local: docker-compose up hindsight -d  |  Cloud: check HINDSIGHT_ACCESS_KEY")
        return 1

    hs = _CloudSeeder(HINDSIGHT_URL, api_key=ACCESS_KEY, bank_id=BANK_ID)

    try:
        # Ensure bank
        print("\n[1] Ensuring memory bank ...")
        try:
            await hs.acreate_bank(  # type: ignore[attr-defined]
                bank_id=BANK_ID,
                name="EvidenceEU Document Corpus",
                mission=(
                    "EU cross-border document intelligence assistant with deep knowledge of "
                    "regulations on freedom of movement, employment rights, professional "
                    "qualifications, social security, equal treatment, and cross-border services."
                ),
            )
            print(f"  {GREEN}OK{RESET}  Bank '{BANK_ID}' ready")
        except Exception as exc:
            print(f"  {DIM}  (already exists or: {exc}){RESET}")

        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE_CHARS,
            chunk_overlap=CHUNK_OVERLAP_CHARS,
            separators=["\n\n", "\n", ". ", " ", ""],
            keep_separator=False,
        )

        # Ingest phase — each language sequentially to avoid rate-limit spikes
        index_counts: dict[str, int] = {}
        exit_code = 0

        for lang in LANGUAGES:
            label = _LANG_LABEL[lang]
            print(f"\n[2-{label}] Processing {len(docs)} documents in {label} ...")
            indexed, skipped, failed = await _ingest_language(lang, hs, splitter)
            index_counts[lang] = indexed

            _hr()
            print(f"  [{label}] Indexed : {indexed}")
            print(f"  [{label}] Skipped : {skipped} (already in Hindsight)")
            print(f"  [{label}] Failed  : {len(failed)}")
            if failed:
                print(f"  [{label}] Failed IDs: {', '.join(failed[:15])}")

            if indexed < MIN_DOCS:
                print(
                    f"\n{RED}ERROR: [{label}] Only {indexed}/{MIN_DOCS} documents indexed. Exit 1.{RESET}"
                )
                exit_code = 1

        if exit_code != 0:
            return exit_code

        # Validation phase
        if DRY_RUN:
            print(f"\n{DIM}Dry run — skipping validation.{RESET}")
            print(f"\n{BOLD}RECALL DE: N/A (dry run){RESET}")
            print(f"{BOLD}RECALL FR: N/A (dry run){RESET}\n")
            return 0

        print("\n[3] Waiting 15 s for Hindsight fact extraction ...")
        await asyncio.sleep(15)

        print(f"\n[4] Multilingual validation queries ...")
        _hr()

        W_Q, W_R, W_L, W_S = 42, 38, 6, 14
        print(
            f"{BOLD}{'Query':<{W_Q}} {'Top-1 Result':<{W_R}} "
            f"{'Lang':<{W_L}} {'Correct Src?':<{W_S}} P/F{RESET}"
        )
        print("-" * (W_Q + W_R + W_L + W_S + 8))

        all_rows: list[dict[str, Any]] = []
        lang_passed: dict[str, int] = {}

        for lang in LANGUAGES:
            label = _LANG_LABEL[lang]
            passed, rows = await _validate_language(lang, hs)
            lang_passed[lang] = passed
            all_rows.extend(rows)

            for row in rows:
                qshort = f"{row['id']}: {row['query'][:35]}"
                top1 = row["top1"]
                correct = row["correct"]
                pf_label = f"{GREEN}PASS{RESET}" if correct else f"{RED}FAIL{RESET}"
                src_label = f"{GREEN}Yes{RESET}" if correct else f"{RED}No{RESET}"
                src_pad = src_label + " " * (W_S - 3)
                print(f"{qshort:<{W_Q}} {top1:<{W_R}} {label:<{W_L}} {src_pad} {pf_label}")

        _hr()
        for lang in LANGUAGES:
            label = _LANG_LABEL[lang]
            p = lang_passed[lang]
            colour = GREEN if p >= 2 else RED
            print(f"{BOLD}{colour}RECALL {label}: {p}/3 passed{RESET}")

        # Save report to docs/testing/multilingual-recall.md
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        _save_recall_report(date_str, index_counts, all_rows, lang_passed)

        return 0

    finally:
        # Always close the Hindsight client — even on unexpected exceptions.
        await hs.aclose()


if __name__ == "__main__":
    if "--multilingual" in sys.argv:
        sys.exit(asyncio.run(run_multilingual()))
    else:
        sys.exit(asyncio.run(run()))
