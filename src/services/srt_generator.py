import json
from langchain_core.prompts import PromptTemplate

from utils.logger import logger
from src.services.gemini_client import get_gemini_llm


def generate_srt_from_diarization(
    diarized_transcript: dict,
    gemini_api_key: str | None = None
) -> str:
    """
    Convert diarized transcript JSON into SRT subtitle format using Gemini.

    Args:
        diarized_transcript (dict): Diarized transcript returned from Sarvam

    Returns:
        str: Generated SRT subtitle text
    """

    try:
        logger.info("Generating SRT from diarized transcript using Gemini")

        llm = get_gemini_llm(google_api_key=gemini_api_key)

        prompt_template = PromptTemplate(
            input_variables=["transcript"],
            template="""
                    You are an expert subtitle generator.

                    Convert the following diarized transcript JSON into a proper SRT subtitle file.

                    Rules:
                    - Convert start_time_seconds and end_time_seconds to SRT timestamp format
                    - Timestamp format: HH:MM:SS,mmm
                    - Maintain speaker dialogue
                    - Combine small fragments where appropriate
                    - Output ONLY valid SRT text
                    - Do not include explanations

                    Diarized Transcript:
                    {transcript}
                    """
        )

        prompt = prompt_template.format(
            transcript=json.dumps(diarized_transcript, indent=2)
        )

        response = llm.invoke(prompt)

        srt_text = response.content

        logger.info("SRT generation completed")

        return srt_text

    except Exception:
        logger.exception("Failed to generate SRT from diarized transcript")
        raise
