import os
import json
from pathlib import Path
from dotenv import load_dotenv
from sarvamai import SarvamAI

from utils.logger import logger
from config.path import ENV_PATH, RESULTS_DIR, UPLOAD_DIR

# Load environment variables
load_dotenv(dotenv_path=ENV_PATH)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

if not SARVAM_API_KEY:
    raise ValueError("SARVAM_API_KEY not found in environment variables")


def load_metadata(metadata_file: Path) -> dict:
    """
    Load metadata JSON file.

    Args:
        metadata_file (Path): Path to metadata.json

    Returns:
        dict: Metadata dictionary
    """
    try:
        with open(metadata_file, "r") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load metadata")
        raise


def save_metadata(metadata_file: Path, data: dict) -> None:
    """
    Save metadata JSON file.

    Args:
        metadata_file (Path): Path to metadata.json
        data (dict): Updated metadata
    """
    try:
        with open(metadata_file, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        logger.exception("Failed to save metadata")
        raise


def transcribe_with_batch(
    file_path: str,
    file_hash: str,
    metadata_file: Path
) -> dict:
    """
    Process audio file using Sarvam Batch API (blocking version).

    Steps:
    - Create batch job
    - Upload file
    - Start job
    - Wait until complete
    - Download output JSON
    - Update metadata status

    Args:
        file_path (str): Full path to audio file
        file_hash (str): SHA256 hash key from metadata
        metadata_file (Path): Path to metadata.json

    Returns:
        dict: Result information including status and output file
    """

    try:
        logger.info(f"Starting Sarvam batch transcription for: {file_path}")

        client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

        # Create job
        job = client.speech_to_text_job.create_job(
            model="saaras:v3",
            mode="translit",
            language_code="hi-IN",
            with_diarization=True
        )

        logger.info("Batch job created successfully")

        # Upload file
        job.upload_files(file_paths=[file_path])
        logger.info("File uploaded to Sarvam job")

        # Start job
        job.start()
        logger.info("Sarvam job started")

        # Wait for completion (BLOCKING – testing phase)
        results = job.wait_until_complete()

        logger.info(f"Sarvam job completed with state: {results.job_state}")

        metadata = load_metadata(metadata_file)

        if results.job_state == "Completed":

            # Download output JSON
            RESULTS_DIR.mkdir(exist_ok=True)
            job.download_outputs(output_dir=str(RESULTS_DIR))

            # Find generated JSON file
            audio_filename = Path(file_path).stem
            result_file = RESULTS_DIR / f"{audio_filename}.json"

            # Update metadata
            metadata[file_hash]["status"] = "completed"
            metadata[file_hash]["result_file"] = str(result_file)
            metadata[file_hash]["sarvam_job_id"] = job.job_id

            save_metadata(metadata_file, metadata)

            logger.info("Transcription completed and metadata updated")

            return {
                "status": "completed",
                "sarvam_job_id": job.job_id,
                "result_file": str(result_file)
            }

        else:
            # Failed case
            metadata[file_hash]["status"] = "failed"
            metadata[file_hash]["sarvam_job_id"] = job.job_id

            save_metadata(metadata_file, metadata)

            logger.error("Sarvam transcription failed")

            return {
                "status": "failed",
                "sarvam_job_id": job.job_id
            }

    except Exception:
        logger.exception("Error during Sarvam batch processing")

        # Update metadata as failed if unexpected error occurs
        metadata = load_metadata(metadata_file)
        metadata[file_hash]["status"] = "failed"
        save_metadata(metadata_file, metadata)

        raise


