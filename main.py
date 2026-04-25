from fastapi import FastAPI
from fastapi.responses import FileResponse

from config.path import BASE_DIR
from src.api.session import router as session_router
from src.api.upload import router as upload_router
from src.api.process import router as process_router
from utils.logger import logger

app = FastAPI(title="Audio Analyzer API", description="API for uploading and analyzing audio files", version="1.0.0")

app.include_router(session_router)
app.include_router(upload_router)
app.include_router(process_router)

UI_FILE = BASE_DIR / "static" / "index.html"


@app.get("/", include_in_schema=False)
def serve_ui():
    if UI_FILE.exists():
        return FileResponse(UI_FILE)

    logger.warning("UI file not found. Falling back to health payload.")
    return {"status": "API is running", "message": "UI file not found"}


@app.get("/health")
def health_check():
    logger.info("Health check endpoint called")
    return {"status": "API is running"}


