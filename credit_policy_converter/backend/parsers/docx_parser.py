"""
DOCX parser for credit policy documents.
Extracts tables and paragraphs, preserving section structure.

Splitting strategy (tried in order, first one that produces >1 section wins):
  1. "Rule set name:" paragraph lines  → one section per ruleset
  2. Heading-style paragraphs          → one section per heading
  3. Entire document as one section    → last resort
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.table import Table

_RULESET_PAT = re.compile(
    r'Rule\s+set\s+name\s*[:\-]\s*(.+)',
    re.IGNORECASE,
)


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


def _make_section(name: str, lines: List[str]) -> Optional[Dict[str, Any]]:
    """Build a section dict from a list of text lines, or None if too short."""
    text = "\n".join(lines).strip()
    if not text or len(text) < 40:
        return None
    return {
        "name": name,
        "headers": ["Content"],
        "rows": [{"Content": text}],
        "text": f"=== {name} ===\n{text[:8000]}",
        "row_count": 1,
    }


def _collect_blocks(doc) -> List[Tuple[str, str]]:
    """
    Return a list of (block_type, text) for every paragraph and table
    in document order.  block_type is "p" or "tbl".
    """
    blocks: List[Tuple[str, str]] = []
    for block in doc.element.body:
        tag = block.tag.split("}")[-1]
        if tag == "p":
            from docx.text.paragraph import Paragraph
            para = Paragraph(block, doc)
            text = para.text.strip()
            if text:
                blocks.append(("p", text))
        elif tag == "tbl":
            from docx.table import Table as DocxTable
            table = DocxTable(block, doc)
            text = _table_to_text(table).strip()
            if text:
                blocks.append(("tbl", text))
    return blocks


def _split_by_ruleset_name(blocks: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """
    Split on paragraphs that match 'Rule set name: <name>'.
    Returns sections or [] if pattern not found.
    """
    splits: List[Tuple[str, int]] = []
    for i, (btype, text) in enumerate(blocks):
        if btype == "p":
            m = _RULESET_PAT.search(text)
            if m:
                rs_name = m.group(1).strip().rstrip("*")
                if rs_name:
                    splits.append((rs_name, i))

    if not splits:
        return []

    sections: List[Dict[str, Any]] = []

    # Everything before first marker → preamble (pre_read / metadata)
    preamble_lines = [text for _, text in blocks[: splits[0][1]]]
    if preamble_lines and len("\n".join(preamble_lines)) > 80:
        sec = _make_section("Input Payload", preamble_lines)
        if sec:
            sections.append(sec)

    for i, (name, start_idx) in enumerate(splits):
        end_idx = splits[i + 1][1] if i + 1 < len(splits) else len(blocks)
        lines = [text for _, text in blocks[start_idx:end_idx]]
        sec = _make_section(name, lines)
        if sec:
            sections.append(sec)

    return sections


def _split_by_headings(doc) -> List[Dict[str, Any]]:
    """
    Original strategy: split on Heading-style paragraphs.
    Tables and body paragraphs accumulate into the current section.
    """
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
        sections.append({
            "name": current_name,
            "headers": header_row[:],
            "rows": current_rows[:],
            "text": text[:8000],
            "row_count": len(current_rows),
        })

    for block in doc.element.body:
        tag = block.tag.split("}")[-1]

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

            h = [c.text.strip() for c in rows[0].cells]
            if not header_row:
                header_row = h

            for row in rows[1:]:
                cells = [c.text.strip() for c in row.cells]
                row_dict = dict(zip(h, cells))
                current_rows.append(row_dict)
                current_lines.append("\t".join(cells))

    _flush()
    return sections


def parse_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a DOCX file into named sections.

    Splitting strategy (tried in order, first one that produces >1 section wins):
      1. "Rule set name:" paragraph lines
      2. Heading-style paragraphs
      3. Entire document as one section (fallback)
    """
    doc = Document(file_path)

    # Strategy 1: "Rule set name:" lines
    blocks = _collect_blocks(doc)
    sections = _split_by_ruleset_name(blocks)
    if sections:
        return sections

    # Strategy 2: Heading-based splitting
    sections = _split_by_headings(doc)
    if sections:
        return sections

    # Strategy 3: Whole document as one section
    full_text = "\n".join(text for _, text in blocks)
    return [{
        "name": "Document",
        "headers": [],
        "rows": [],
        "text": full_text[:8000],
        "row_count": 0,
    }]
