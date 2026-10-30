"""Provider-neutral routing metadata for PDF uploads."""

from typing import Literal

from pydantic import BaseModel


class PDFProcessingProfile(BaseModel):
    """Describe the available PDF translation product route."""

    route: Literal[
        "pdf_reference_translation",
        "document_understanding_translation",
    ] = "pdf_reference_translation"
    output_mode: Literal["reference", "extracted_text"] = "reference"
    layout_preserved: bool = True
    original_unchanged: Literal[True] = True
    form_filling_supported: Literal[False] = False
    is_fillable_form: bool = False

    @classmethod
    def document_understanding(cls) -> "PDFProcessingProfile":
        """Return the explicit extracted-text route used without BabelDOC."""
        return cls(
            route="document_understanding_translation",
            output_mode="extracted_text",
            layout_preserved=False,
        )
