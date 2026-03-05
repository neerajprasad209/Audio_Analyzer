import json
import uuid
import hashlib
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks

from utils.logger import logger
from config.path import UPLOAD_DIR, METADATA_FILE

router = APIRouter()

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac"}
# METADATA_FILE = UPLOAD_DIR / "metadata.json"

UPLOAD_DIR.mkdir(exist_ok=True)

if not METADATA_FILE.exists():
    with open(METADATA_FILE, "w") as f:
        json.dump({}, f)


def generate_file_hash(file_bytes: bytes) -> str:
    """Generate SHA256 hash for uploaded file."""
    return hashlib.sha256(file_bytes).hexdigest()


def load_metadata() -> dict:
    """
    Load metadata file.
    If not exists, create empty metadata file.
    """
    try:
        if not METADATA_FILE.exists():
            logger.warning("metadata.json not found. Creating new one.")
            with open(METADATA_FILE, "w") as f:
                json.dump({}, f)
            return {}

        with open(METADATA_FILE, "r") as f:
            return json.load(f)

    except Exception:
        logger.exception("Failed to load metadata")
        raise


def save_metadata(data: dict):
    with open(METADATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    """
    Upload audio file only.
    No processing happens here.
    """

    try:
        logger.info("Upload request received")

        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        file_bytes = await file.read()
        file_hash = generate_file_hash(file_bytes)

        metadata = load_metadata()

        # Duplicate check
        if file_hash in metadata:
            record = metadata[file_hash]

            logger.info("Duplicate file detected")

            return {
                "message": "File already uploaded",
                "file_id": record["file_id"],
                "status": record["status"]
            }

        # New file
        file_id = str(uuid.uuid4())
        new_filename = f"{file_id}_{file.filename}"
        file_path = UPLOAD_DIR / new_filename

        with open(file_path, "wb") as buffer:
            buffer.write(file_bytes)

        metadata[file_hash] = {
            "file_id": file_id,
            "stored_filename": new_filename,
            "status": "uploaded",
            "sarvam_job_id": None,
            "result_file": None
        }

        save_metadata(metadata)

        logger.info(f"File uploaded successfully with ID: {file_id}")

        return {
            "message": "File uploaded successfully",
            "file_id": file_id,
            "status": "uploaded"
        }

    except Exception:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        logger.info("Audio upload request completed")
        
        
        
        # try:
    #     logger.info("Received audio upload request")

    #     file_extension = Path(file.filename).suffix.lower()

    #     if file_extension not in ALLOWED_EXTENSIONS:
    #         logger.error(f"Invalid file format: {file_extension}")
    #         raise HTTPException(
    #             status_code=400,
    #             detail="Unsupported file format"
    #         )

    #     # Read file content
    #     file_bytes = await file.read()

    #     # Generate content hash
    #     file_hash = generate_file_hash(file_bytes)

    #     metadata = load_metadata()

    #     # Check duplicate
    #     if file_hash in metadata:
    #         logger.warning("Duplicate file upload attempt detected")
    #         raise HTTPException(
    #             status_code=409,
    #             detail="File already uploaded"
    #         )

    #     # Generate unique file ID
    #     file_id = str(uuid.uuid4())
    #     new_filename = f"{file_id}_{file.filename}"
    #     file_path = UPLOAD_DIR / new_filename

    #     # Save file
    #     with open(file_path, "wb") as buffer:
    #         buffer.write(file_bytes)

    #     # Save metadata entry
    #     metadata[file_hash] = {
    #         "file_id": file_id,
    #         "original_filename": file.filename,
    #         "stored_filename": new_filename,
    #         "status": "uploaded"
    #     }

    #     save_metadata(metadata)

    #     logger.info(f"File stored successfully with ID: {file_id}")

    #     return {
    #         "message": "File uploaded successfully",
    #         "file_id": file_id
    #     }

    # except HTTPException:
    #     raise
    # except Exception:
    #     logger.exception("Unexpected error during file upload")
    #     raise HTTPException(status_code=500, detail="Internal Server Error")