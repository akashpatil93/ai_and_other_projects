"""
Credit Policy Converter — FastAPI backend.
Converts policy documents (XLSX, PDF, DOCX, JSON) to workflow JSON via Claude AI.
"""
import json
import os
import tempfile
import uuid
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from llm.assembler import assemble_workflow
from llm.claude_client import ClaudeClient
from parsers.docx_parser import parse_docx
from parsers.excel_parser import parse_excel
from parsers.pdf_parser import parse_pdf
from validators.workflow_validator import validate_workflow

app = FastAPI(title="Credit Policy Converter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory stores  (swap for Redis / DB in production)
# ─────────────────────────────────────────────────────────────────────────────
uploads_store: Dict[str, Dict] = {}
workflows_store: Dict[str, Dict] = {}


def _get_client(header_key: str) -> ClaudeClient:
    """Resolve API key: request header takes priority, then .env / env var."""
    return ClaudeClient(api_key=header_key or os.environ.get("ANTHROPIC_API_KEY", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Request / response models
# ─────────────────────────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    file_id: str


class GenerateRequest(BaseModel):
    file_id: str


class UpdateWorkflowRequest(BaseModel):
    workflow: Dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/verify-key")
async def verify_key(x_anthropic_key: str = Header(default="")):
    """Lightweight check: confirm the key is non-empty and looks structurally valid."""
    key = x_anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(400, detail="No API key provided.")
    if not key.startswith("sk-ant-"):
        raise HTTPException(400, detail="Key does not look like a valid Anthropic API key.")
    # Mask for safe return
    masked = key[:12] + "..." + key[-4:]
    return {"valid": True, "masked": masked}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Accept a policy document upload and store it in memory."""
    allowed = {".xlsx", ".xls", ".pdf", ".docx", ".json", ".csv"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(
            400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(allowed))}",
        )

    content = await file.read()
    file_id = str(uuid.uuid4())
    uploads_store[file_id] = {
        "filename": file.filename,
        "content": content,
        "content_type": file.content_type,
        "size": len(content),
    }

    return {"file_id": file_id, "filename": file.filename, "size": len(content)}


@app.post("/api/parse")
async def parse_file(request: ParseRequest):
    """Parse the uploaded document and return detected sections."""
    if request.file_id not in uploads_store:
        raise HTTPException(404, detail="File not found. Upload first.")

    file_data = uploads_store[request.file_id]
    filename = (file_data["filename"] or "").lower()
    content: bytes = file_data["content"]
    ext = os.path.splitext(filename)[1] or ".xlsx"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if ext in (".xlsx", ".xls"):
            sections = parse_excel(tmp_path)
        elif ext == ".pdf":
            sections = parse_pdf(tmp_path)
        elif ext == ".docx":
            sections = parse_docx(tmp_path)
        elif ext == ".csv":
            import csv as csv_mod
            import io
            text = content.decode("utf-8", errors="replace")
            reader = csv_mod.DictReader(io.StringIO(text))
            rows = list(reader)
            headers = list(rows[0].keys()) if rows else []
            lines = ["\t".join(str(v) for v in r.values()) for r in rows[:150]]
            sections = [{
                "name": "CSV Data",
                "headers": headers,
                "rows": rows[:150],
                "text": "\t".join(headers) + "\n" + "\n".join(lines),
                "row_count": len(rows),
            }]
        elif ext == ".json":
            data = json.loads(content)
            sections = [{
                "name": "workflow_json",
                "headers": [],
                "rows": [],
                "text": json.dumps(data, indent=2)[:6000],
                "row_count": 1,
            }]
        else:
            raise HTTPException(400, detail=f"Cannot parse file type: {ext}")
    finally:
        os.unlink(tmp_path)

    parse_id = str(uuid.uuid4())
    uploads_store[request.file_id]["sections"] = sections
    uploads_store[request.file_id]["parse_id"] = parse_id

    return {
        "parse_id": parse_id,
        "section_count": len(sections),
        "sections": [
            {
                "name": s["name"],
                "row_count": s.get("row_count", 0),
                "headers": s.get("headers", [])[:6],
            }
            for s in sections
        ],
    }


@app.post("/api/generate")
async def generate_workflow(
    request: GenerateRequest,
    x_anthropic_key: str = Header(default=""),
):
    """Parse (if needed) + run Claude + assemble + validate workflow JSON."""
    if request.file_id not in uploads_store:
        raise HTTPException(404, detail="File not found. Upload first.")

    file_data = uploads_store[request.file_id]

    # Auto-parse if not done yet
    if "sections" not in file_data:
        await parse_file(ParseRequest(file_id=request.file_id))
        file_data = uploads_store[request.file_id]

    sections: List[Dict] = file_data.get("sections", [])
    if not sections:
        raise HTTPException(400, detail="No sections found in document.")

    try:
        claude_client = _get_client(x_anthropic_key)
        extracted = await claude_client.extract_all_sections(sections)
        workflow = assemble_workflow(extracted)
        validation = validate_workflow(workflow)

        workflow_id = str(uuid.uuid4())
        workflows_store[workflow_id] = {
            "workflow": workflow,
            "validation": validation,
            "file_id": request.file_id,
        }

        return {
            "workflow_id": workflow_id,
            "workflow": workflow,
            "validation": validation,
        }

    except Exception as exc:
        raise HTTPException(500, detail=f"Generation failed: {exc}") from exc


@app.post("/api/validate")
async def validate_endpoint(body: Dict[str, Any]):
    """Validate any workflow JSON body."""
    wf = body.get("workflow", body)
    return validate_workflow(wf)


@app.get("/api/workflow/{workflow_id}")
async def get_workflow(workflow_id: str):
    if workflow_id not in workflows_store:
        raise HTTPException(404, detail="Workflow not found.")
    return workflows_store[workflow_id]


@app.put("/api/workflow/{workflow_id}")
async def update_workflow(workflow_id: str, request: UpdateWorkflowRequest):
    if workflow_id not in workflows_store:
        raise HTTPException(404, detail="Workflow not found.")
    validation = validate_workflow(request.workflow)
    workflows_store[workflow_id]["workflow"] = request.workflow
    workflows_store[workflow_id]["validation"] = validation
    return {
        "workflow_id": workflow_id,
        "workflow": request.workflow,
        "validation": validation,
    }


@app.get("/api/export/{workflow_id}")
async def export_workflow(workflow_id: str):
    if workflow_id not in workflows_store:
        raise HTTPException(404, detail="Workflow not found.")
    workflow = workflows_store[workflow_id]["workflow"]
    json_str = json.dumps(workflow, indent=2)
    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=workflow_{workflow_id[:8]}.workflow"
        },
    )
