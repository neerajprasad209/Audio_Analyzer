import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.services.session_manager import (
    get_session_paths,
    load_session_metadata,
    save_session_metadata,
)
from utils.logger import logger

router = APIRouter()

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac"}


def generate_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


@router.post("/upload-audio")
async def upload_audio(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload an audio file into the active session folder.
    """
    try:
        logger.info(f"Upload request received for session: {session_id}")

        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        file_bytes = await file.read()
        file_hash = generate_file_hash(file_bytes)

        paths = get_session_paths(session_id.strip())
        metadata = load_session_metadata(session_id.strip())
        files_data = metadata.setdefault("files", {})

        # Duplicate check inside this session only.
        if file_hash in files_data:
            record = files_data[file_hash]
            return {
                "message": "File already uploaded in this session",
                "session_id": session_id,
                "file_id": record["file_id"],
                "status": record["status"]
            }

        file_id = str(uuid.uuid4())
        safe_name = Path(file.filename).name
        stored_filename = f"{file_id}_{safe_name}"
        file_path = paths["audio_dir"] / stored_filename

        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)

        files_data[file_hash] = {
            "file_id": file_id,
            "original_filename": safe_name,
            "stored_filename": stored_filename,
            "status": "uploaded",
            "sarvam_job_id": None,
            "result_file": None,
            "srt_file": None,
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        }
        metadata["last_active_at"] = datetime.now(timezone.utc).isoformat()

        save_session_metadata(session_id.strip(), metadata)

        logger.info(f"File uploaded successfully: session={session_id}, file_id={file_id}")

        return {
            "message": "File uploaded successfully",
            "session_id": session_id,
            "file_id": file_id,
            "status": "uploaded"
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        logger.info("Audio upload request completed")
