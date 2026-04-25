from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.services.session_manager import (
    create_session,
    end_session,
    touch_session,
)
from utils.logger import logger

router = APIRouter(prefix="/session", tags=["session"])


class StartSessionRequest(BaseModel):
    sarvam_api_key: str = Field(min_length=1)
    gemini_api_key: str = Field(min_length=1)


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1)


@router.post("/start")
def start_session(request: StartSessionRequest):
    """
    Create a session-scoped workspace folder after user saves both API keys.
    """
    try:
        created = create_session(
            sarvam_api_key=request.sarvam_api_key.strip(),
            gemini_api_key=request.gemini_api_key.strip()
        )
        return {
            "message": "Session started",
            "session_id": created["session_id"],
            "folder_name": created["folder_name"]
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to start session")
        raise HTTPException(status_code=500, detail="Failed to start session")


@router.post("/heartbeat")
def heartbeat(request: SessionRequest):
    """
    Keep the session active while the UI is open.
    """
    try:
        touch_session(request.session_id.strip())
        return {"message": "Session active"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Session heartbeat failed")
        raise HTTPException(status_code=500, detail="Session heartbeat failed")


@router.post("/end")
def stop_session(request: SessionRequest):
    """
    End session and delete its workspace folder.
    """
    try:
        deleted = end_session(request.session_id.strip(), reason="client-end")
        if not deleted:
            return {"message": "Session already ended"}
        return {"message": "Session ended and folder deleted"}
    except Exception:
        logger.exception("Failed to end session")
        raise HTTPException(status_code=500, detail="Failed to end session")
