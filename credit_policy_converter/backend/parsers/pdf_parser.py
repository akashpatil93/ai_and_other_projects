"""PDF document parser for credit policy documents using PyMuPDF."""
import re
from typing import List, Dict, Any


def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a PDF file and return text sections.
    Falls back to a single section if structure cannot be detected.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "PyMuPDF is required for PDF parsing. Install with: pip install PyMuPDF"
        )

    doc = fitz.open(file_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()

    if not full_text.strip():
        return []

    # Try to detect section boundaries by common heading patterns
    heading_pattern = re.compile(
        r'\n([A-Z][A-Z &/\-]{3,50})\n',
        re.MULTILINE,
    )

    splits: List[tuple] = [("Introduction", 0)]
    for match in heading_pattern.finditer(full_text):
        name = match.group(1).strip()
        # Filter out noise (all caps lines that are too long or too short)
        if 5 <= len(name) <= 60:
            splits.append((name, match.start()))

    sections = []
    for i, (name, start) in enumerate(splits):
        end = splits[i + 1][1] if i + 1 < len(splits) else len(full_text)
        text = full_text[start:end].strip()
        if text and len(text) > 80:
            sections.append({
                "name": name,
                "headers": ["Content"],
                "rows": [{"Content": text}],
                "text": f"=== {name} ===\n{text[:6000]}",
                "row_count": 1,
            })

    if not sections:
        # Single fallback section
        sections = [{
            "name": "Policy Document",
            "headers": ["Content"],
            "rows": [{"Content": full_text}],
            "text": f"=== Policy Document ===\n{full_text[:8000]}",
            "row_count": 1,
        }]

    return sections
