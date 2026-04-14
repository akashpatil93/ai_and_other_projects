"""PDF document parser for credit policy documents using PyMuPDF."""
import re
from typing import Any, Dict, List, Optional, Tuple


def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a PDF and return a list of named sections suitable for Claude extraction.

    Splitting strategy (tried in order, first one that produces >1 section wins):
      1. "Rule set name:" bullet lines  → one section per ruleset (best for trigger/policy PDFs)
      2. Numbered headings (1.1, 2.3 …) → one section per heading
      3. ALL-CAPS lines                 → legacy fallback
      4. Entire document as one section → last resort
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

    print(f"[debug] pdf_parser: extracted {len(full_text)} chars total")

    # ── Strategy 1: "Rule set name:" lines ───────────────────────────────────
    sections = _split_by_ruleset_name(full_text)
    if sections:
        print(f"[debug] pdf_parser: split by ruleset_name → {len(sections)} sections: {[s['name'] for s in sections]}")
        return sections

    # ── Strategy 2: numbered headings (1.1, 2.3, A.1 …) ─────────────────────
    sections = _split_by_numbered_headings(full_text)
    if sections:
        print(f"[debug] pdf_parser: split by numbered_headings → {len(sections)} sections: {[s['name'] for s in sections]}")
        return sections

    # ── Strategy 3: ALL-CAPS lines ────────────────────────────────────────────
    sections = _split_by_allcaps(full_text)
    if sections:
        print(f"[debug] pdf_parser: split by allcaps → {len(sections)} sections: {[s['name'] for s in sections]}")
        return sections

    print(f"[debug] pdf_parser: no split strategy matched, using single fallback section")
    # ── Strategy 4: single fallback section ──────────────────────────────────
    return [{
        "name": "Policy Document",
        "headers": ["Content"],
        "rows": [{"Content": full_text}],
        "text": f"=== Policy Document ===\n{full_text[:24000]}",
        "row_count": 1,
    }]


# ─────────────────────────────────────────────────────────────────────────────
# Splitting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_section(name: str, text: str) -> Optional[Dict[str, Any]]:
    """Return a section dict or None if the text is too short to be useful."""
    text = text.strip()
    if not text or len(text) < 20:
        return None
    return {
        "name": name,
        "headers": ["Content"],
        "rows": [{"Content": text}],
        "text": f"=== {name} ===\n{text[:24000]}",
        "row_count": 1,
    }


def _split_by_ruleset_name(full_text: str) -> List[Dict[str, Any]]:
    """
    Split on lines that contain 'Rule set name' (case-insensitive).
    Each such line starts a new named section.
    Lines like:
        ● Rule set name: Location Strategy
        Rule set name : Negative Databases
    """
    # Match optional bullet/symbol + "Rule set name" + optional spaces/colon + the name
    # Broad match to catch any bullet character PyMuPDF might extract
    pattern = re.compile(
        r'(?:^|[\n\r])\s*[^\w\s]?\s*Rule\s+set\s+name\s*[:\-]\s*(.+)',
        re.IGNORECASE,
    )
    all_matches = list(pattern.finditer(full_text))
    print(f"[debug] pdf_parser _split_by_ruleset_name: found {len(all_matches)} 'Rule set name' matches (regex)")

    splits: List[Tuple[str, int]] = []
    for m in all_matches:
        rs_name = m.group(1).strip().rstrip("*")
        if rs_name:
            splits.append((rs_name, m.start()))

    # Fallback: line-by-line search (catches edge cases with unusual line endings or bullets)
    if not splits:
        _rs_pat = re.compile(r'rule\s*set\s*name\s*[:\-]\s*(.+)', re.IGNORECASE)
        pos = 0
        for line in full_text.splitlines(keepends=True):
            m = _rs_pat.search(line)
            if m:
                rs_name = m.group(1).strip().rstrip("*")
                if rs_name:
                    splits.append((rs_name, pos))
            pos += len(line)
        if splits:
            print(f"[debug] pdf_parser _split_by_ruleset_name: found {len(splits)} matches via line-by-line fallback")

    if not splits:
        return []

    # Everything before the first ruleset = preamble (metadata/input payload)
    sections = []
    preamble_end = splits[0][1]
    preamble = full_text[:preamble_end].strip()
    if preamble and len(preamble) > 80:
        sec = _make_section("Input Payload", preamble)
        if sec:
            sections.append(sec)

    for i, (name, start) in enumerate(splits):
        end = splits[i + 1][1] if i + 1 < len(splits) else len(full_text)
        text = full_text[start:end]
        sec = _make_section(name, text)
        if sec:
            sections.append(sec)

    return sections


def _split_by_numbered_headings(full_text: str) -> List[Dict[str, Any]]:
    """
    Split on numbered section headings like:
        1.1 Input Payload
        1.2 Rules to be Executed
        2. Credit Checks
    """
    pattern = re.compile(
        r'(?:^|[\n\r])((?:\d+\.)+\d*\s+[A-Za-z].{3,60})(?:\n|$)',
    )

    splits: List[Tuple[str, int]] = []
    for m in pattern.finditer(full_text):
        name = m.group(1).strip()
        splits.append((name, m.start()))

    if len(splits) < 2:
        return []

    sections = []
    for i, (name, start) in enumerate(splits):
        end = splits[i + 1][1] if i + 1 < len(splits) else len(full_text)
        text = full_text[start:end]
        sec = _make_section(name, text)
        if sec:
            sections.append(sec)

    return sections


def _split_by_allcaps(full_text: str) -> List[Dict[str, Any]]:
    """Original strategy: split on ALL-CAPS heading lines."""
    heading_pattern = re.compile(r'\n([A-Z][A-Z &/\-]{3,50})\n', re.MULTILINE)

    splits: List[Tuple[str, int]] = [("Introduction", 0)]
    for m in heading_pattern.finditer(full_text):
        name = m.group(1).strip()
        if 5 <= len(name) <= 60:
            splits.append((name, m.start()))

    if len(splits) < 2:
        return []

    sections = []
    for i, (name, start) in enumerate(splits):
        end = splits[i + 1][1] if i + 1 < len(splits) else len(full_text)
        text = full_text[start:end].strip()
        if text and len(text) > 80:
            sec = _make_section(name, text)
            if sec:
                sections.append(sec)

    return sections
