"""
Synthetic PDF Fixture Generator for OCR Benchmarking.

Generates 10 varied PDF samples in-memory (fpdf2) -- never writes to disk.
Each sample targets a specific OCR challenge: clean text, low quality,
multilingual, tables, handwriting simulation, etc.

DRY: reuses existing _FAKE_PDF_BYTES pattern from test_ocr_service.py
when appropriate; all generation is in-memory via BytesIO.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

import pypdfium2 as pdfium
from fpdf import FPDF
from PIL import Image, ImageEnhance, ImageFilter

# ---------------------------------------------------------------------------
# Scan simulation dependencies (pypdfium2 + Pillow)
# Both are in backend/pyproject.toml: Pillow>=10.3.0, pypdfium2>=4.30.0
# Used ONLY for disk-based fixture generation, never in CI in-memory path
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sample metadata
# ---------------------------------------------------------------------------


@dataclass
class SampleMeta:
    """Metadata for a single benchmark sample."""

    name: str
    description: str
    expected_language: str
    pdf_bytes: bytes
    challenges: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sample generators
# ---------------------------------------------------------------------------


def _make_blank() -> FPDF:
    """Return a new FPDF instance with default settings."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    return pdf


def sample_01_clean_english() -> SampleMeta:
    """Clean English single-page document -- baseline."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "EvidenceEU -- Multilingual Document Intelligence", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", size=10)
    text = (
        "This document is a clean English-language sample intended to establish "
        "a baseline OCR accuracy measurement. The text is well-formatted with "
        "standard margins, a single-column layout, and no images or tables. "
        "OCR systems should achieve near-perfect character-level accuracy on "
        "this sample under normal conditions.\n\n"
        "The European Union has established a comprehensive framework for "
        "cross-border recognition of public documents. Regulation (EU) 2016/1191 "
        "simplifies the circulation of certain public documents between Member "
        "States by abolishing the apostille requirement and introducing "
        "multilingual standard forms."
    )
    pdf.multi_cell(0, 5, text)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="01_clean_english",
        description="Clean English text, single page, standard formatting",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["baseline"],
    )


def sample_02_low_quality_scan() -> SampleMeta:
    """Simulated low-quality scan -- small font, light color, dense text."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=6)
    pdf.set_text_color(150, 150, 150)
    text = (
        "This text simulates a low-quality scanned document. The font is very "
        "small, the text color is light gray (low contrast), and the line "
        "spacing is minimal. OCR systems should struggle with character "
        "recognition on this sample.\n\n"
        "Paragraph two continues with dense formatting and minimal spacing "
        "between words. The challenge here is distinguishing individual "
        "characters when the resolution is poor and contrast is low. "
        "Common OCR errors on this type of input include confusing 'rn' with 'm', "
        "'cl' with 'd', and '1' with 'l' or 'I'."
    )
    pdf.multi_cell(0, 2, text)
    pdf.set_text_color(0, 0, 0)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="02_low_quality_scan",
        description="Tiny font (6pt), light gray text, minimal line spacing -- simulates poor scan",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["low_contrast", "small_font", "dense_text"],
    )


def sample_03_german_legal() -> SampleMeta:
    """German legal text -- umlauts, compound nouns, formal register."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 10, "Aufenthaltserlaubnis -- Bescheinigung gemass § 78a AufenthG", ln=True)
    pdf.ln(3)
    text = (
        "Die zustandige Auslanderbehorde bescheinigt hiermit, dass der "
        "Antragsteller gemass § 81 Abs. 3 des Aufenthaltsgesetzes (AufenthG) "
        "die Erteilung einer Aufenthaltserlaubnis beantragt hat. "
        "Bis zur Entscheidung uber den Antrag gilt der Aufenthalt als "
        "erlaubt. Diese Bescheinigung berechtigt nicht zur Ruckkehr in "
        "das Bundesgebiet.\n\n"
        "Die Gultigkeitsdauer dieser Fiktionsbescheinigung betragt "
        "sechs Monate ab Ausstellungsdatum. Eine Verlangerung ist unter "
        "den Voraussetzungen des § 81 Abs. 4 AufenthG moglich.\n\n"
        "Hinweis: Diese Übersetzung dient lediglich der Information. "
        "Rechtlich verbindlich ist ausschliesslich der deutsche Originaltext."
    )
    pdf.multi_cell(0, 5, text)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="03_german_legal",
        description="German legal text with umlauts, compound nouns, formal register",
        expected_language="de",
        pdf_bytes=buf.getvalue(),
        challenges=["umlauts", "compound_nouns", "legal_terminology"],
    )


def sample_04_french_admin() -> SampleMeta:
    """French administrative text -- accents, formal register."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 10, "Attestation de residence -- Prefecture de Paris", ln=True)
    pdf.ln(3)
    text = (
        "Vu le Code de l'entree et du sejour des etrangers et du droit "
        "d'asile (CESEDA), la presente attestation certifie que le "
        "demandeur a depose une demande de titre de sejour aupres de "
        "la prefecture competente.\n\n"
        "Le recepisse de demande de carte de sejour est valable pour "
        "une duree de trois mois a compter de sa date de delivrance. "
        "Il est renouvelable sur presentation de l'ancien recepisse.\n\n"
        "Des reception de cette attestation, le demandeur est prie de "
        "verifier l'exactitude des informations suivantes : nom, prenom, "
        "date et lieu de naissance, nationalite, adresse."
    )
    pdf.multi_cell(0, 5, text)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="04_french_admin",
        description="French administrative text with accents (e, e, e, c, a, u)",
        expected_language="fr",
        pdf_bytes=buf.getvalue(),
        challenges=["accents", "formal_register", "administrative"],
    )


def sample_05_table_data() -> SampleMeta:
    """Document with tabular data -- columns, rows, numbers."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Quarterly Report -- Q1 2026", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", size=9)
    # Table header
    col_widths = [50, 35, 35, 35, 35]
    headers = ["Country", "Applications", "Approved", "Rejected", "Pending"]
    for w, h in zip(col_widths, headers, strict=True):
        pdf.cell(w, 7, h, border=1, align="C")
    pdf.ln()
    # Table rows
    rows = [
        ["Germany", "12,450", "10,200", "1,800", "450"],
        ["France", "8,920", "7,100", "1,500", "320"],
        ["Italy", "6,340", "4,800", "1,200", "340"],
        ["Netherlands", "3,210", "2,900", "210", "100"],
        ["Belgium", "2,890", "2,500", "280", "110"],
    ]
    for row in rows:
        for w, cell in zip(col_widths, row, strict=True):
            pdf.cell(w, 6, cell, border=1, align="C")
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 5, "Source: European Migration Network, March 2026", ln=True)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="05_table_data",
        description="Tabular data with column headers and numeric values",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["tables", "numbers", "column_alignment"],
    )


def sample_06_handwriting_simulation() -> SampleMeta:
    """Italic text simulating handwriting style."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", style="I", size=14)
    text = (
        "This text is rendered in italic font to simulate the appearance "
        "of handwritten or cursive script. OCR systems often perform "
        "significantly worse on italic text because character shapes "
        "deviate from their standard forms.\n\n"
        "The quick brown fox jumps over the lazy dog.\n"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ\n"
        "abcdefghijklmnopqrstuvwxyz\n"
        "0123456789 !@#$%^&*()"
    )
    pdf.multi_cell(0, 6, text)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="06_handwriting_simulation",
        description="Italic text simulating handwriting -- tests cursive/script recognition",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["italic", "handwriting", "character_variants"],
    )


def sample_07_multi_column() -> SampleMeta:
    """Two-column layout -- common in EU official journals."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    # Left column
    x_left = 10
    x_right = 110
    y_start = pdf.get_y()
    pdf.set_xy(x_left, y_start)
    pdf.multi_cell(
        90,
        4,
        (
            "COLUMN ONE: This text appears in the left column of a "
            "two-column layout. Multi-column documents are common in "
            "EU official journals and legal gazettes. OCR systems must "
            "correctly identify column boundaries and preserve reading "
            "order across the page."
        ),
        border=0,
    )
    # Right column -- same Y start
    pdf.set_xy(x_right, y_start)
    pdf.multi_cell(
        90,
        4,
        (
            "COLUMN TWO: The right column contains separate content that "
            "should not be merged with the left column during extraction. "
            "Cross-column text bleeding is a major source of OCR errors "
            "in legal document processing."
        ),
        border=0,
    )
    pdf.ln(10)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 5, "(End of two-column section -- returns to single column)", ln=True)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="07_multi_column",
        description="Two-column layout -- tests column boundary detection",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["multi_column", "reading_order", "layout_preservation"],
    )


def sample_08_mixed_languages() -> SampleMeta:
    """Mixed EN/DE/FR document -- tests language detection and mixed OCR."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 8, "Trilingual Document -- EN / DE / FR", ln=True, align="C")
    pdf.ln(3)
    sections = [
        (
            "English Section",
            (
                "This section is written in English. The OCR system should "
                "correctly identify the language and extract text with "
                "appropriate character sets. English uses the basic Latin "
                "alphabet without diacritical marks."
            ),
        ),
        (
            "Deutscher Abschnitt",
            (
                "Dieser Abschnitt ist auf Deutsch verfasst. Die Umlaute a, o, u "
                "und das Eszett ss mussen korrekt erkannt werden. Auch die "
                "Gross- und Kleinschreibung der Substantive ist wichtig."
            ),
        ),
        (
            "Section francaise",
            (
                "Cette section est redigee en francais. Les accents aigus (e), "
                "graves (e, a, u), circonflexes (e, a, i, o, u) et la cedille (c) "
                "doivent tous etre correctement reconnus par le systeme d'OCR."
            ),
        ),
    ]
    for title, body in sections:
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.cell(0, 6, title, ln=True)
        pdf.set_font("Helvetica", style="", size=10)
        pdf.multi_cell(0, 4, body)
        pdf.ln(2)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="08_mixed_languages",
        description="Single document with EN, DE, and FR sections -- tests multilingual OCR",
        expected_language="mixed",
        pdf_bytes=buf.getvalue(),
        challenges=["multilingual", "language_boundaries", "diacritics"],
    )


def sample_09_blank_page() -> SampleMeta:
    """Single blank page -- edge case."""
    pdf = _make_blank()
    pdf.add_page()
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="09_blank_page",
        description="Single blank page -- edge case for OCR confidence handling",
        expected_language="none",
        pdf_bytes=buf.getvalue(),
        challenges=["blank", "empty_output", "confidence_floor"],
    )


def sample_10_multi_page() -> SampleMeta:
    """Five-page document with varying content per page."""
    pdf = _make_blank()
    titles = [
        "Page 1: Introduction",
        "Page 2: Background and Context",
        "Page 3: Methodology",
        "Page 4: Results and Analysis",
        "Page 5: Conclusions and Recommendations",
    ]
    bodies = [
        "This document provides a comprehensive overview of the EvidenceEU "
        "project. It covers the motivation, design decisions, implementation "
        "details, and future roadmap for multilingual document intelligence "
        "in cross-border European contexts.",
        "The European Union's single market enables free movement of people, "
        "goods, services, and capital. However, cross-border document "
        "recognition remains fragmented. Citizens moving between Member States "
        "face bureaucratic hurdles requiring certified translations of birth "
        "certificates, marriage licenses, diplomas, and other public documents.",
        "The EvidenceEU platform uses a hybrid architecture combining "
        "Cloudflare Workers for edge computing, FastAPI for backend services, "
        "and a multi-engine OCR pipeline (Mistral primary, Tesseract fallback) "
        "for document text extraction. Translation is handled via Cloudflare "
        "Workers AI and BabelDOC for layout preservation.",
        "Preliminary results show 97% character-level accuracy on clean "
        "English documents using Mistral OCR, with Tesseract achieving 92% "
        "on the same corpus. German documents show slightly lower accuracy "
        "(94% Mistral, 88% Tesseract) due to compound noun complexity.",
        "Future work includes integrating Matrix protocol for secure "
        "cross-border document exchange, expanding the corpus to 500+ EU "
        "public documents, and developing a commercial tier with Doclingo "
        "for production-quality layout-preserving translation.",
    ]
    for _i, (title, body) in enumerate(zip(titles, bodies, strict=True)):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, title, ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, body)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="10_multi_page",
        description="Five-page document with varying content",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["multi_page", "content_variety"],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_SAMPLE_GENERATORS = [
    sample_01_clean_english,
    sample_02_low_quality_scan,
    sample_03_german_legal,
    sample_04_french_admin,
    sample_05_table_data,
    sample_06_handwriting_simulation,
    sample_07_multi_column,
    sample_08_mixed_languages,
    sample_09_blank_page,
    sample_10_multi_page,
]


def generate_all_samples() -> list[SampleMeta]:
    """Generate all 10 benchmark samples in-memory.

    DRY: each generator function creates its own fpdf instance and
    returns a SampleMeta with the PDF bytes. No disk writes anywhere.
    """
    return [gen() for gen in _SAMPLE_GENERATORS]


def get_sample_bytes(name: str) -> bytes:
    """Return PDF bytes for a named sample (looked up by SampleMeta.name)."""
    for meta in generate_all_samples():
        if meta.name == name:
            return meta.pdf_bytes
    raise KeyError(f"Sample '{name}' not found in generated fixtures")


# ---------------------------------------------------------------------------
# Scan Simulation Pipeline (pypdfium2 → PIL → degrade → fpdf2 re-encode)
#
# Round-trip: fpdf2 clean PDF → pypdfium2 render to PIL Image → Pillow
# degradation (blur, DPI reduction, noise) → fpdf2 embed image as new PDF.
# Used ONLY for disk-based "scanned quality" fixtures (CI in-memory path
# never calls these — works with the existing clean fpdf2 samples).
#
# ß/Unicode constraint: re.IGNORECASE does not handle ß → SS case folding
# (ß.upper() == 'SS', but 'SS'.lower() is 'ss' not 'ß'). Test cases
# deliberately use ä/ö/ü but NEVER ß — cross-reference translation QA task.
# ---------------------------------------------------------------------------


def _rasterize_pdf_to_image(pdf_bytes: bytes, *, scale: float = 2.0) -> Image.Image:
    """Rasterize the first page of a PDF to a PIL Image via pypdfium2.

    Args:
        pdf_bytes: PDF file contents as bytes.
        scale: Render scale factor (1.0 = 72 DPI equivalent, 2.0 = 144 DPI).

    Returns:
        PIL Image in RGB mode.
    """
    pdf = pdfium.PdfDocument(pdf_bytes)
    page = pdf[0]  # first page only
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil().convert("RGB")
    page.close()
    pdf.close()
    return pil_image


def _degrade_image(
    image: Image.Image,
    *,
    target_dpi: int = 72,
    blur_radius: float = 1.5,
    noise_factor: float = 0.05,
    contrast_factor: float = 0.85,
    brightness_factor: float = 0.9,
) -> Image.Image:
    """Apply scanner-like degradation to a PIL Image.

    Simulates: low DPI rescaling, Gaussian blur, reduced contrast/brightness,
    and salt-and-pepper noise (random pixel corruption).

    Args:
        image: PIL Image to degrade.
        target_dpi: Approximate DPI to resize to (relative to 72 DPI base).
        blur_radius: GaussianBlur sigma radius (higher = more blur).
        noise_factor: Fraction of pixels to corrupt with noise (0.0–1.0).
        contrast_factor: ImageEnhance.Contrast factor (0.0 = solid gray, 1.0 = original).
        brightness_factor: ImageEnhance.Brightness factor (0.0 = black, 1.0 = original).

    Returns:
        Degraded PIL Image in RGB mode.
    """
    # DPI simulation: resize down from render scale (assumes 144 DPI input from scale=2.0)
    orig_w, orig_h = image.size
    scale_factor = target_dpi / 144.0
    new_w = max(1, int(orig_w * scale_factor))
    new_h = max(1, int(orig_h * scale_factor))
    degraded = image.resize((new_w, new_h), Image.LANCZOS)

    # Blur: simulate scanner optics imperfections
    degraded = degraded.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Contrast and brightness reduction
    degraded = ImageEnhance.Contrast(degraded).enhance(contrast_factor)
    degraded = ImageEnhance.Brightness(degraded).enhance(brightness_factor)

    # Salt-and-pepper noise: random pixel corruption
    if noise_factor > 0:
        pixels = degraded.load()
        assert pixels is not None
        for y in range(degraded.height):
            for x in range(degraded.width):
                if random.random() < noise_factor:
                    # Randomly set to black or white
                    pixels[x, y] = (0, 0, 0) if random.random() < 0.5 else (255, 255, 255)

    return degraded


def _image_to_pdf_bytes(image: Image.Image) -> bytes:
    """Re-encode a PIL Image as a single-page PDF via fpdf2.

    Args:
        image: PIL Image to embed.

    Returns:
        PDF file contents as bytes.
    """
    pdf = FPDF(unit="pt")
    # Match PDF page size to image dimensions at 72 DPI
    img_w, img_h = image.size
    pdf.add_page(format=(img_w, img_h))

    # Save image to in-memory buffer for fpdf2 embedding
    img_buf = BytesIO()
    image.save(img_buf, format="PNG")
    img_buf.seek(0)

    pdf.image(img_buf, x=0, y=0, w=img_w, h=img_h, type="PNG")
    out_buf = BytesIO()
    pdf.output(out_buf)
    return out_buf.getvalue()


def generate_scan_simulation(
    clean_pdf_bytes: bytes,
    *,
    dpi: int = 72,
    blur_radius: float = 1.5,
    noise_factor: float = 0.05,
) -> bytes:
    """Full scan-simulation round-trip: clean PDF → rasterize → degrade → re-encode to PDF.

    This is the main entry point for creating "scanned quality" fixtures.
    Preserves existing in-memory generation — never writes to disk.

    Args:
        clean_pdf_bytes: A clean fpdf2-generated PDF as bytes.
        dpi: Target DPI for degradation (default 72 = low-quality scan).
        blur_radius: GaussianBlur sigma radius.
        noise_factor: Fraction of pixels corrupted with noise.

    Returns:
        Degraded PDF as bytes.
    """
    image = _rasterize_pdf_to_image(clean_pdf_bytes)
    degraded = _degrade_image(
        image, target_dpi=dpi, blur_radius=blur_radius, noise_factor=noise_factor
    )
    return _image_to_pdf_bytes(degraded)


# ---------------------------------------------------------------------------
# New sample generators for disk-based 10-fixture set
# These extend the existing 10 in-memory samples (not replace them).
# Naming matches the user-specified 10-fixture list (01–10).
# ---------------------------------------------------------------------------


def sample_d01_clean_en_legal() -> SampleMeta:
    """Disk fixture 01: Clean English legal text (single page)."""
    return sample_01_clean_english()


def sample_d02_clean_de_legal() -> SampleMeta:
    """Disk fixture 02: Clean German legal text (ä/ö/ü but NOT ß — see ß constraint doc).

    ß constraint: re.IGNORECASE does not handle ß → SS case folding
    (ß.upper() == 'SS', but 'SS'.lower() is 'ss' not 'ß').
    Test cases deliberately avoid ß — cross-reference translation QA task.
    """
    return sample_03_german_legal()


def sample_d03_clean_fr_admin() -> SampleMeta:
    """Disk fixture 03: Clean French administrative text (é/è/ê accents)."""
    return sample_04_french_admin()


def sample_d04_low_quality_scan() -> SampleMeta:
    """Disk fixture 04: Low-quality scan simulation (blur, 72 DPI, noise).

    Round-trip: clean EN sample → pypdfium2 render → Pillow degrade → re-encode.
    """
    clean_bytes = sample_01_clean_english().pdf_bytes
    degraded_bytes = generate_scan_simulation(
        clean_bytes, dpi=72, blur_radius=1.5, noise_factor=0.05
    )
    return SampleMeta(
        name="d04_low_quality_scan",
        description="Low-quality scan simulation: 72 DPI, Gaussian blur (1.5σ), 5% noise",
        expected_language="en",
        pdf_bytes=degraded_bytes,
        challenges=["low_dpi", "blur", "noise", "scan_simulation"],
    )


def sample_d05_table_3col_5row() -> SampleMeta:
    """Disk fixture 05: Table with 3 columns and 5 rows (EN)."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Cross-Border Document Types -- EU Overview", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", size=9)
    col_widths = [60, 60, 60]
    headers = ["Document Type", "Authority", "Validity"]
    for w, h in zip(col_widths, headers, strict=True):
        pdf.cell(w, 7, h, border=1, align="C")
    pdf.ln()
    rows = [
        ["Birth Certificate", "Civil Registry", "10 years"],
        ["Marriage License", "Municipal Office", "6 months"],
        ["Diploma", "University", "Unlimited"],
        ["Criminal Record", "Ministry of Justice", "3 months"],
        ["Residence Permit", "Immigration Office", "1-5 years"],
    ]
    for row in rows:
        for w, cell in zip(col_widths, row, strict=True):
            pdf.cell(w, 6, cell, border=1, align="C")
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 5, "Source: EU e-Justice Portal, 2026", ln=True)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="d05_table_3col_5row",
        description="Table: 3 columns (Document Type, Authority, Validity), 5 rows — EN",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["tables", "columns", "structured_data"],
    )


def sample_d06_multipage_3pg() -> SampleMeta:
    """Disk fixture 06: Multi-page document with 3 pages (EN)."""
    pdf = _make_blank()
    titles = [
        "Page 1: Introduction to Cross-Border Documents",
        "Page 2: Legal Framework",
        "Page 3: Practical Guidance",
    ]
    bodies = [
        (
            "Cross-border document recognition is a cornerstone of the European "
            "Union's single market. Citizens moving between Member States require "
            "reliable recognition of their public documents -- birth certificates, "
            "marriage licenses, diplomas, and criminal records."
        ),
        (
            "Regulation (EU) 2016/1191 simplifies the circulation of certain "
            "public documents between Member States. It abolishes the apostille "
            "requirement and introduces multilingual standard forms for birth, "
            "death, marriage, registered partnership, and other key documents."
        ),
        (
            "To obtain a multilingual standard form, visit the issuing authority "
            "in your country of residence. The form is available in all EU "
            "languages and does not require translation. Processing time varies "
            "by Member State but typically takes 5-15 working days."
        ),
    ]
    for title, body in zip(titles, bodies, strict=True):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, title, ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, body)
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="d06_multipage_3pg",
        description="Multi-page: 3 pages of EN legal/administrative text",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["multi_page", "pagination", "cross_page_flow"],
    )


def sample_d07_mixed_en_de() -> SampleMeta:
    """Disk fixture 07: Mixed English/German content (2 sections, no FR for clarity)."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Bilingual Document -- EN / DE", ln=True, align="C")
    pdf.ln(5)
    # English section
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(0, 6, "English Section", ln=True)
    pdf.set_font("Helvetica", style="", size=10)
    pdf.multi_cell(
        0,
        5,
        (
            "This certificate confirms that the applicant has submitted a "
            "complete application for a residence permit. The processing time "
            "is approximately four to six weeks from the date of submission. "
            "The applicant is authorized to remain in the country during the "
            "pendency of the application."
        ),
    )
    pdf.ln(3)
    # German section
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(0, 6, "Deutscher Abschnitt", ln=True)
    pdf.set_font("Helvetica", style="", size=10)
    pdf.multi_cell(
        0,
        5,
        (
            "Diese Bescheinigung bestatigt, dass der Antragsteller einen "
            "vollstandigen Antrag auf Erteilung einer Aufenthaltserlaubnis "
            "eingereicht hat. Die Bearbeitungsdauer betragt etwa vier bis "
            "sechs Wochen ab dem Datum der Antragstellung. Der Antragsteller "
            "ist berechtigt, wahrend der Anhangigkeit des Antrags im Land "
            "zu verbleiben. Die zustandige Auslanderbehorde wird den "
            "Antragsteller schriftlich uber die Entscheidung informieren."
        ),
    )
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="d07_mixed_en_de",
        description="Mixed EN/DE content: two sections with language switch",
        expected_language="mixed",
        pdf_bytes=buf.getvalue(),
        challenges=["multilingual", "language_boundaries", "umlauts"],
    )


def sample_d08_bold_italic_heavy() -> SampleMeta:
    """Disk fixture 08: Heavy bold/italic formatting throughout."""
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, "Formatted Document -- Bold & Italic Heavy", ln=True, align="C")
    pdf.ln(5)
    # Bold section
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.multi_cell(
        0,
        5,
        "THIS SECTION IS RENDERED ENTIRELY IN BOLD TYPEFACE. The purpose is to test OCR recognition of bold-formatted legal text, which is commonly used for headings, emphasis, and key clauses in official documents.",
    )
    pdf.ln(3)
    # Italic section
    pdf.set_font("Helvetica", style="I", size=11)
    pdf.multi_cell(
        0,
        5,
        "This section is rendered entirely in italic typeface. Italic text presents a significant challenge for OCR systems because the character shapes deviate from their standard upright forms, making individual character recognition more difficult.",
    )
    pdf.ln(3)
    # Bold+Italic section
    pdf.set_font("Helvetica", style="BI", size=11)
    pdf.multi_cell(
        0,
        5,
        "This section combines both bold and italic styling simultaneously. Double-emphasized text is less common but appears in certain legal documents for critical warnings or disclaimers that require maximum visual prominence.",
    )
    pdf.ln(3)
    # Mixed inline
    pdf.set_font("Helvetica", size=10)
    pdf.write(5, "The ")
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.write(5, "quick brown fox")
    pdf.set_font("Helvetica", size=10)
    pdf.write(5, " jumps over the ")
    pdf.set_font("Helvetica", style="I", size=10)
    pdf.write(5, "lazy dog")
    pdf.set_font("Helvetica", size=10)
    pdf.write(5, ". This sentence tests inline formatting transitions.")
    buf = BytesIO()
    pdf.output(buf)
    return SampleMeta(
        name="d08_bold_italic_heavy",
        description="Heavy bold, italic, and bold-italic formatting throughout",
        expected_language="en",
        pdf_bytes=buf.getvalue(),
        challenges=["bold", "italic", "mixed_styles", "inline_formatting"],
    )


def sample_d09_handwriting_simulation() -> SampleMeta:
    """Disk fixture 09: Handwriting simulation (degraded italic + heavy noise).

    APPROXIMATION DISCLAIMER: True handwriting OCR requires a handwritten font
    or actual handwriting samples. This fixture approximates the challenge by:
    1. Rendering italic text (cursive-like character shapes)
    2. Running full scan simulation pipeline (rasterize → degrade → re-encode)
    3. Adding extra noise (7% vs standard 5%) and heavier blur (2.0σ vs 1.5σ)
    to simulate the irregularity of handwriting.

    This is NOT a replacement for real handwriting OCR testing. It validates
    that the OCR pipeline degrades gracefully with cursive+noise input.
    """
    # Build clean italic PDF
    pdf = _make_blank()
    pdf.add_page()
    pdf.set_font("Helvetica", style="I", size=14)
    text = (
        "This text simulates the appearance of handwritten script. The quick "
        "brown fox jumps over the lazy dog. ABCDEFGHIJKLMNOPQRSTUVWXYZ "
        "abcdefghijklmnopqrstuvwxyz 0123456789. Cursive recognition is one "
        "of the most challenging problems in optical character recognition "
        "because character shapes vary significantly between individuals and "
        "writing styles."
    )
    pdf.multi_cell(0, 6, text)
    clean_buf = BytesIO()
    pdf.output(clean_buf)

    # Degrade more aggressively than standard scan simulation
    degraded_bytes = generate_scan_simulation(
        clean_buf.getvalue(),
        dpi=72,
        blur_radius=2.0,
        noise_factor=0.07,
    )
    return SampleMeta(
        name="d09_handwriting_simulation",
        description="Handwriting approximation: italic text + heavy scan degradation (2.0σ blur, 7% noise)",
        expected_language="en",
        pdf_bytes=degraded_bytes,
        challenges=["handwriting", "cursive", "heavy_noise", "heavy_blur", "italic"],
    )


def sample_d10_blank_page() -> SampleMeta:
    """Disk fixture 10: Blank page (edge case — confirms fixture file exists on disk)."""
    return SampleMeta(
        name="d10_blank_page",
        description="Single blank page — edge case for OCR confidence handling",
        expected_language="none",
        pdf_bytes=sample_09_blank_page().pdf_bytes,
        challenges=["blank", "empty_output", "confidence_floor"],
    )


# ---------------------------------------------------------------------------
# Disk fixture registry (10 fixtures for the new benchmark set)
# ---------------------------------------------------------------------------

_DISK_SAMPLE_GENERATORS = [
    sample_d01_clean_en_legal,
    sample_d02_clean_de_legal,
    sample_d03_clean_fr_admin,
    sample_d04_low_quality_scan,
    sample_d05_table_3col_5row,
    sample_d06_multipage_3pg,
    sample_d07_mixed_en_de,
    sample_d08_bold_italic_heavy,
    sample_d09_handwriting_simulation,
    sample_d10_blank_page,
]


def generate_all_disk_fixtures() -> list[SampleMeta]:
    """Generate all 10 disk-bound benchmark samples.

    DRY: reuses existing clean sample generators where possible (d01→sample_01,
    d02→sample_03, d03→sample_04, d10→sample_09). Scan-simulated fixtures
    (d04, d09) use the round-trip pipeline. All others are new fpdf2 generators.
    """
    return [gen() for gen in _DISK_SAMPLE_GENERATORS]


def save_fixtures_to_disk(output_dir: Path) -> list[Path]:
    """Write all 10 disk fixtures as .pdf files to the given directory.

    Creates the directory if it doesn't exist. Returns the list of
    written file paths, sorted by fixture name.

    GDPR note: fixtures are test-only synthetic data, never user data —
    safe to commit to repo.

    Args:
        output_dir: Directory to write fixture PDFs into.

    Returns:
        List of written Path objects.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    fixtures = generate_all_disk_fixtures()
    for fixture in fixtures:
        file_path = output_dir / f"{fixture.name}.pdf"
        file_path.write_bytes(fixture.pdf_bytes)
        written.append(file_path)
    return sorted(written)
