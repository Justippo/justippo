"""Runtime bridge from the sidecar HTTP contract to the BabelDOC CLI."""

from __future__ import annotations

import asyncio
import base64
import csv
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class BabelDocRuntimeError(Exception):
    """Base class for runtime failures mapped to ADR-012 envelopes."""

    error_code = "TRANSLATION_FAILED"


class BabelDocConfigError(BabelDocRuntimeError):
    """Raised when the sidecar is missing required runtime configuration."""

    error_code = "SERVICE_UNAVAILABLE"


class BabelDocInvalidInputError(BabelDocRuntimeError):
    """Raised when runtime options are malformed."""

    error_code = "INVALID_INPUT"


class BabelDocTimeoutError(BabelDocRuntimeError):
    """Raised when BabelDOC exceeds the request timeout."""

    error_code = "TIMEOUT"


class BabelDocOutputError(BabelDocRuntimeError):
    """Raised when BabelDOC exits without a translated PDF."""

    error_code = "TRANSLATION_FAILED"


@dataclass(frozen=True)
class BabelDocRuntimeResult:
    """Successful BabelDOC runtime output."""

    translated_b64: str
    source_lang: str
    target_lang: str
    detected_lang: str
    processing_time_ms: float
    layout_preserved: bool
    pages_processed: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BabelDocRuntimeConfig:
    """OpenAI-compatible backend settings consumed by BabelDOC."""

    openai_base_url: str
    openai_api_key: str
    openai_model: str


_ALLOWED_OPTIONS = {
    "qps",
    "max_pages",
    "watermark",
    "enhance_compatibility",
    "min_text_length",
}
_MAX_QPS = 16
_MAX_PAGES = 20
_MAX_MIN_TEXT_LENGTH = 20


def get_runtime_config() -> BabelDocRuntimeConfig:
    """Read the BabelDOC translation backend config from the environment."""
    base_url = os.environ.get("BABELDOC_OPENAI_BASE_URL", "").strip()
    api_key = os.environ.get("BABELDOC_OPENAI_API_KEY", "").strip()
    model = os.environ.get("BABELDOC_OPENAI_MODEL", "").strip()

    missing = [
        name
        for name, value in (
            ("BABELDOC_OPENAI_BASE_URL", base_url),
            ("BABELDOC_OPENAI_API_KEY", api_key),
            ("BABELDOC_OPENAI_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise BabelDocConfigError(
            "BabelDOC runtime is not configured; missing " + ", ".join(missing)
        )
    parsed_base_url = urlparse(base_url)
    _ALLOWED_HOSTNAMES = {"gateway.ai.cloudflare.com", "api.cloudflare.com"}
    if parsed_base_url.scheme != "https" or parsed_base_url.hostname not in _ALLOWED_HOSTNAMES:
        raise BabelDocConfigError(
            "BABELDOC_OPENAI_BASE_URL must point to Cloudflare AI Gateway "
            "(gateway.ai.cloudflare.com) or the Workers AI REST endpoint "
            "(api.cloudflare.com)"
        )

    return BabelDocRuntimeConfig(
        openai_base_url=base_url,
        openai_api_key=api_key,
        openai_model=model,
    )


async def run_babeldoc_translation(
    *,
    document: bytes,
    glossary_rows: list[dict[str, str]],
    source_lang: str,
    target_lang: str,
    preserve_layout: bool,
    timeout_seconds: int,
    options: dict[str, Any],
) -> BabelDocRuntimeResult:
    """Translate a PDF by invoking the BabelDOC CLI in an isolated temp dir."""
    config = get_runtime_config()
    start = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="evidenceeu-babeldoc-") as temp_dir:
        work_dir = Path(temp_dir)
        input_pdf = work_dir / "input.pdf"
        input_pdf.write_bytes(document)

        runtime_config_path = _write_runtime_config(config=config, work_dir=work_dir)

        glossary_path = _write_babeldoc_glossary(
            glossary_rows=glossary_rows,
            source_lang=source_lang,
            target_lang=target_lang,
            work_dir=work_dir,
        )

        command = _build_command(
            input_pdf=input_pdf,
            work_dir=work_dir,
            glossary_path=glossary_path,
            source_lang=source_lang,
            target_lang=target_lang,
            timeout_options=options,
            runtime_config_path=runtime_config_path,
        )

        await _run_command(command, timeout_seconds=timeout_seconds)
        output_pdf = _find_translated_pdf(work_dir=work_dir, input_pdf=input_pdf)
        translated_b64 = base64.b64encode(output_pdf.read_bytes()).decode("ascii")

    elapsed_ms = (time.perf_counter() - start) * 1000
    return BabelDocRuntimeResult(
        translated_b64=translated_b64,
        source_lang=source_lang,
        target_lang=target_lang,
        detected_lang=source_lang,
        processing_time_ms=elapsed_ms,
        layout_preserved=preserve_layout,
        pages_processed=int(options.get("max_pages") or 0),
        warnings=[],
    )


def _build_command(
    *,
    input_pdf: Path,
    work_dir: Path,
    glossary_path: Path | None,
    source_lang: str,
    target_lang: str,
    timeout_options: dict[str, Any],
    runtime_config_path: Path,
) -> list[str]:
    """Build a safe argv list for the BabelDOC CLI."""
    unknown_options = sorted(set(timeout_options) - _ALLOWED_OPTIONS)
    if unknown_options:
        raise BabelDocInvalidInputError(
            "unsupported BabelDOC options: " + ", ".join(unknown_options)
        )

    qps_value = timeout_options.get("qps", 4)
    if qps_value is None:
        qps_value = 4
    try:
        qps = int(qps_value)
    except (TypeError, ValueError) as exc:
        raise BabelDocInvalidInputError("options.qps must be an integer") from exc

    if qps < 1 or qps > _MAX_QPS:
        raise BabelDocInvalidInputError(f"options.qps must be between 1 and {_MAX_QPS}")

    watermark_value = timeout_options.get("watermark", False)
    if not isinstance(watermark_value, bool):
        raise BabelDocInvalidInputError("options.watermark must be a boolean")
    watermark = watermark_value

    enhance_compatibility = timeout_options.get("enhance_compatibility", True)
    if not isinstance(enhance_compatibility, bool):
        raise BabelDocInvalidInputError("options.enhance_compatibility must be a boolean")

    min_text_length_value = timeout_options.get("min_text_length", 2)
    try:
        min_text_length = int(min_text_length_value)
    except (TypeError, ValueError) as exc:
        raise BabelDocInvalidInputError("options.min_text_length must be an integer") from exc
    if min_text_length < 1 or min_text_length > _MAX_MIN_TEXT_LENGTH:
        raise BabelDocInvalidInputError(
            f"options.min_text_length must be between 1 and {_MAX_MIN_TEXT_LENGTH}"
        )

    output_dir = work_dir / "output"
    output_dir.mkdir(mode=0o700, exist_ok=True)

    command = [
        "babeldoc",
        "--config",
        str(runtime_config_path),
        "--files",
        str(input_pdf),
        "--lang-in",
        source_lang,
        "--lang-out",
        target_lang,
        "--working-dir",
        str(work_dir),
        "--output",
        str(output_dir),
        "--qps",
        str(qps),
        "--min-text-length",
        str(min_text_length),
        "--no-dual",
        "--watermark-output-mode",
        "watermarked" if watermark else "no_watermark",
    ]

    if enhance_compatibility:
        command.append("--enhance-compatibility")

    max_pages = timeout_options.get("max_pages")
    if max_pages is not None:
        try:
            max_pages_int = int(max_pages)
        except (TypeError, ValueError) as exc:
            raise BabelDocInvalidInputError("options.max_pages must be an integer") from exc
        if max_pages_int < 1 or max_pages_int > _MAX_PAGES:
            raise BabelDocInvalidInputError(f"options.max_pages must be between 1 and {_MAX_PAGES}")
        command.extend(["--pages", f"1-{max_pages_int}"])

    if glossary_path is not None:
        command.extend(["--glossary-files", str(glossary_path)])

    return command


def _write_runtime_config(
    *,
    config: BabelDocRuntimeConfig,
    work_dir: Path,
) -> Path:
    """Write secrets to a request-local config instead of subprocess argv."""
    config_path = work_dir / "babeldoc.toml"
    config_text = "\n".join(
        (
            "[babeldoc]",
            "openai = true",
            f"openai-model = {json.dumps(config.openai_model)}",
            f"openai-base-url = {json.dumps(config.openai_base_url)}",
            f"openai-api-key = {json.dumps(config.openai_api_key)}",
            "",
        )
    )
    config_path.write_text(config_text, encoding="utf-8")
    config_path.chmod(0o600)
    return config_path


def _write_babeldoc_glossary(
    *,
    glossary_rows: list[dict[str, str]],
    source_lang: str,
    target_lang: str,
    work_dir: Path,
) -> Path | None:
    """Convert EvidenceEU glossary rows to BabelDOC's source/target CSV format."""
    if not glossary_rows:
        return None

    source_column = f"term_{source_lang}"
    target_column = f"term_{target_lang}"
    glossary_path = work_dir / "glossary.csv"

    with glossary_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["source", "target", "tgt_lng"])
        writer.writeheader()
        for row in glossary_rows:
            writer.writerow(
                {
                    "source": row[source_column],
                    "target": row[target_column],
                    "tgt_lng": target_lang,
                }
            )

    return glossary_path


async def _run_command(command: list[str], *, timeout_seconds: int) -> None:
    """Run BabelDOC asynchronously and map failures without logging document bytes."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise BabelDocConfigError("BabelDOC executable is unavailable") from exc

    try:
        await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise BabelDocTimeoutError(f"BabelDOC processing exceeded {timeout_seconds}s") from exc

    if process.returncode != 0:
        raise BabelDocRuntimeError(f"BabelDOC exited with code {process.returncode}")


def _find_translated_pdf(*, work_dir: Path, input_pdf: Path) -> Path:
    """Locate the translated PDF generated by BabelDOC."""
    candidates = [path for path in work_dir.rglob("*.pdf") if path.resolve() != input_pdf.resolve()]
    if not candidates:
        raise BabelDocOutputError("BabelDOC completed but no translated PDF was produced")

    preferred = [
        path
        for path in candidates
        if any(token in path.name.lower() for token in ("mono", "translated", "no_watermark"))
    ]
    pool = preferred or candidates
    return max(pool, key=lambda path: path.stat().st_mtime)
