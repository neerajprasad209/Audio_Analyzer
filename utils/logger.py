import sys
import os
from loguru import logger

# 1. Define the logs directory
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def setup_app_logger():
    # Remove default handler to prevent duplicate logs in console
    logger.remove()

    # 2. Terminal Logger (Colorful and clean for active debugging)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG"
    )

    # 3. File Logger (Date & Time specific filename)
    # Using {time} inside the string tells Loguru to generate a unique name
    log_file_path = os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD_HH-mm-ss}.log")
    
    logger.add(
        log_file_path,
        rotation="10 MB",    # Still rotates if a single session log gets too huge
        retention="7 days",   # Automatically deletes logs older than 7 days
        compression="zip",    # Compresses old logs to save space
        level="INFO",         # Saves INFO, WARNING, ERROR, and CRITICAL
        enqueue=True,         # Safe to use with multi-threading/Async (like your AI Agent)
        backtrace=True,       # Great for your AI project: logs the full error stack
        diagnose=True         # Shows variable values in the error log
    )

# Initialize the logger immediately
setup_app_logger()

# Export for use across the project
__all__ = ["logger"]