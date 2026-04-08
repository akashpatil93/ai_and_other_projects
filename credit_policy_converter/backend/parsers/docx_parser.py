"""
DOCX parser for credit policy documents.
Extracts tables and paragraphs, preserving section structure.
"""
from typing import Any, Dict, List

from docx import Document
from docx.table import Table


def _table_to_text(table: Table) -> str:
    """Convert a docx Table to a tab-separated text block."""
    lines = []
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        lines.append("\t".join(cells))
    return "\n".join(lines)


def _is_heading(para) -> bool:
    """True if a paragraph uses a Heading style."""
    return para.style and para.style.name.startswith("Heading")


def parse_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a DOCX file into sections.

    Each Heading-style paragraph starts a new section; table content and
    body paragraphs are accumulated into that section's text.
    """
    doc = Document(file_path)

    sections: List[Dict[str, Any]] = []
    current_name = "Document"
    current_lines: List[str] = []
    current_rows: List[Dict] = []
    header_row: List[str] = []
    found_first_heading = False

    def _flush():
        if not current_lines and not current_rows:
            return
        text = "\n".join(current_lines)
        sections.append(
            {
                "name": current_name,
                "headers": header_row[:],
                "rows": current_rows[:],
                "text": text[:8000],
                "row_count": len(current_rows),
            }
        )

    for block in doc.element.body:
        tag = block.tag.split("}")[-1]  # "p" or "tbl"

        if tag == "p":
            from docx.text.paragraph import Paragraph
            para = Paragraph(block, doc)
            text = para.text.strip()
            if not text:
                continue

            if _is_heading(para):
                if found_first_heading:
                    _flush()
                    current_lines = []
                    current_rows = []
                    header_row = []
                found_first_heading = True
                current_name = text
            else:
                current_lines.append(text)

        elif tag == "tbl":
            from docx.table import Table as DocxTable
            table = DocxTable(block, doc)
            rows = table.rows
            if not rows:
                continue

            # First row = header
            h = [c.text.strip() for c in rows[0].cells]
            if not header_row:
                header_row = h

            for row in rows[1:]:
                cells = [c.text.strip() for c in row.cells]
                row_dict = dict(zip(h, cells))
                current_rows.append(row_dict)
                current_lines.append("\t".join(cells))

    _flush()

    if not sections:
        # Fallback: whole document as one section
        full_text = "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        sections = [
            {
                "name": "Document",
                "headers": [],
                "rows": [],
                "text": full_text[:8000],
                "row_count": 0,
            }
        ]

    return sections
