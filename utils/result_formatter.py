import json
from pathlib import Path
from utils.logger import logger


def format_sarvam_output(result_file: Path) -> None:
    """
    Format Sarvam raw JSON output into structured format.

    This function:
    - Loads raw Sarvam JSON
    - Extracts required fields
    - Overwrites the file with clean structured JSON

    Args:
        result_file (Path): Path to downloaded Sarvam JSON file
    """

    try:
        logger.info(f"Formatting Sarvam output file: {result_file}")

        if not result_file.exists():
            logger.error(f"Result file not found: {result_file}")
            raise FileNotFoundError(f"Result file not found: {result_file}")

        # Load raw JSON
        with open(result_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # Extract structured fields
        structured_output = {
            "request_id": raw_data.get("request_id"),
            "transcript": raw_data.get("transcript"),
            "timestamps": raw_data.get("timestamps"),
            "diarized_transcript": raw_data.get("diarized_transcript"),
            "language_code": raw_data.get("language_code"),
            "language_probability": raw_data.get("language_probability")
        }

        # Overwrite with clean structured JSON
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(
                structured_output,
                f,
                indent=4,
                ensure_ascii=False  # Important for Hindi text
            )

        logger.info("Sarvam output formatted successfully")

    except Exception:
        logger.exception("Failed to format Sarvam output")
        raise