from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from services.parser_service import parse_file, parse_url
from services.linkedin_service import fetch_linkedin_profile
from services import session_store

router = APIRouter()


class SessionRequest(BaseModel):
    agent: str = "claude"
    api_key: str


class LinkedInRequest(BaseModel):
    session_id: str
    url: str


class JDUrlRequest(BaseModel):
    session_id: str
    url: str


def _require_session(session_id: str):
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please refresh and start again.")
    return session


# ──────────────────────────────────────────
# Session
# ──────────────────────────────────────────

@router.post("/session")
async def create_session(request: SessionRequest):
    session_id = session_store.create_session()
    session_store.update_session(session_id, {
        "agent": request.agent,
        "api_key": request.api_key,
    })
    return {"session_id": session_id}


# ──────────────────────────────────────────
# Resume
# ──────────────────────────────────────────

@router.post("/resume")
async def upload_resume(session_id: str = Form(...), file: UploadFile = File(...)):
    session = _require_session(session_id)
    file_bytes = await file.read()
    try:
        text = parse_file(file_bytes, file.filename)
        profile = session["profile"]
        profile["resume_text"] = text
        session_store.update_session(session_id, {"profile": profile})
        return {"success": True, "message": f"Resume parsed — {len(text):,} characters extracted."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────
# LinkedIn
# ──────────────────────────────────────────

@router.post("/linkedin")
async def fetch_linkedin(request: LinkedInRequest):
    session = _require_session(request.session_id)
    success, content = fetch_linkedin_profile(request.url)

    if success:
        profile = session["profile"]
        profile["linkedin_text"] = content
        session_store.update_session(request.session_id, {"profile": profile})
        return {"success": True, "message": "LinkedIn profile imported successfully."}

    return {
        "success": False,
        "message": content,
        "needs_manual": True,
    }


# ──────────────────────────────────────────
# GitHub / other URL
# ──────────────────────────────────────────

@router.post("/github")
async def add_github(session_id: str = Form(...), url: str = Form(...)):
    session = _require_session(session_id)
    try:
        text = parse_url(url)
        profile = session["profile"]
        profile["github_text"] = text[:4000]
        session_store.update_session(session_id, {"profile": profile})
        return {"success": True, "message": "GitHub profile fetched successfully."}
    except ValueError as e:
        return {"success": False, "message": str(e)}


# ──────────────────────────────────────────
# Additional candidate info (text)
# ──────────────────────────────────────────

@router.post("/additional-info")
async def add_additional_info(session_id: str = Form(...), info: str = Form(...)):
    session = _require_session(session_id)
    profile = session["profile"]
    profile["other_info"] = info
    session_store.update_session(session_id, {"profile": profile})
    return {"success": True, "message": "Additional info saved."}


# ──────────────────────────────────────────
# Job Description — URL
# ──────────────────────────────────────────

@router.post("/jd-url")
async def fetch_jd_url(request: JDUrlRequest):
    session = _require_session(request.session_id)
    try:
        text = parse_url(request.url)
        preview = text[:300] + ("..." if len(text) > 300 else "")
        session_store.update_session(request.session_id, {
            "job_description": text,
            "job_description_preview": preview,
        })
        return {
            "success": True,
            "message": f"Job description fetched — {len(text):,} characters.",
            "preview": preview,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────
# Job Description — File upload
# ──────────────────────────────────────────

@router.post("/jd-file")
async def upload_jd_file(session_id: str = Form(...), file: UploadFile = File(...)):
    session = _require_session(session_id)
    file_bytes = await file.read()
    try:
        text = parse_file(file_bytes, file.filename)
        preview = text[:300] + ("..." if len(text) > 300 else "")
        session_store.update_session(session_id, {
            "job_description": text,
            "job_description_preview": preview,
        })
        return {
            "success": True,
            "message": f"JD parsed — {len(text):,} characters.",
            "preview": preview,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────
# Job Description — Paste text
# ──────────────────────────────────────────

@router.post("/jd-text")
async def upload_jd_text(session_id: str = Form(...), text: str = Form(...)):
    _require_session(session_id)
    preview = text[:300] + ("..." if len(text) > 300 else "")
    session_store.update_session(session_id, {
        "job_description": text,
        "job_description_preview": preview,
    })
    return {"success": True, "message": "Job description saved."}
