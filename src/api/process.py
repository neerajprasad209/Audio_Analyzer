from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json

from utils.logger import logger
from config.path import UPLOAD_DIR
from src.services.sarvam_client import transcribe_with_batch

router = APIRouter()

METADATA_FILE = UPLOAD_DIR / "metadata.json"


class ProcessRequest(BaseModel):
    file_id: str


def load_metadata():
    with open(METADATA_FILE, "r") as f:
        return json.load(f)


def save_metadata(data: dict):
    with open(METADATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@router.post("/process-audio")
def process_audio(request: ProcessRequest):
    """
    Process uploaded audio using Sarvam batch API (blocking version).
    """

    try:
        logger.info(f"Processing request for file_id: {request.file_id}")

        metadata = load_metadata()

        file_hash_key = None
        file_record = None

        # Find file using file_id
        for hash_key, record in metadata.items():
            if record["file_id"] == request.file_id:
                file_hash_key = hash_key
                file_record = record
                break

        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        status = file_record.get("status")

        # Already completed
        if status == "completed":
            return {
                "message": "File already processed",
                "file_id": request.file_id,
                "result_file": file_record.get("result_file")
            }

        # Already processing
        if status == "processing":
            return {
                "message": "File is already processing",
                "file_id": request.file_id,
                "sarvam_job_id": file_record.get("sarvam_job_id")
            }

        # Only allow processing if status == uploaded or failed
        if status in ["uploaded", "failed"]:

            file_path = UPLOAD_DIR / file_record["stored_filename"]

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="Audio file missing")

            # Set status to processing before calling Sarvam
            file_record["status"] = "processing"
            save_metadata(metadata)

            result = transcribe_with_batch(
                file_path=str(file_path),
                file_hash=file_hash_key,
                metadata_file=METADATA_FILE
            )

            return {
                "message": "Processing completed",
                "file_id": request.file_id,
                "status": result["status"],
                "sarvam_job_id": result.get("sarvam_job_id"),
                "result_file": result.get("result_file")
            }

        raise HTTPException(status_code=400, detail="Invalid file state")

    except HTTPException:
        raise
    except Exception:
        logger.exception("Processing failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
    finally:
        logger.info(f"Processing request completed for file")
