from typing import Dict, Any, Optional
import uuid
from datetime import datetime

# In-memory session store (replace with Redis for production)
sessions: Dict[str, Dict[str, Any]] = {}


def create_session() -> str:
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "created_at": datetime.now().isoformat(),
        "messages": [],
        "profile": {
            "resume_text": "",
            "linkedin_text": "",
            "github_text": "",
            "other_info": "",
        },
        "job_description": "",
        "job_description_preview": "",
        "generated_resume": "",
        "generated_cover_letter": "",
        "resume_approved": False,
        "agent": "claude",
        "api_key": "",
    }
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return sessions.get(session_id)


def update_session(session_id: str, updates: Dict[str, Any]) -> bool:
    if session_id not in sessions:
        return False
    sessions[session_id].update(updates)
    return True


def delete_session(session_id: str) -> bool:
    if session_id in sessions:
        del sessions[session_id]
        return True
    return False
