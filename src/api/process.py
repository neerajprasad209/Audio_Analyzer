from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.services.sarvam_client import transcribe_with_batch
from src.services.session_manager import (
    get_session_keys,
    get_session_paths,
    load_session_metadata,
    save_session_metadata,
)
from utils.logger import logger

router = APIRouter()


class ProcessRequest(BaseModel):
    session_id: str = Field(min_length=1)
    file_id: str = Field(min_length=1)
    mode: Literal["transcribe", "translate", "verbatim", "translit", "codemix"] = "transcribe"


def _find_file_record(metadata: dict, file_id: str) -> tuple[str | None, dict | None]:
    files_data = metadata.get("files", {})
    for hash_key, record in files_data.items():
        if record.get("file_id") == file_id:
            return hash_key, record
    return None, None


@router.post("/process-audio")
def process_audio(request: ProcessRequest):
    """
    Process uploaded audio using Sarvam batch API and generate SRT.
    """
    session_id = request.session_id.strip()
    file_id = request.file_id.strip()

    try:
        logger.info(f"Processing request: session={session_id}, file_id={file_id}")

        paths = get_session_paths(session_id)
        sarvam_api_key, gemini_api_key = get_session_keys(session_id)

        metadata = load_session_metadata(session_id)
        file_hash_key, file_record = _find_file_record(metadata, file_id)

        if not file_record or not file_hash_key:
            raise HTTPException(status_code=404, detail="File not found in this session")

        status = file_record.get("status")

        if status == "completed":
            return {
                "message": "File already processed",
                "session_id": session_id,
                "file_id": file_id,
                "status": status,
                "sarvam_job_id": file_record.get("sarvam_job_id"),
                "result_file": file_record.get("result_file"),
                "srt_file": file_record.get("srt_file"),
                "download_srt_url": (
                    f"/download-srt/{session_id}/{file_id}" if file_record.get("srt_file") else None
                )
            }

        if status == "processing":
            return {
                "message": "File is already processing",
                "session_id": session_id,
                "file_id": file_id,
                "sarvam_job_id": file_record.get("sarvam_job_id")
            }

        if status not in ["uploaded", "failed"]:
            raise HTTPException(status_code=400, detail="Invalid file state")

        file_path = paths["audio_dir"] / file_record["stored_filename"]
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Audio file missing")

        file_record["status"] = "processing"
        metadata["last_active_at"] = datetime.now(timezone.utc).isoformat()
        save_session_metadata(session_id, metadata)

        result = transcribe_with_batch(
            file_path=str(file_path),
            file_hash=file_hash_key,
            metadata_file=paths["metadata_file"],
            result_dir=paths["results_dir"],
            mode=request.mode,
            sarvam_api_key=sarvam_api_key,
            gemini_api_key=gemini_api_key
        )

        return {
            "message": "Processing completed",
            "session_id": session_id,
            "file_id": file_id,
            "status": result["status"],
            "sarvam_job_id": result.get("sarvam_job_id"),
            "result_file": result.get("result_file"),
            "srt_file": result.get("srt_file"),
            "download_srt_url": (
                f"/download-srt/{session_id}/{file_id}" if result.get("srt_file") else None
            )
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Processing failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        logger.info(f"Processing request completed: session={session_id}, file_id={file_id}")


@router.get("/download-srt/{session_id}/{file_id}")
def download_srt(session_id: str, file_id: str):
    """
    Download generated SRT file from the user's session folder.
    """
    session_id = session_id.strip()
    file_id = file_id.strip()

    paths = get_session_paths(session_id)
    metadata = load_session_metadata(session_id)
    _, file_record = _find_file_record(metadata, file_id)

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found in this session")

    srt_file_path = file_record.get("srt_file")
    if not srt_file_path:
        raise HTTPException(status_code=404, detail="SRT file not available")

    srt_path = Path(srt_file_path)
    if not srt_path.exists():
        fallback = paths["results_dir"] / f"{file_id}.srt"
        if not fallback.exists():
            raise HTTPException(status_code=404, detail="SRT file missing on server")
        srt_path = fallback

    return FileResponse(
        path=srt_path,
        media_type="application/x-subrip",
        filename=srt_path.name
    )
