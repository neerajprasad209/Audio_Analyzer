import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from sarvamai import SarvamAI

from utils.logger import logger
from config.path import ENV_PATH

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
        logger.exception("Failed to load metadata file")
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
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception:
        logger.exception("Failed to save metadata")
        raise


def parse_job_results(results_json: str) -> tuple:
    """
    Parse Sarvam job response JSON and extract job_id, file_name and file_id.

    Args:
        results_json (str): JSON string returned from results.model_dump_json()

    Returns:
        tuple: (job_id, file_name, file_id)
    """
    try:
        data = json.loads(results_json)

        job_id = data.get("job_id")

        job_details = data.get("job_details", [])

        if not job_details:
            raise ValueError("No job_details found in Sarvam response")

        first_job = job_details[0]

        file_info = first_job["inputs"][0]

        file_name = file_info["file_name"]
        file_id = file_info["file_id"]

        logger.info(f"Parsed Sarvam job result: job_id={job_id}, file_name={file_name}, file_id={file_id}")

        return job_id, file_name, file_id

    except Exception:
        logger.exception("Failed to parse Sarvam job results")
        raise


def fetch_download_url(job_id: str, file_id: str) -> str:
    """
    Fetch download URL from Sarvam download-files API.

    Args:
        job_id (str): Sarvam job ID
        file_id (str): File ID from Sarvam job response

    Returns:
        str: Download URL for transcript JSON
    """
    try:
        file_id = f"{file_id}.json"
        
        logger.info(f"Fetching download URL from Sarvam for job_id={job_id}, file_id={file_id}")
        
        payload = {
                "job_id": job_id,
                "files": [file_id]  # Must be a list of strings
            }

        headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json"
        }

        url = "https://api.sarvam.ai/speech-to-text/job/v1/download-files"

        logger.info(f"Requesting download URL for job_id={job_id}")

        response = requests.post(url, json=payload, headers=headers)

        response.raise_for_status()

        response_data = response.json()
        
        logger.info(f"Sarvam download URL response: {response_data}")

        download_urls = response_data.get("download_urls", {})['0.json']['file_url']
        logger.info(f"Extracted download URLs: {download_urls}")

        return download_urls

    except Exception:
        logger.exception("Failed to fetch download URL from Sarvam")
        raise


def download_transcript(download_url: str) -> dict:
    """
    Download transcript JSON from Sarvam storage URL.

    Args:
        download_url (str): Signed download URL

    Returns:
        dict: Transcript JSON response
    """
    try:
        logger.info("Downloading transcript JSON from Sarvam storage")

        response = requests.get(download_url)

        response.raise_for_status()

        transcript_json = response.json()

        logger.info("Transcript JSON downloaded successfully")

        return transcript_json

    except Exception:
        logger.exception("Failed to download transcript JSON")
        raise


def transcribe_with_batch(
    file_path: str,
    file_hash: str,
    metadata_file: Path
) -> dict:
    """
    Process audio file using Sarvam Batch API and store transcript in metadata.

    Steps:
    - Create batch job
    - Upload file
    - Start job
    - Wait for completion
    - Fetch transcript download URL
    - Download transcript JSON
    - Store transcript in metadata.json

    Args:
        file_path (str): Path to audio file
        file_hash (str): SHA256 hash used as metadata key
        metadata_file (Path): Path to metadata.json

    Returns:
        dict: Processing result
    """

    try:
        logger.info(f"Starting Sarvam batch transcription for file: {file_path}")

        client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

        # Create Sarvam job
        job = client.speech_to_text_job.create_job(
            model="saaras:v3",
            mode="translit",
            language_code="hi-IN",
            with_diarization=True
        )

        logger.info(f"Sarvam job created successfully with job_id: {job.job_id}")

        # Upload audio file
        job.upload_files(file_paths=[file_path])

        logger.info("Audio file uploaded to Sarvam job")

        # Start processing
        job.start()

        logger.info("Sarvam batch job started")

        # Wait until job finishes
        results = job.wait_until_complete()

        logger.info(f"Sarvam job completed with state: {results.job_state}")

        metadata = load_metadata(metadata_file)
        
        logger.info(f"Loaded metadata: {metadata}")

        if results.job_state == "Completed":

            # Convert Sarvam response to JSON
            results_json = results.model_dump_json()
            
            logger.info(f"Sarvam job results: {results_json}")

            # Extract job_id, file_name, file_id
            job_id, file_name, file_id = parse_job_results(results_json)
            
            logger.info(f"Extracted from Sarvam results - job_id: {job_id}, file_name: {file_name}, file_id: {file_id}")

            # Get transcript download URL
            download_url = fetch_download_url(job_id, file_id)

            # Download transcript JSON
            transcript_json = download_transcript(download_url)

            # Extract transcript fields
            transcript = transcript_json.get("transcript")
            diarized_transcript = transcript_json.get("diarized_transcript")
            timestamps = transcript_json.get("timestamps")

            # Update metadata with transcript
            metadata[file_hash]["status"] = "completed"
            metadata[file_hash]["sarvam_job_id"] = job_id
            metadata[file_hash]["transcript"] = transcript
            metadata[file_hash]["diarized_transcript"] = diarized_transcript
            metadata[file_hash]["timestamps"] = timestamps

            save_metadata(metadata_file, metadata)

            logger.info("Metadata updated with transcript successfully")

            return {
                "status": "completed",
                "sarvam_job_id": job_id
            }

        else:

            metadata[file_hash]["status"] = "failed"
            metadata[file_hash]["sarvam_job_id"] = job.job_id

            save_metadata(metadata_file, metadata)

            logger.error("Sarvam transcription failed")

            return {
                "status": "failed",
                "sarvam_job_id": job.job_id
            }

    except Exception:

        logger.exception("Unexpected error during Sarvam batch transcription")

        metadata = load_metadata(metadata_file)
        metadata[file_hash]["status"] = "failed"

        save_metadata(metadata_file, metadata)

        raise