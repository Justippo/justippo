"""
OCR Benchmark Runner — Sprint 2 (3-way: Mistral + Tesseract + Reducto).

Integrates with pytest (runs via `pytest tests/benchmark/`), reuses
existing OCRService and mock infrastructure from test_ocr_service.py.

Ephemeral: all PDFs are generated in-memory via fpdf2; no disk writes.
Measures: time (ms), text quality (1-5 heuristic), confidence score,
fallback correctness, path used (Mistral vs Tesseract vs Reducto).
DE/FR language detection and chunking validation included.

DRY: reuses _make_httpx_response from test_ocr_service.py pattern and
the SampleMeta dataclass from the fixture generator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ocr_service import OCRPage, OCRService

from .pdf_fixture_generator import SampleMeta, generate_all_disk_fixtures, generate_all_samples

# ---------------------------------------------------------------------------
# Benchmark result schema (reuses OCRPage from ocr_service.py)
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """Single benchmark run result."""

    sample_name: str
    path_used: str  # "Mistral" | "Tesseract"
    quality: int  # 1-5 heuristic
    confidence: float | None
    fallback_correct: bool | str  # True | False | "not_applicable"
    time_ms: float
    pages: int
    total_chars: int
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Quality heuristic (DRY: one place, reused across all samples)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Language detection (heuristic, no external deps — reuse)
# ---------------------------------------------------------------------------


def _detect_language(text: str) -> str:
    """Character-frequency based language detection for DE/FR/EN validation.

    Returns 'de', 'fr', 'en', or 'mixed'.
    """
    de_markers = (
        sum(1 for c in text if c in "äßöü")
        + text.count(" der ")
        + text.count(" die ")
        + text.count(" und ")
        + text.count(" das ")
    )
    fr_markers = (
        sum(1 for c in text if c in "éèêëçàùûîôâ")
        + text.count(" le ")
        + text.count(" la ")
        + text.count(" les ")
        + text.count(" des ")
    )
    en_markers = text.count(" the ") + text.count(" and ") + text.count(" is ") + text.count(" of ")
    if de_markers > max(fr_markers, en_markers, 2):
        return "de"
    if fr_markers > max(de_markers, en_markers, 2):
        return "fr"
    if en_markers > 2 or (de_markers == 0 and fr_markers == 0):
        return "en"
    return "mixed"


def _rate_quality(text: str, expected_chars_min: int) -> int:
    """Rate extracted text quality on a 1-5 scale.

    5 = substantial text, no obvious garbage
    4 = good but some artifacts
    3 = partial extraction or significant errors
    2 = minimal usable text
    1 = empty or garbage

    This is a heuristic for pre-live benchmarking; real CER will replace it.
    """
    if not text or len(text.strip()) == 0:
        return 1
    stripped = text.strip()
    if len(stripped) < 10:
        return 2
    if len(stripped) < expected_chars_min * 0.3:
        return 3
    if len(stripped) < expected_chars_min * 0.7:
        return 4
    return 5


# ---------------------------------------------------------------------------
# Mock helpers (DRY: same pattern as _make_httpx_response in test_ocr_service.py)
# ---------------------------------------------------------------------------

_MOCK_MISTRAL_RESPONSES: dict[str, dict[str, Any]] = {
    "01_clean_english": {
        "pages": [
            {
                "index": 0,
                "markdown": "EvidenceEU — Multilingual Document Intelligence\n\nThis document is a clean English-language sample. The OCR system achieved near-perfect accuracy.",
                "confidence_scores": {"average_page_confidence_score": 0.98},
            }
        ],
    },
    "02_low_quality_scan": {
        "pages": [
            {
                "index": 0,
                "markdown": "This text simulates a low-quality scan. Font is small, text color is light gray.",
                "confidence_scores": {"average_page_confidence_score": 0.55},
            }
        ],
    },
    "03_german_legal": {
        "pages": [
            {
                "index": 0,
                "markdown": "Aufenthaltserlaubnis — Bescheinigung gemäß § 78a AufenthG\n\nDie zuständige Ausländerbehörde bescheinigt hiermit, dass der Antragsteller die Erteilung beantragt hat.",
                "confidence_scores": {"average_page_confidence_score": 0.91},
            }
        ],
    },
    "04_french_admin": {
        "pages": [
            {
                "index": 0,
                "markdown": "Attestation de résidence — Préfecture de Paris\n\nVu le Code de l'entrée et du séjour des étrangers, la présente attestation certifie le dépôt.",
                "confidence_scores": {"average_page_confidence_score": 0.89},
            }
        ],
    },
    "05_table_data": {
        "pages": [
            {
                "index": 0,
                "markdown": "Quarterly Report — Q1 2026\n\nCountry | Applications | Approved | Rejected | Pending\nGermany | 12,450 | 10,200 | 1,800 | 450\nFrance | 8,920 | 7,100 | 1,500 | 320",
                "confidence_scores": {"average_page_confidence_score": 0.72},
            }
        ],
    },
    "06_handwriting_simulation": {
        "pages": [
            {
                "index": 0,
                "markdown": "This text is rendered in italic font. The quick brown fox jumps over the lazy dog.",
                "confidence_scores": {"average_page_confidence_score": 0.60},
            }
        ],
    },
    "07_multi_column": {
        "pages": [
            {
                "index": 0,
                "markdown": "COLUMN ONE: This text appears in the left column. COLUMN TWO: The right column contains separate content.",
                "confidence_scores": {"average_page_confidence_score": 0.65},
            }
        ],
    },
    "08_mixed_languages": {
        "pages": [
            {
                "index": 0,
                "markdown": "Trilingual Document\nEnglish Section: This section is written in English.\nDeutscher Abschnitt: Dieser Abschnitt ist auf Deutsch verfasst.\nSection française: Cette section est rédigée en français.",
                "confidence_scores": {"average_page_confidence_score": 0.85},
            }
        ],
    },
    "09_blank_page": {
        "pages": [
            {
                "index": 0,
                "markdown": "",
                "confidence_scores": {"average_page_confidence_score": 0.0},
            }
        ],
    },
    "10_multi_page": {
        "pages": [
            {
                "index": 0,
                "markdown": "Page 1: Introduction — This document provides a comprehensive overview.",
                "confidence_scores": {"average_page_confidence_score": 0.95},
            },
            {
                "index": 1,
                "markdown": "Page 2: Background — The European Union's single market enables free movement.",
                "confidence_scores": {"average_page_confidence_score": 0.94},
            },
            {
                "index": 2,
                "markdown": "Page 3: Methodology — The EvidenceEU platform uses a hybrid architecture.",
                "confidence_scores": {"average_page_confidence_score": 0.96},
            },
            {
                "index": 3,
                "markdown": "Page 4: Results — Preliminary results show 97% character-level accuracy.",
                "confidence_scores": {"average_page_confidence_score": 0.97},
            },
            {
                "index": 4,
                "markdown": "Page 5: Conclusions — Future work includes Matrix protocol integration.",
                "confidence_scores": {"average_page_confidence_score": 0.93},
            },
        ],
    },
    # Disk fixture mock responses (new 10-fixture set)
    "d01_clean_english": {
        "pages": [
            {
                "index": 0,
                "markdown": "EvidenceEU — Multilingual Document Intelligence\n\nThis document is a clean English-language sample. OCR systems should achieve near-perfect accuracy.",
                "confidence_scores": {"average_page_confidence_score": 0.98},
            }
        ],
    },
    "d03_german_legal": {
        "pages": [
            {
                "index": 0,
                "markdown": "Aufenthaltserlaubnis — Bescheinigung gemäß § 78a AufenthG\n\nDie zuständige Ausländerbehörde bescheinigt hiermit, dass der Antragsteller die Erteilung beantragt hat.",
                "confidence_scores": {"average_page_confidence_score": 0.91},
            }
        ],
    },
    "d04_french_admin": {
        "pages": [
            {
                "index": 0,
                "markdown": "Attestation de résidence — Préfecture de Paris\n\nVu le Code de l'entrée et du séjour des étrangers, la présente attestation certifie le dépôt.",
                "confidence_scores": {"average_page_confidence_score": 0.89},
            }
        ],
    },
    "d04_low_quality_scan": {
        "pages": [
            {
                "index": 0,
                "markdown": "This text simulates a low-quality scan. Font is small, text color is light gray. Low DPI and noise present.",
                "confidence_scores": {"average_page_confidence_score": 0.55},
            }
        ],
    },
    "d05_table_3col_5row": {
        "pages": [
            {
                "index": 0,
                "markdown": "Cross-Border Document Types -- EU Overview\n\nDocument Type | Authority | Validity\nBirth Certificate | Civil Registry | 10 years\nMarriage License | Municipal Office | 6 months\nDiploma | University | Unlimited\nCriminal Record | Ministry of Justice | 3 months\nResidence Permit | Immigration Office | 1-5 years",
                "confidence_scores": {"average_page_confidence_score": 0.72},
            }
        ],
    },
    "d06_multipage_3pg": {
        "pages": [
            {
                "index": 0,
                "markdown": "Page 1: Introduction to Cross-Border Documents\n\nCross-border document recognition is a cornerstone of the European Union's single market.",
                "confidence_scores": {"average_page_confidence_score": 0.95},
            },
            {
                "index": 1,
                "markdown": "Page 2: Legal Framework\n\nRegulation (EU) 2016/1191 simplifies the circulation of certain public documents between Member States.",
                "confidence_scores": {"average_page_confidence_score": 0.94},
            },
            {
                "index": 2,
                "markdown": "Page 3: Practical Guidance\n\nTo obtain a multilingual standard form, visit the issuing authority in your country of residence.",
                "confidence_scores": {"average_page_confidence_score": 0.93},
            },
        ],
    },
    "d07_mixed_en_de": {
        "pages": [
            {
                "index": 0,
                "markdown": "Bilingual Document -- EN / DE\n\nEnglish Section: This certificate confirms that the applicant has submitted a complete application.\n\nDeutscher Abschnitt: Diese Bescheinigung bestätigt, dass der Antragsteller einen vollständigen Antrag eingereicht hat.",
                "confidence_scores": {"average_page_confidence_score": 0.85},
            }
        ],
    },
    "d08_bold_italic_heavy": {
        "pages": [
            {
                "index": 0,
                "markdown": "Formatted Document -- Bold & Italic Heavy\n\nTHIS SECTION IS RENDERED ENTIRELY IN BOLD TYPEFACE. The purpose is to test OCR recognition.\n\nThis section is rendered entirely in italic typeface.\n\nThe quick brown fox jumps over the lazy dog. This sentence tests inline formatting transitions.",
                "confidence_scores": {"average_page_confidence_score": 0.60},
            }
        ],
    },
    "d09_handwriting_simulation": {
        "pages": [
            {
                "index": 0,
                "markdown": "This text simulates the appearance of handwritten script. The quick brown fox jumps over the lazy dog.",
                "confidence_scores": {"average_page_confidence_score": 0.51},
            }
        ],
    },
    "d10_blank_page": {
        "pages": [
            {
                "index": 0,
                "markdown": "",
                "confidence_scores": {"average_page_confidence_score": 0.0},
            }
        ],
    },
    # Original disk fixture mock responses end
}


def _mock_mistral_response(sample_name: str) -> MagicMock:
    """Build a mock httpx.Response for a given sample (DRY)."""
    body = _MOCK_MISTRAL_RESPONSES.get(sample_name, _MOCK_MISTRAL_RESPONSES["01_clean_english"])
    resp = MagicMock()
    resp.status_code = 200
    resp.text = ""
    resp.json.return_value = body
    return resp


# ---------------------------------------------------------------------------
# Main benchmark executor
# ---------------------------------------------------------------------------


async def _run_benchmark_on_sample(
    sample: SampleMeta,
    *,
    use_mistral: bool = True,
) -> BenchmarkResult:
    """Run OCR on one sample and return a BenchmarkResult.

    DRY: reuses OCRService.process() exactly as test_ocr_service.py does.
    """
    service = OCRService()
    errors: list[str] = []
    start = time.perf_counter()

    if use_mistral:
        mock_response = _mock_mistral_response(sample.name)
        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_cls,
            patch(
                "app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock
            ) as mock_layout,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = True
            mock_settings.MISTRAL_API_KEY = "test-key"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client
            mock_layout.return_value = {}

            pages: list[OCRPage] = await service.process(sample.pdf_bytes, "application/pdf")
            path_used = "Mistral"
            fallback_correct: bool | str = "not_applicable"
    else:
        # Tesseract path — mock _process_tesseract directly (DRY: same as test_ocr_service.py)
        with (
            patch("app.services.ocr_service.settings") as mock_settings,
            patch("app.services.ocr_service._run_doclayout_analysis", new_callable=AsyncMock),
            patch.object(service, "_process_tesseract", new_callable=AsyncMock) as mock_tess,
        ):
            mock_settings.MISTRAL_OCR_ENABLED = False
            # Generate plausible Tesseract output from sample description
            tess_text = "" if "blank" in sample.name else f"[Tesseract] {sample.description[:80]}"
            mock_tess.return_value = [OCRPage(page=1, text=tess_text, confidence=None)]

            pages = await service.process(sample.pdf_bytes, "application/pdf")
            path_used = "Tesseract"
            fallback_correct = True

    elapsed_ms = (time.perf_counter() - start) * 1000

    # Collect results
    full_text = " ".join(p["text"] for p in pages)
    total_chars = len(full_text)
    confidences = [p["confidence"] for p in pages if p["confidence"] is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    # Quality heuristic — expected minimum chars based on sample
    expected_min_map: dict[str, int] = {
        "01_clean_english": 200,
        "02_low_quality_scan": 100,
        "03_german_legal": 150,
        "04_french_admin": 150,
        "05_table_data": 100,
        "06_handwriting_simulation": 80,
        "07_multi_column": 100,
        "08_mixed_languages": 100,
        "09_blank_page": 0,
        "10_multi_page": 200,
    }
    expected_min = expected_min_map.get(sample.name, 100)
    quality = _rate_quality(full_text, expected_min)

    # Error checks
    if sample.name == "09_blank_page" and full_text.strip():
        errors.append("Expected blank output but got text")
    if sample.name != "09_blank_page" and not full_text.strip():
        errors.append("Expected text but got empty output")
    if use_mistral and avg_confidence is None and sample.name != "09_blank_page":
        errors.append("Mistral path should return confidence scores")

    return BenchmarkResult(
        sample_name=sample.name,
        path_used=path_used,
        quality=quality,
        confidence=avg_confidence,
        fallback_correct=fallback_correct,
        time_ms=round(elapsed_ms, 2),
        pages=len(pages),
        total_chars=total_chars,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Live-mode Mistral OCR (uses real Cloudflare AI Gateway — production code path)
# ---------------------------------------------------------------------------


async def _run_benchmark_live(
    sample: SampleMeta,
) -> BenchmarkResult:
    """Run OCR through the production code path: Cloudflare AI Gateway → Mistral.

    DRY: calls service.process() with real settings, mocking only the
    non-blocking _run_doclayout_analysis. All other code (base64 encoding,
    gateway URL construction, payload building, response parsing) is the
    exact same code that runs in production — no URL bypass.
    """
    service = OCRService()
    errors: list[str] = []
    start = time.perf_counter()

    try:
        with patch(
            "app.services.ocr_service._run_doclayout_analysis",
            new_callable=AsyncMock,
            return_value={},
        ):
            pages: list[OCRPage] = await service.process(sample.pdf_bytes, "application/pdf")
        path_used = "Mistral (live)"
        fallback_correct: bool | str = "not_applicable"
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            sample_name=sample.name,
            path_used="Mistral (live)",
            quality=1,
            confidence=None,
            fallback_correct=False,
            time_ms=round(elapsed_ms, 2),
            pages=0,
            total_chars=0,
            errors=[f"Mistral API error: {exc}"],
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    full_text = " ".join(p["text"] for p in pages)
    total_chars = len(full_text)
    confidences = [p["confidence"] for p in pages if p["confidence"] is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    expected_min_map: dict[str, int] = {
        "01_clean_english": 200,
        "02_low_quality_scan": 100,
        "03_german_legal": 150,
        "04_french_admin": 150,
        "05_table_data": 100,
        "06_handwriting_simulation": 80,
        "07_multi_column": 100,
        "08_mixed_languages": 100,
        "09_blank_page": 0,
        "10_multi_page": 200,
    }
    expected_min = expected_min_map.get(sample.name, 100)
    quality = _rate_quality(full_text, expected_min)

    if sample.name == "09_blank_page" and full_text.strip():
        errors.append("Expected blank output but got text")
    if sample.name != "09_blank_page" and not full_text.strip():
        errors.append("Expected text but got empty output")

    return BenchmarkResult(
        sample_name=sample.name,
        path_used=path_used,
        quality=quality,
        confidence=avg_confidence,
        fallback_correct=fallback_correct,
        time_ms=round(elapsed_ms, 2),
        pages=len(pages),
        total_chars=total_chars,
        errors=errors,
    )


# ---------------------------------------------------------------------------


class TestOCRBenchmark:
    """OCR benchmark suite — Mistral path on all 10 synthetic samples."""

    @pytest.mark.asyncio
    async def test_benchmark_all_mistral(self) -> None:
        """Run all 10 samples through Mocked Mistral path."""
        samples = generate_all_samples()
        results: list[BenchmarkResult] = []
        for sample in samples:
            result = await _run_benchmark_on_sample(sample, use_mistral=True)
            results.append(result)
            # Assert basic correctness
            assert result.time_ms >= 0, f"{sample.name}: time must be non-negative"
            if sample.name != "09_blank_page":
                assert result.pages >= 1, f"{sample.name}: should have at least one page"
            assert result.quality >= 1, f"{sample.name}: quality must be 1-5"
            assert result.quality <= 5, f"{sample.name}: quality must be 1-5"

        # Summary checks
        total = len(results)
        high_quality = sum(1 for r in results if r.quality >= 4)
        assert high_quality >= total * 0.5, (
            f"At least 50% of samples should score quality >= 4, got {high_quality}/{total}"
        )

    @pytest.mark.asyncio
    async def test_benchmark_all_tesseract(self) -> None:
        """Run all 10 samples through Tesseract fallback path."""
        samples = generate_all_samples()
        results: list[BenchmarkResult] = []
        for sample in samples:
            result = await _run_benchmark_on_sample(sample, use_mistral=False)
            results.append(result)
            assert result.path_used == "Tesseract"
            assert result.confidence is None, "Tesseract should set confidence=None"

    @pytest.mark.asyncio
    async def test_blank_page_confidence_zero(self) -> None:
        """Blank page should have confidence near 0 via Mistral."""
        sample = [s for s in generate_all_samples() if s.name == "09_blank_page"][0]
        result = await _run_benchmark_on_sample(sample, use_mistral=True)
        assert result.quality == 1, "Blank page quality must be 1"
        assert result.confidence is not None and result.confidence < 0.1, (
            f"Blank page confidence should be near 0, got {result.confidence}"
        )

    @pytest.mark.asyncio
    async def test_multilingual_sample_has_substantial_text(self) -> None:
        """Multilingual sample should extract substantial text."""
        sample = [s for s in generate_all_samples() if s.name == "08_mixed_languages"][0]
        result = await _run_benchmark_on_sample(sample, use_mistral=True)
        assert result.quality >= 3, f"Multilingual sample quality: {result.quality}"
        assert result.total_chars > 20, "Multilingual sample should have meaningful text"

    @pytest.mark.asyncio
    async def test_multi_page_sample_page_count(self) -> None:
        """Five-page document should report 5 pages."""
        sample = [s for s in generate_all_samples() if s.name == "10_multi_page"][0]
        result = await _run_benchmark_on_sample(sample, use_mistral=True)
        assert result.pages == 5, f"Expected 5 pages, got {result.pages}"


# ---------------------------------------------------------------------------
# Live Mistral OCR benchmark (requires MISTRAL_API_KEY set in .env)
# Skipped in CI — REM-8 blocks direct provider URLs, gateway uses placeholders.
# ---------------------------------------------------------------------------


class TestOCRBenchmarkLive:
    """Live Mistral OCR benchmark — calls the real Mistral API.

    Prerequisites:
    - MISTRAL_API_KEY must be set in backend/.env
    - Run locally only (not in CI) — requires network + real API key
    """

    @pytest.mark.asyncio
    async def test_live_benchmark_all_samples(self) -> None:
        """Run all 10 synthetic samples through the live Mistral OCR API."""
        samples = generate_all_samples()
        results: list[BenchmarkResult] = []
        for sample in samples:
            result = await _run_benchmark_live(sample)
            results.append(result)
            assert result.time_ms > 0, f"{sample.name}: time must be positive"
            if sample.name != "09_blank_page":
                assert result.pages >= 1, f"{sample.name}: should have at least one page"
                assert result.total_chars > 0, f"{sample.name}: should extract text"
            assert result.quality >= 1, f"{sample.name}: quality must be 1-5"
            assert result.quality <= 5, f"{sample.name}: quality must be 1-5"

        total = len(results)
        successful = sum(1 for r in results if not r.errors)
        assert successful == total, (
            f"All {total} samples should succeed; errors: {[r.errors for r in results if r.errors]}"
        )

    @pytest.mark.asyncio
    async def test_live_blank_page_quality(self) -> None:
        """Blank page should produce minimal output via live Mistral."""
        sample = [s for s in generate_all_samples() if s.name == "09_blank_page"][0]
        result = await _run_benchmark_live(sample)
        assert result.total_chars <= 10, (
            f"Blank page should have minimal chars, got {result.total_chars}"
        )

    @pytest.mark.asyncio
    async def test_live_multi_page_count(self) -> None:
        """Five-page document must return exactly 5 pages via live Mistral."""
        sample = [s for s in generate_all_samples() if s.name == "10_multi_page"][0]
        result = await _run_benchmark_live(sample)
        assert result.pages == 5, f"Expected 5 pages, got {result.pages}"
        assert result.confidence is not None and result.confidence > 0.9, (
            f"Multi-page confidence should be high, got {result.confidence}"
        )


# ---------------------------------------------------------------------------
# Reducto 3-way benchmark (ADR-009: public corpus only -- local only)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Results table printer (DRY: one place, outputs ocr-benchmark.md table format)
# ---------------------------------------------------------------------------


def print_results_table(results: list[BenchmarkResult], title: str = "Benchmark Results") -> None:
    """Print benchmark results as a Markdown table to stdout.

    Output format matches docs/testing/ocr-benchmark.md table structure.
    """
    print(f"\n## {title}\n")
    print("| File | Quality (1–5) | Confidence | Time (ms) | Pages | Chars |")
    print("|------|---------------|------------|-----------|-------|-------|")
    total_time = 0.0
    total_confidence = 0.0
    count_with_confidence = 0
    for r in results:
        conf_str = f"{r.confidence:.4f}" if r.confidence is not None else "None"
        print(
            f"| {r.sample_name} | {r.quality} | {conf_str} | {r.time_ms:.0f} | {r.pages} | {r.total_chars} |"
        )
        total_time += r.time_ms
        if r.confidence is not None:
            total_confidence += r.confidence
            count_with_confidence += 1
    mean_time = total_time / len(results) if results else 0
    mean_conf = total_confidence / count_with_confidence if count_with_confidence else 0
    print(f"| **Mean** | | **{mean_conf:.4f}** | **{mean_time:.0f}** | | |")
    print()


# ---------------------------------------------------------------------------
# Disk-File Fixture Benchmark (parametrized — 10 individual tests)
# ---------------------------------------------------------------------------

# Resolve once at module load (safe: generate_all_disk_fixtures is deterministic)
_DISK_FIXTURES_BY_NAME = {f.name: f for f in generate_all_disk_fixtures()}
_DISK_FIXTURE_NAMES = sorted(_DISK_FIXTURES_BY_NAME.keys())


class TestOCRBenchmarkWithDiskFixtures:
    """OCR benchmark on disk-bound fixtures (10 parametrized tests + 1 Tesseract fallback).

    Fixtures can be persisted to disk via save_fixtures_to_disk() for
    manual validation. Tests run against in-memory generated versions
    (same content, no disk I/O required in CI).
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("fixture_name", _DISK_FIXTURE_NAMES)
    async def test_disk_fixture_mistral(self, fixture_name: str) -> None:
        """Run each of the 10 disk fixtures through mocked Mistral path.

        Records latency + confidence, asserts confidence > 0.5 for
        non-blank fixtures (or None for Tesseract-only fixtures).
        """
        sample = _DISK_FIXTURES_BY_NAME[fixture_name]
        result = await _run_benchmark_on_sample(sample, use_mistral=True)

        # Assert basic correctness
        assert result.time_ms >= 0, f"{fixture_name}: time must be non-negative"
        assert result.pages >= 0, f"{fixture_name}: page count must be non-negative"
        assert result.quality >= 1, f"{fixture_name}: quality must be 1-5"
        assert result.quality <= 5, f"{fixture_name}: quality must be 1-5"

        # Confidence assertion: > 0.5 for non-blank, near 0 for blank
        if fixture_name == "d10_blank_page":
            assert result.confidence is not None and result.confidence < 0.1, (
                f"Blank page confidence should be near 0, got {result.confidence}"
            )
        elif result.confidence is not None:
            assert result.confidence > 0.5, (
                f"{fixture_name}: confidence {result.confidence:.4f} should be > 0.5"
            )

        # Non-blank fixtures should extract some text
        if fixture_name != "d10_blank_page":
            assert result.total_chars > 0, (
                f"{fixture_name}: should extract text, got {result.total_chars} chars"
            )

    @pytest.mark.asyncio
    async def test_tesseract_fallback_all_fixtures(self) -> None:
        """Force MISTRAL_OCR_ENABLED=false, run all 10 through Tesseract path.

        Asserts: no crash, all results have text (except blank page),
        confidence is always None (Tesseract default).
        """
        all_fixtures = list(_DISK_FIXTURES_BY_NAME.values())
        results: list[BenchmarkResult] = []
        for sample in all_fixtures:
            result = await _run_benchmark_on_sample(sample, use_mistral=False)
            results.append(result)

            # Tesseract path assertions
            assert result.path_used == "Tesseract", (
                f"{sample.name}: should use Tesseract, got {result.path_used}"
            )
            assert result.confidence is None, (
                f"{sample.name}: Tesseract confidence should be None, got {result.confidence}"
            )

            if sample.name != "d10_blank_page":
                assert result.total_chars > 0, (
                    f"{sample.name}: Tesseract should extract text, got {result.total_chars} chars"
                )
            else:
                assert result.total_chars <= 10, (
                    f"Blank page should have minimal chars, got {result.total_chars}"
                )

        # Print results table after all assertions pass
        print_results_table(results, title="Tesseract Fallback — All 10 Disk Fixtures")


class TestReductoBenchmark3Way:
    """Reducto OCR benchmark -- calls the real Reducto API.

    Prerequisites:
    - REDUCTO_API_KEY must be set in backend/.env
    - Run locally only (not in CI) -- requires network + real API key
    - ADR-009: Reducto is NEVER used for user-uploaded documents.
      This benchmark validates the public-corpus-only path.
    """

    @pytest.mark.asyncio
    async def test_reducto_all_de_fr_mixed_samples(self) -> None:
        """Run all DE, FR, and mixed-language samples through Reducto.

        Validates: language detection, chunking (500-2000 chars), and
        that all samples return parseable content.
        """
        from reducto import Reducto  # type: ignore[import]

        samples = generate_all_samples()
        target = [s for s in samples if s.expected_language in ("de", "fr", "mixed")]
        assert len(target) >= 3, "Should have at least 3 DE/FR/mixed samples"

        import os
        from pathlib import Path

        key = os.getenv("REDUCTO_API_KEY", "")
        if not key:
            env_file = Path(__file__).resolve().parents[2] / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("REDUCTO_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break

        client = Reducto(api_key=key)
        results: list[dict[str, object]] = []

        for sample in target:
            start = time.perf_counter()
            try:
                upload = client.upload(file=BytesIO(sample.pdf_bytes))
                parse_result = client.parse.run(
                    input=upload,
                    retrieval={"chunking": {"chunk_mode": "variable"}},
                )
                elapsed_ms = (time.perf_counter() - start) * 1000

                chunks = parse_result.result.chunks if parse_result.result.chunks else []
                full_text = "\n\n".join(ch.content for ch in chunks)
                chunk_sizes = [len(ch.content) for ch in chunks]
                detected_lang = _detect_language(full_text)
                chunking_ok = all(500 <= cs <= 2000 for cs in chunk_sizes) if chunk_sizes else False

                results.append(
                    {
                        "name": sample.name,
                        "detected_lang": detected_lang,
                        "chunks": len(chunks),
                        "chunking_ok": chunking_ok,
                        "time_ms": round(elapsed_ms, 1),
                        "error": None,
                    }
                )

                assert len(chunks) > 0, f"{sample.name}: Reducto should return chunks"
                assert chunking_ok, (
                    f"{sample.name}: chunk sizes {chunk_sizes} must be 500-2000 chars"
                )
                if sample.expected_language == "mixed":
                    assert detected_lang in ("de", "fr"), (
                        f"{sample.name}: mixed should detect de or fr, got {detected_lang}"
                    )
                else:
                    assert detected_lang == sample.expected_language, (
                        f"{sample.name}: expected {sample.expected_language}, got {detected_lang}"
                    )
            except Exception as exc:
                results.append(
                    {
                        "name": sample.name,
                        "time_ms": round((time.perf_counter() - start) * 1000, 1),
                        "error": str(exc)[:200],
                    }
                )
                pytest.fail(f"{sample.name}: Reducto API error: {exc}")

        total = len(results)
        lang_ok = sum(
            1 for r in results if not r.get("error") and r.get("detected_lang") is not None
        )
        chunk_ok = sum(1 for r in results if r.get("chunking_ok"))
        assert lang_ok == total, f"Language detection: {lang_ok}/{total}"
        assert chunk_ok == total, f"Chunking validation: {chunk_ok}/{total}"

    @pytest.mark.asyncio
    async def test_reducto_not_used_for_user_uploads(self) -> None:
        """Verify Reducto is architecturally scoped to public corpus only.

        ADR-009: Reducto is NEVER imported in ocr_service.py or any user-facing
        endpoint. The seeding pipeline (scripts/seed_documents.py) is the only caller.
        """
        import ast
        from pathlib import Path

        ocr_service_path = (
            Path(__file__).resolve().parents[2] / "app" / "services" / "ocr_service.py"
        )
        source = ocr_service_path.read_text()
        tree = ast.parse(source)

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)

        reducto_refs = [i for i in imports if "reducto" in i.lower()]
        assert not reducto_refs, (
            f"ocr_service.py must NOT import Reducto (ADR-009). Found: {reducto_refs}"
            f"\nReducto belongs exclusively in scripts/seed_documents.py "
            f"for public EUR-Lex corpus parsing."
        )
