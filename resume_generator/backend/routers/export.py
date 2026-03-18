import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from services import session_store

router = APIRouter()


class ExportRequest(BaseModel):
    session_id: str
    content_type: str  # "resume" | "cover_letter"
    format: str        # "txt" | "pdf" | "docx"


@router.post("/download")
async def export_document(request: ExportRequest):
    session = session_store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if request.content_type == "resume":
        content = session.get("generated_resume", "")
        base_name = "resume"
    elif request.content_type == "cover_letter":
        content = session.get("generated_cover_letter", "")
        base_name = "cover_letter"
    else:
        raise HTTPException(status_code=400, detail="Invalid content_type.")

    if not content:
        raise HTTPException(status_code=400, detail="No content to export yet.")

    fmt = request.format.lower()

    if fmt == "txt":
        return Response(
            content=content.encode("utf-8"),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={base_name}.txt"},
        )

    elif fmt == "pdf":
        pdf_bytes = _generate_pdf(content)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={base_name}.pdf"},
        )

    elif fmt == "docx":
        docx_bytes = _generate_docx(content)
        return Response(
            content=docx_bytes,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            headers={"Content-Disposition": f"attachment; filename={base_name}.docx"},
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use txt, pdf, or docx.")


# ──────────────────────────────────────────
# PDF Generation
# ──────────────────────────────────────────

def _generate_pdf(content: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
    )

    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "CandidateName",
        fontSize=16,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#111827"),
        spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "Contact",
        fontSize=9,
        fontName="Helvetica",
        textColor=colors.HexColor("#6B7280"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1D4ED8"),
        spaceBefore=10,
        spaceAfter=3,
        textTransform="uppercase",
    )
    body_style = ParagraphStyle(
        "Body",
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=3,
        leading=14,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=14,
        spaceAfter=2,
    )

    story = []
    lines = content.split("\n")
    first_non_empty = next((i for i, l in enumerate(lines) if l.strip()), 0)

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        upper = line.upper()
        is_section = (
            line.isupper()
            and 3 < len(line) < 60
            and not line.startswith("•")
            and not line.startswith("-")
        )

        if i == first_non_empty:
            # First non-empty line = candidate name
            story.append(Paragraph(line, name_style))
        elif i == first_non_empty + 1 and "|" in line:
            story.append(Paragraph(line, contact_style))
        elif is_section:
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB"), spaceAfter=3))
            story.append(Paragraph(line, section_style))
        elif line.startswith(("•", "-", "*")):
            clean = line.lstrip("•-* ").strip()
            story.append(Paragraph(f"• {clean}", bullet_style))
        else:
            story.append(Paragraph(line, body_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ──────────────────────────────────────────
# DOCX Generation
# ──────────────────────────────────────────

def _generate_docx(content: str) -> bytes:
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # Margins
    for section in doc.sections:
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Default font
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    lines = content.split("\n")
    first_non_empty = next((i for i, l in enumerate(lines) if l.strip()), 0)

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            continue

        is_section = (
            line.isupper()
            and 3 < len(line) < 60
            and not line.startswith("•")
            and not line.startswith("-")
        )

        if i == first_non_empty:
            # Candidate name
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(16)
            run.font.color.rgb = RGBColor(0x11, 0x18, 0x27)
            p.paragraph_format.space_after = Pt(2)

        elif i == first_non_empty + 1 and "|" in line:
            # Contact line
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
            p.paragraph_format.space_after = Pt(6)

        elif is_section:
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(3)

        elif line.startswith(("•", "-", "*")):
            clean = line.lstrip("•-* ").strip()
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(clean).font.size = Pt(10)
            p.paragraph_format.space_after = Pt(2)

        else:
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.font.size = Pt(10)
            p.paragraph_format.space_after = Pt(2)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
