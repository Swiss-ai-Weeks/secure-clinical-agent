"""Read page text from an uploaded PDF so it can be published as a note."""

from __future__ import annotations

import io


def looks_like_pdf(raw: bytes, filename: str, content_type: str) -> bool:
    name = (filename or "").lower()
    media = (content_type or "").split(";", 1)[0].strip().lower()
    return raw.startswith(b"%PDF-") or name.endswith(".pdf") or media == "application/pdf"


def extract_pdf_text(raw: bytes) -> str:
    """Return concatenated page text. Empty when the PDF has no readable text."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted and reader.decrypt("") == 0:
            return ""
        parts = [(page.extract_text() or "").strip() for page in reader.pages]
    except (PdfReadError, ValueError, TypeError):
        return ""
    return "\n".join(part for part in parts if part).strip()
