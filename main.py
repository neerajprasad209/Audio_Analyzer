from utils.logger import logger
from fastapi import FastAPI
from src.api.upload import router as upload_router
from src.api.process import router as process_router

app = FastAPI(title="Audio Analyzer API", description="API for uploading and analyzing audio files", version="1.0.0")

app.include_router(upload_router)
app.include_router(process_router)


@app.get("/")
def health_check():
    logger.info("Health check endpoint called")
    return {"status": "API is running"}


