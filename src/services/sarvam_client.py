import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import requests
from dotenv import load_dotenv
from sarvamai import SarvamAI

from config.path import ENV_PATH
from src.services.srt_generator import generate_srt_from_diarization
from utils.config_loader import load_settings
from utils.logger import logger

load_dotenv(dotenv_path=ENV_PATH)


def resolve_sarvam_api_key(sarvam_api_key: str | None) -> str:
    resolved_key = sarvam_api_key or os.getenv("SARVAM_API_KEY")
    if not resolved_key:
        raise ValueError("SARVAM_API_KEY is required in request or .env")
    return resolved_key


def load_metadata(metadata_file: Path) -> dict:
    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load metadata file")
        raise


def save_metadata(metadata_file: Path, data: dict) -> None:
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception:
        logger.exception("Failed to save metadata")
        raise


def parse_job_results(results_json: str) -> tuple[str, str]:
    """
    Parse Sarvam job response JSON and extract job_id and file_id.
    """
    try:
        data = json.loads(results_json)
        job_id = data.get("job_id")
        job_details = data.get("job_details", [])

        if not job_details:
            raise ValueError("No job_details found in Sarvam response")

        first_job = job_details[0]
        file_info = first_job["inputs"][0]
        file_id = file_info["file_id"]

        logger.info(f"Parsed Sarvam job result: job_id={job_id}, file_id={file_id}")
        return job_id, file_id
    except Exception:
        logger.exception("Failed to parse Sarvam job results")
        raise


def fetch_download_url(job_id: str, file_id: str, sarvam_api_key: str) -> str:
    """
    Fetch transcript download URL from Sarvam.
    """
    try:
        payload = {"job_id": job_id, "files": [f"{file_id}.json"]}
        headers = {"api-subscription-key": sarvam_api_key, "Content-Type": "application/json"}
        url = "https://api.sarvam.ai/speech-to-text/job/v1/download-files"

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()

        download_urls = response_data.get("download_urls", {})
        if not download_urls:
            raise ValueError("No download URLs returned by Sarvam")

        first_file = next(iter(download_urls.values()))
        file_url = first_file.get("file_url")
        if not file_url:
            raise ValueError("Missing file_url in Sarvam download response")

        return file_url
    except Exception:
        logger.exception("Failed to fetch download URL from Sarvam")
        raise


def download_transcript(download_url: str) -> dict:
    try:
        response = requests.get(download_url)
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception("Failed to download transcript JSON")
        raise


def load_sarvam_job_config() -> tuple[str, bool]:
    """
    Read Sarvam job configuration from config/settings.yaml.
    Returns:
        tuple: (model, with_diarization)
    """
    settings = load_settings() or {}
    sarvam_settings = settings.get("sarvam", {})
    request_config = sarvam_settings.get("request_config", {})

    model = sarvam_settings.get("model") or "saaras:v3"
    with_diarization = bool(request_config.get("diarization", True))
    return model, with_diarization


def transcribe_with_batch(
    file_path: str,
    file_hash: str,
    metadata_file: Path,
    result_dir: Path,
    mode: Literal["transcribe", "translate", "verbatim", "translit", "codemix"] = "transcribe",
    sarvam_api_key: str | None = None,
    gemini_api_key: str | None = None
) -> dict:
    """
    Process one audio file, update session metadata, and write SRT output.
    """
    job = None

    try:
        logger.info(f"Starting Sarvam batch transcription for file: {file_path}")

        resolved_sarvam_api_key = resolve_sarvam_api_key(sarvam_api_key)
        client = SarvamAI(api_subscription_key=resolved_sarvam_api_key)
        model, with_diarization = load_sarvam_job_config()

        job = client.speech_to_text_job.create_job(
            model=model,
            mode=mode,
            with_diarization=with_diarization
        )
        logger.info(f"Sarvam job created successfully with job_id: {job.job_id}")

        job.upload_files(file_paths=[file_path])
        job.start()
        results = job.wait_until_complete()

        metadata = load_metadata(metadata_file)
        files_data = metadata.setdefault("files", {})
        metadata_record = files_data.get(file_hash)

        if not metadata_record:
            raise ValueError(f"Metadata record not found for file hash: {file_hash}")

        if results.job_state == "Completed":
            results_json = results.model_dump_json()
            job_id, provider_file_id = parse_job_results(results_json)

            download_url = fetch_download_url(job_id, provider_file_id, resolved_sarvam_api_key)
            transcript_json = download_transcript(download_url)

            transcript = transcript_json.get("transcript")
            diarized_transcript = transcript_json.get("diarized_transcript")
            timestamps = transcript_json.get("timestamps")

            srt_output = None
            srt_file_path = None
            result_dir.mkdir(parents=True, exist_ok=True)

            if diarized_transcript:
                try:
                    srt_output = generate_srt_from_diarization(
                        diarized_transcript,
                        gemini_api_key=gemini_api_key
                    )
                    srt_file_path = result_dir / f"{metadata_record['file_id']}.srt"
                    with open(srt_file_path, "w", encoding="utf-8") as srt_file:
                        srt_file.write(srt_output)
                except Exception:
                    logger.exception("SRT generation failed")

            metadata_record["status"] = "completed"
            metadata_record["sarvam_job_id"] = job_id
            metadata_record["transcript"] = transcript
            metadata_record["diarized_transcript"] = diarized_transcript
            metadata_record["timestamps"] = timestamps
            metadata_record["result_file"] = None
            metadata_record["srt_output"] = srt_output
            metadata_record["srt_file"] = str(srt_file_path) if srt_file_path else None
            metadata["last_active_at"] = datetime.now(timezone.utc).isoformat()
            save_metadata(metadata_file, metadata)

            return {
                "status": "completed",
                "sarvam_job_id": job_id,
                "result_file": None,
                "srt_file": str(srt_file_path) if srt_file_path else None
            }

        metadata_record["status"] = "failed"
        metadata_record["sarvam_job_id"] = getattr(job, "job_id", None)
        metadata["last_active_at"] = datetime.now(timezone.utc).isoformat()
        save_metadata(metadata_file, metadata)

        return {"status": "failed", "sarvam_job_id": getattr(job, "job_id", None)}

    except Exception:
        logger.exception("Unexpected error during Sarvam batch transcription")
        metadata = load_metadata(metadata_file)
        files_data = metadata.setdefault("files", {})

        if file_hash in files_data:
            files_data[file_hash]["status"] = "failed"
            if job and getattr(job, "job_id", None):
                files_data[file_hash]["sarvam_job_id"] = job.job_id

        metadata["last_active_at"] = datetime.now(timezone.utc).isoformat()
        save_metadata(metadata_file, metadata)
        raise
