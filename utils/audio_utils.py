import soundfile as sf
from utils.logger import logger


def get_audio_duration(file_path: str) -> float:
    """
    Get duration of audio file in seconds.
    """
    try:
        with sf.SoundFile(file_path) as audio:
            duration = len(audio) / audio.samplerate
            logger.info(f"Audio duration: {duration} seconds")
            return duration
    except Exception:
        logger.exception("Failed to calculate audio duration")
        raise