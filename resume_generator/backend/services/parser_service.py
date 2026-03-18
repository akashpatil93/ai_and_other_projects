import io
import requests
from bs4 import BeautifulSoup
from typing import Optional


def parse_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages).strip()
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def parse_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        raise ValueError(f"Failed to parse DOCX: {str(e)}")


def parse_url(url: str) -> str:
    """Extract meaningful text from any URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if response.status_code in (403, 999):
            raise ValueError(
                "Access denied by the website. Try copying the job description text and pasting it directly."
            )
        raise ValueError(f"HTTP error {response.status_code}: {str(e)}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Could not reach URL: {str(e)}")

    soup = BeautifulSoup(response.content, "html.parser")

    # Remove noisy elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
        tag.decompose()

    # Try to find main content areas first
    main_content = (
        soup.find("main")
        or soup.find(attrs={"class": lambda c: c and "job" in c.lower() if c else False})
        or soup.find(attrs={"id": lambda i: i and "job" in i.lower() if i else False})
        or soup
    )

    text = main_content.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip() and len(line.strip()) > 3]

    # Cap at ~8000 characters to avoid bloating context
    full_text = "\n".join(lines)
    return full_text[:8000] if len(full_text) > 8000 else full_text


def parse_file(file_bytes: bytes, filename: str) -> str:
    """Dispatch to the correct parser based on file extension."""
    fn = filename.lower()
    if fn.endswith(".pdf"):
        return parse_pdf(file_bytes)
    elif fn.endswith(".docx"):
        return parse_docx(file_bytes)
    elif fn.endswith(".txt") or fn.endswith(".md"):
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(
            f"Unsupported file type '{filename}'. Please upload a PDF, DOCX, or TXT file."
        )
