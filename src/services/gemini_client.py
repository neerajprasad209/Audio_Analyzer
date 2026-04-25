import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from config.path import ENV_PATH
from utils.logger import logger

# Load environment variables
load_dotenv(dotenv_path=ENV_PATH)

def get_gemini_llm(google_api_key: str | None = None):
    """
    Initialize Gemini LLM using LangChain.

    Returns:
        ChatGoogleGenerativeAI: Gemini LLM instance
    """

    try:
        resolved_key = google_api_key or os.getenv("GOOGLE_API_KEY")
        if not resolved_key:
            raise ValueError("GOOGLE_API_KEY is required in request or .env")

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            temperature=0,
            google_api_key=resolved_key
        )

        logger.info("Gemini LLM initialized successfully")

        return llm

    except Exception:
        logger.exception("Failed to initialize Gemini LLM")
        raise
