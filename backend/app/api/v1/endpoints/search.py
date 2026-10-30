# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Search Endpoint — Multilingual Document Search (Sprint 2)

Responsibilities:
- Accept natural-language queries via GET /api/v1/search?q=...&top_k=5
- Stream results back to the frontend via Server-Sent Events (SSE)
- Delegate retrieval to HindsightRAGService.query()
- Yield typed SSE events: result | error | done (sentinel)
- Detect client disconnects between yields and stop the generator cleanly
- Propagate upstream RAG errors as SSE error events — never as HTTP 500
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.sse import sse_frame
from app.db.d1_client import D1Client
from app.integrations.datadog import (
    begin_search_stage_batch,
    build_search_stage_series,
    flush_search_stage_batch,
    record_search_stage,
    reset_search_stage_batch,
)
from app.integrations.llm.answer_generation import active_model_info, generate_answer_stream
from app.integrations.llm.answer_generation import generate_answer as apertus_generate
from app.integrations.llm.answer_generation import is_enabled as apertus_enabled
from app.repositories.glossary_repo import GlossaryRepo
from app.services.chat_guidance import (
    GroundingConfig,
    build_empty_result_guidance,
    build_grounding_verdict,
)
from app.services.rag_service import (
    PLACEHOLDER_DISCLAIMER,
    HindsightRAGService,
    build_rag_prompt,
    detect_placeholders,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _request_id(request: Request) -> str:
    """Return a log-safe correlation ID propagated by the proxy."""
    for header in ("x-request-id", "cf-ray"):
        value = request.headers.get(header)
        if isinstance(value, str) and _REQUEST_ID_PATTERN.fullmatch(value):
            return value
    return "unavailable"


# ── Pydantic models ────────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str
    language: str = "en"  # ISO 639-1 code: en, de, fr
    document_types: list[str] = []  # e.g. ["regulation", "form", "guideline"]
    max_results: int = 10


class SearchResult(BaseModel):
    answer: str
    sources: list[dict[str, str]]  # [{title, url, excerpt, language}]
    query_language: str
    result_languages: list[str]


# ── Core SSE generator ─────────────────────────────────────────────────────────


async def _sse_events(
    q: str,
    top_k: int,
    rag: HindsightRAGService,
    request: Request,
    lang: str = "en",
    retrieval_q: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    guidance: bool = False,
    emit_model: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams typed SSE events for a single search request.

    Event sequence (happy path):
        ping  × N   — ``: ping\n\n`` comment every 10s during RAG query wait
        result × N  — one per RAG chunk returned by HindsightRAGService.query()
        done        — sentinel signalling end-of-stream

    Event sequence (upstream failure):
        error × 1  — message from the exception
        done       — sentinel so the client can close cleanly

    Client disconnect:
        If ``await request.is_disconnected()`` returns True between yields the
        generator breaks immediately without raising or emitting further events.

    Keepalive:
        During the RAG query phase (which may take 1–15s), SSE comment lines
        are emitted every 10 seconds to prevent proxy timeouts (Cloudflare 524)
        and browser EventSource reconnect triggers. The ``: ping`` format
        matches FastAPI's built-in EventSourceResponse convention so the
        keepalive is compatible if we later switch to ``response_class``.

        Once results start flowing, data events are frequent enough that no
        keepalive is needed.
    """
    disconnected = False

    try:
        # ── RAG query with keepalive ────────────────────────────────────
        # Use asyncio.wait with a shorter timeout so we can yield periodic
        # SSE comment lines while the external RAG API is still processing.
        query_task = asyncio.ensure_future(
            asyncio.wait_for(rag.query(q=retrieval_q or q, top_k=top_k, lang=lang), timeout=90.0)
        )

        _KEEPALIVE_INTERVAL = 10.0

        while True:
            done, _ = await asyncio.wait([query_task], timeout=_KEEPALIVE_INTERVAL)
            if query_task in done:
                results: list[dict[str, Any]] = query_task.result()
                break

            yield ": ping\n\n"

            if await request.is_disconnected():
                logger.debug("SSE client disconnected during RAG query (q=%r) — stopping", q)
                query_task.cancel()
                return

        # ── Pre-compute guidance (cheap, deterministic) ──────────────────
        guidance_msg = build_empty_result_guidance(q) if guidance else None

        # ── Stream results ──────────────────────────────────────────────
        for result in results:
            if await request.is_disconnected():
                logger.debug("SSE client disconnected during stream (q=%r) — stopping generator", q)
                disconnected = True
                break

            yield sse_frame("result", result)

            if settings.SSE_CHUNK_DELAY_MS > 0:
                await asyncio.sleep(settings.SSE_CHUNK_DELAY_MS / 1000)

        # ── Guidance marker matched → emit curated answer, skip LLM call ─
        # Emit BOTH guidance event (for structured display) and answer_chunks
        # (so frontend.answer path fires even if guidance event races with
        # isStreaming=False). The frontend prioritises guidance over answer,
        # so both is safe.
        if guidance_msg and guidance_msg["reason"] != "no_verified_source" and not disconnected:
            if not await request.is_disconnected():
                yield sse_frame("results_complete", "[RESULTS_READY]")
                yield sse_frame("guidance", guidance_msg)
                msg = guidance_msg["message"]
                for i in range(0, len(msg), 80):
                    yield sse_frame("answer_chunk", {"text": msg[i : i + 80]})
            await flush_search_stage_batch()
            yield sse_frame("done", "[DONE]")
            return

        if guidance and not results and not await request.is_disconnected():
            yield sse_frame("guidance", guidance_msg)

        # ── Results-ready sentinel ──────────────────────────────────────
        # Emit `results_complete` as soon as retrieved chunks are delivered,
        # BEFORE the (slower) answer-generation step. The client has its RAG
        # hits now, so user-perceived latency = retrieval time (~2–3s),
        # independent of the Apertus answer stream. This decouples NFR-01
        # (first-result p95) from answer-generation tail latency and keeps
        # 50-VU concurrency from blocking on the LLM call. Apertus chunks
        # stream in AFTER this as a progressive enhancement; the final `done`
        # (emitted by the wrapping generator) marks true stream end.
        if not await request.is_disconnected():
            yield sse_frame("results_complete", "[RESULTS_READY]")

        # ── Generate a grounded answer with the configured provider ────
        # Streamed AFTER `done`: retrieved chunks are already on the client.
        # No-op if its token is unset. Layer 2 injection defense:
        # build_rag_prompt() wraps chunks in structural delimiters before
        # sending to the LLM.
        if apertus_enabled() and results and not await request.is_disconnected():
            generation_started = time.perf_counter()
            generation_completed = False
            answer_parts: list[str] = []
            try:
                prompt = build_rag_prompt(
                    q,
                    results,
                    conversation_history=conversation_history,
                    guidance=guidance,
                )
                answer_stream = generate_answer_stream(
                    prompt,
                    neuron_budget_kv=getattr(request.scope.get("env"), "NEURON_BUDGET_KV", None),
                )
                first_token = await anext(answer_stream, None)
                if first_token is not None:
                    if await request.is_disconnected():
                        disconnected = True
                    else:
                        answer_parts.append(first_token)
                        model_info = active_model_info(prompt) if emit_model else None
                        if model_info is not None:
                            yield sse_frame("answer_model", model_info.as_event_payload())
                        yield sse_frame("answer_chunk", {"text": first_token})

                async for token in answer_stream:
                    if disconnected:
                        break
                    if await request.is_disconnected():
                        logger.debug("SSE client disconnected during generation (q=%r)", q)
                        disconnected = True
                        break
                    answer_parts.append(token)
                    yield sse_frame("answer_chunk", {"text": token})
                generation_completed = not disconnected

                # Post-generation placeholder check — defense-in-depth.
                # If the LLM output contains skeleton placeholders (bare %,
                # empty ranges), append a disclaimer so the user knows to
                # verify exact figures externally.
                if generation_completed and not disconnected:
                    full_answer = "".join(answer_parts)
                    if detect_placeholders(full_answer):
                        yield sse_frame(
                            "answer_chunk",
                            {"text": PLACEHOLDER_DISCLAIMER},
                        )

                    # Grounding gate (Linus DEC-0059 adaptation): validate
                    # each claim against known document IDs and entity mentions.
                    # Emits grounding_verdict SSE event; soft refusal only.
                    grounding_verdict = build_grounding_verdict(
                        full_answer,
                        results,
                        config=GroundingConfig(
                            enabled=settings.GROUNDING_GATE_ENABLED,
                            soft_refusal=True,
                        ),
                    )
                    yield sse_frame("grounding_verdict", grounding_verdict)
            except RuntimeError as exc:
                # Answer-generation failure is non-fatal; retrieved chunks remain useful.
                # Frontend already has the raw chunks; answer is an enhancement.
                logger.warning("RAG answer generation failed (non-fatal): %s", exc)
                yield sse_frame("answer_error", {"message": str(exc)})
            finally:
                generation_outcome = (
                    "success" if generation_completed else "cancelled" if disconnected else "error"
                )
                generation_metric = build_search_stage_series(
                    stage="answer_generation",
                    outcome=generation_outcome,
                    duration_ms=(time.perf_counter() - generation_started) * 1000,
                    env=settings.APP_ENV,
                )
                await record_search_stage(generation_metric)

    except TimeoutError:
        logger.error("RAG query timed out after 90 seconds")
        if not await request.is_disconnected():
            yield sse_frame("results_complete", "[RESULTS_READY]")
    except Exception as exc:  # noqa: BLE001
        q_hash = hashlib.sha256(q.encode()).hexdigest()[:8]
        logger.warning("Upstream RAG error for q_hash=%s: %s", q_hash, exc)
        if not await request.is_disconnected():
            yield sse_frame("results_complete", "[RESULTS_READY]")

    if not disconnected:
        # Stage timings are flushed as one bounded request before the client
        # closes on `done`. This avoids relying on background work after the
        # StreamingResponse lifecycle ends.
        await flush_search_stage_batch()
        yield sse_frame("done", "[DONE]")


async def _sse_generator(
    q: str,
    top_k: int,
    rag: HindsightRAGService,
    request: Request,
    lang: str = "en",
    retrieval_q: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    guidance: bool = False,
    emit_model: bool = False,
    request_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Bind metrics and record one structured terminal stream outcome."""
    batch_token = begin_search_stage_batch()
    correlation_id = request_id or _request_id(request)
    outcome = "premature_termination"
    saw_application_error = False
    try:
        async for frame in _sse_events(
            q=q,
            top_k=top_k,
            rag=rag,
            request=request,
            lang=lang,
            retrieval_q=retrieval_q,
            conversation_history=conversation_history,
            guidance=guidance,
            emit_model=emit_model,
        ):
            if frame.startswith("event: error") or frame.startswith("event: answer_error"):
                saw_application_error = True
            elif frame.startswith("event: done\n"):
                outcome = "application_error" if saw_application_error else "done"
            yield frame
        if outcome == "premature_termination" and await request.is_disconnected():
            outcome = "client_disconnect"
    except asyncio.CancelledError:
        outcome = "client_disconnect"
        raise
    finally:
        reset_search_stage_batch(batch_token)
        logger.info(
            json.dumps(
                {
                    "event": "sse_stream_outcome",
                    "request_id": correlation_id,
                    "outcome": outcome,
                    "endpoint": "chat" if emit_model else "search",
                },
                separators=(",", ":"),
            )
        )


# ── SSE response factory ───────────────────────────────────────────────────────


def _sse_response(
    generator: AsyncGenerator[str, None], request_id: str | None = None
) -> StreamingResponse:
    """
    Wrap a generator in a StreamingResponse with SSE-compliant headers.

    Headers set:
      Content-Type: text/event-stream; charset=utf-8
        — MIME type required by the W3C EventSource spec.
      Cache-Control: no-cache
        — Prevents proxy/browser caching of the live event stream.
      X-Accel-Buffering: no
        — Disables nginx proxy buffering so events reach the client immediately.

    NOT set (by design):
      Connection: keep-alive
        — Prohibited in HTTP/2 (Safari refuses responses with it).
          Cloudflare Workers uses HTTP/2 by default.
          HTTP/1.1 already defaults to keep-alive without this header.
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            **({"X-Request-ID": request_id} if request_id else {}),
        },
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/")
async def search_stream(
    request: Request,
    q: str = Query(..., description="Natural-language query in any supported EU language"),
    top_k: int = Query(5, ge=1, le=50, description="Maximum number of results to return"),
    language: str = Query("en", description="Query language (ISO 639-1: en, de, fr)"),
) -> StreamingResponse:
    """
    SSE streaming search — yields typed events as results arrive from HindsightRAGService.

    Uses the httpx-based Hindsight REST client (Pyodide/Workers-safe).
    Delegates to HindsightRAGService.query() for 4-way hybrid search (dense + BM25 +
    semantic reranking + graph).

    Event types:
      result  — one RAG chunk with selected provenance fields:
                {"id", "text", "type", "chunk_id", "entities", "rank",
                 "document_id", "source_url", "source_title", "source_language"}
      error   — upstream failure: {"message": "<str>"}
      done    — end-of-stream sentinel: "[DONE]"
    """
    normalized_language = language.lower().strip()
    if normalized_language not in {"en", "de", "fr"}:
        normalized_language = "en"

    from app.integrations.posthog import capture_event  # noqa: PLC0415

    await capture_event(
        "search_stream_started",
        distinct_id=getattr(request.state, "posthog_distinct_id", ""),
        properties={"language": normalized_language, "top_k": top_k},
        session_id=getattr(request.state, "posthog_session_id", None),
    )

    rag: HindsightRAGService = HindsightRAGService(
        glossary_repo=GlossaryRepo(D1Client.from_scope(request.scope))
    )
    generator = _sse_generator(
        q=q,
        top_k=top_k,
        rag=rag,
        request=request,
        lang=normalized_language,
        request_id=_request_id(request),
    )

    return _sse_response(generator, _request_id(request))


@router.post("/", response_model=SearchResult)
async def search_documents(request: Request, body: SearchRequest) -> SearchResult:
    """
    Non-streaming document search. Returns answer + citations.

    Delegates to the same RAG pipeline as the streaming endpoint
    but collects all results before returning (DRY).
    """
    try:
        rag = HindsightRAGService(glossary_repo=GlossaryRepo(D1Client.from_scope(request.scope)))
        results = await rag.query(q=body.query, top_k=body.max_results, lang=body.language)

        answer_text = ""
        if results:
            if apertus_enabled():
                prompt = build_rag_prompt(body.query, results)
                apertus_resp = await apertus_generate(prompt)
                if apertus_resp is not None:
                    answer_text = apertus_resp.answer

            if not answer_text:
                answer_text = results[0].get("text", "")

        from app.integrations.posthog import capture_event  # noqa: PLC0415

        await capture_event(
            "search_performed",
            distinct_id=getattr(request.state, "posthog_distinct_id", ""),
            properties={
                "language": body.language,
                "max_results": body.max_results,
                "result_count": len(results),
                "has_answer": bool(answer_text),
            },
            session_id=getattr(request.state, "posthog_session_id", None),
        )

        return SearchResult(
            answer=answer_text,
            sources=[
                {
                    "title": r.get("source_title") or r.get("document_id") or r.get("id") or "",
                    "url": r.get("source_url") or "",
                    "excerpt": r.get("text", ""),
                    "language": r.get("source_language") or body.language,
                }
                for r in results
            ],
            query_language=body.language,
            result_languages=[body.language],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST /search/ failed: %s", exc)
        raise


@router.get("/stream")
async def search_documents_stream(
    request: Request,
    query: str = Query(..., description="Natural language search query"),
    language: str = Query("en", description="Query language (ISO 639-1)"),
) -> StreamingResponse:
    """
    Legacy SSE streaming search endpoint — kept for backward compatibility.
    Prefer GET / with q= param for new clients.
    """
    return await search_stream(request=request, q=query, language=language, top_k=5)
