from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.ai_service import AIService
from services import session_store
from prompts.templates import (
    RESUME_SYSTEM_PROMPT,
    RESUME_GENERATION_PROMPT,
    COVER_LETTER_SYSTEM_PROMPT,
    COVER_LETTER_PROMPT,
)

router = APIRouter()

RESUME_KEYWORDS = [
    "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "EDUCATION",
    "SKILLS", "SUMMARY", "CERTIFICATIONS", "PROJECTS",
]


def _detect_resume_in_response(text: str) -> bool:
    upper = text.upper()
    return sum(1 for kw in RESUME_KEYWORDS if kw in upper) >= 2


def _require_session(session_id: str):
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


def _get_ai(session) -> AIService:
    if not session.get("api_key"):
        raise HTTPException(status_code=400, detail="API key not configured. Please set it in the sidebar.")
    return AIService(session["agent"], session["api_key"])


def _build_profile_text(profile: dict) -> str:
    parts = [f"RESUME:\n{profile['resume_text']}"]
    if profile.get("linkedin_text"):
        parts.append(f"LINKEDIN PROFILE:\n{profile['linkedin_text']}")
    if profile.get("github_text"):
        parts.append(f"GITHUB:\n{profile['github_text']}")
    if profile.get("other_info"):
        parts.append(f"ADDITIONAL CANDIDATE INFO:\n{profile['other_info']}")
    return "\n\n".join(parts)


# ──────────────────────────────────────────
# Validate API key
# ──────────────────────────────────────────

class ValidateKeyRequest(BaseModel):
    agent: str
    api_key: str


@router.post("/validate-key")
async def validate_key(request: ValidateKeyRequest):
    try:
        service = AIService(request.agent, request.api_key)
        success, message = service.validate_api_key()
        return {"success": success, "message": message}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ──────────────────────────────────────────
# Initial resume generation
# ──────────────────────────────────────────

class GenerateResumeRequest(BaseModel):
    session_id: str


@router.post("/generate-resume")
async def generate_resume(request: GenerateResumeRequest):
    session = _require_session(request.session_id)

    profile = session["profile"]
    jd = session.get("job_description", "")

    if not profile.get("resume_text"):
        raise HTTPException(status_code=400, detail="No resume uploaded. Please go back to Step 1.")
    if not jd:
        raise HTTPException(status_code=400, detail="No job description provided. Please go back to Step 2.")

    profile_text = _build_profile_text(profile)
    initial_prompt = RESUME_GENERATION_PROMPT.format(
        profile=profile_text,
        job_description=jd,
    )

    messages = [{"role": "user", "content": initial_prompt}]
    ai = _get_ai(session)
    response = ai.send_message(messages, system=RESUME_SYSTEM_PROMPT)
    messages.append({"role": "assistant", "content": response})

    has_resume = _detect_resume_in_response(response)
    updates: dict = {"messages": messages}
    if has_resume:
        updates["generated_resume"] = response

    session_store.update_session(request.session_id, updates)

    return {"response": response, "has_resume": has_resume}


# ──────────────────────────────────────────
# Multi-turn chat for refinement
# ──────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("/message")
async def chat_message(request: ChatRequest):
    session = _require_session(request.session_id)

    messages = session.get("messages", [])
    messages.append({"role": "user", "content": request.message})

    ai = _get_ai(session)
    response = ai.send_message(messages, system=RESUME_SYSTEM_PROMPT)
    messages.append({"role": "assistant", "content": response})

    has_resume = _detect_resume_in_response(response)
    updates: dict = {"messages": messages}
    if has_resume:
        updates["generated_resume"] = response

    session_store.update_session(request.session_id, updates)

    return {"response": response, "has_resume": has_resume}


# ──────────────────────────────────────────
# Approve resume
# ──────────────────────────────────────────

class ApproveResumeRequest(BaseModel):
    session_id: str


@router.post("/approve-resume")
async def approve_resume(request: ApproveResumeRequest):
    session = _require_session(request.session_id)

    if not session.get("generated_resume"):
        raise HTTPException(status_code=400, detail="No resume to approve yet.")

    messages = session.get("messages", [])
    approval_msg = {
        "role": "assistant",
        "content": (
            "✅ Resume approved!\n\n"
            "You can now:\n"
            "• **Export** your resume as plain text, PDF, or Word document\n"
            "• **Generate a cover letter** tailored to this specific role\n\n"
            "Head to the **Export** tab when you're ready, or ask me to generate your cover letter here."
        ),
    }
    messages.append(approval_msg)
    session_store.update_session(request.session_id, {
        "resume_approved": True,
        "messages": messages,
    })

    return {"success": True}


# ──────────────────────────────────────────
# Generate cover letter
# ──────────────────────────────────────────

class CoverLetterRequest(BaseModel):
    session_id: str
    additional_context: str = ""


@router.post("/generate-cover-letter")
async def generate_cover_letter(request: CoverLetterRequest):
    session = _require_session(request.session_id)

    if not session.get("resume_approved"):
        raise HTTPException(status_code=400, detail="Please approve the resume before generating a cover letter.")

    resume = session.get("generated_resume", "")
    jd = session.get("job_description", "")

    prompt = COVER_LETTER_PROMPT.format(
        resume=resume,
        job_description=jd,
        additional_context=request.additional_context or "None provided.",
    )

    ai = _get_ai(session)
    response = ai.send_message(
        [{"role": "user", "content": prompt}],
        system=COVER_LETTER_SYSTEM_PROMPT,
    )

    session_store.update_session(request.session_id, {"generated_cover_letter": response})
    return {"cover_letter": response}


# ──────────────────────────────────────────
# Session state summary
# ──────────────────────────────────────────

@router.get("/session/{session_id}")
async def get_session_state(session_id: str):
    session = _require_session(session_id)
    return {
        "has_resume_uploaded": bool(session["profile"].get("resume_text")),
        "has_linkedin": bool(session["profile"].get("linkedin_text")),
        "has_github": bool(session["profile"].get("github_text")),
        "has_jd": bool(session.get("job_description")),
        "has_generated_resume": bool(session.get("generated_resume")),
        "resume_approved": session.get("resume_approved", False),
        "has_cover_letter": bool(session.get("generated_cover_letter")),
        "message_count": len(session.get("messages", [])),
        "agent": session.get("agent", "claude"),
    }
