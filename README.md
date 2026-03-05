# Audio Analyzer

A FastAPI-based application for audio file upload, processing, and transcription using the Sarvam AI speech-to-text API. The system supports batch processing with speaker diarization capabilities for Hindi and code-mixed audio files.

## Overview

This application provides a RESTful API for:
- Uploading audio files with duplicate detection
- Processing audio files using Sarvam AI's batch transcription service
- Managing file metadata and processing status
- Storing transcription results with speaker diarization

## Project Structure

```
audio_analyzer/
│
├── config/                          # Configuration management
│   ├── __init__.py
│   ├── path.py                      # Path definitions and directory setup
│   └── settings.yaml                # Sarvam API configuration
│
├── src/                             # Core application source code
│   ├── __init__.py
│   ├── api/                         # API endpoints
│   │   ├── __init__.py
│   │   ├── upload.py                # Audio file upload endpoint
│   │   └── process.py               # Audio processing endpoint
│   ├── services/                    # External service integrations
│   │   ├── __init__.py
│   │   └── sarvam_client.py         # Sarvam AI batch API client
│   └── jobs/                        # Background job handlers (future)
│       └── __init__.py
│
├── utils/                           # Utility modules
│   ├── __init__.py
│   ├── logger.py                    # Loguru-based logging setup
│   ├── config_loader.py             # YAML configuration loader
│   ├── audio_utils.py               # Audio file utilities
│   └── result_formatter.py          # Transcription result formatter
│
├── uploads/                         # Uploaded audio files storage
│   ├── results/                     # Transcription JSON results
│   └── metadata.json                # File tracking metadata
│
├── logs/                            # Application logs (auto-generated)
│
├── at_env/                          # Virtual environment
│
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project configuration
├── .env                             # Environment variables (API keys)
├── .gitignore
└── README.md                        # This file
```

## File Descriptions and Relationships

### Core Application

**main.py** - Application Entry Point
- **Purpose**: FastAPI application initialization and router registration
- **Functions**:
  - `health_check()`: GET endpoint at `/` that returns API status
- **Imports**: 
  - `logger` from `utils.logger`
  - `upload_router` from `src.api.upload`
  - `process_router` from `src.api.process`
- **Relationships**: Entry point that connects all API routers and initializes the FastAPI app

### Configuration Layer

**config/path.py** - Path Management
- **Purpose**: Centralized path configuration for the entire project
- **Constants Defined**:
  - `BASE_DIR`: Project root directory
  - `UPLOAD_DIR`: Directory for uploaded audio files (auto-created)
  - `CONFIG_DIR`: Configuration files directory
  - `SETTINGS_PATH`: Path to settings.yaml
  - `ENV_PATH`: Path to .env file
  - `METADATA_FILE`: Path to metadata.json for tracking uploads
  - `RESULTS_DIR`: Directory for transcription results
- **Relationships**: Imported by `upload.py`, `process.py`, `sarvam_client.py`, and `config_loader.py`

**config/settings.yaml** - API Configuration
- **Purpose**: YAML configuration file for Sarvam AI API settings
- **Configuration Structure**:
  - `sarvam.base_url`: API endpoint URL
  - `sarvam.model`: "saaras:v3" (Sarvam's speech model)
  - `sarvam.mode`: "transcribe" (operation mode)
  - `sarvam.request_config.language`: "hi-IN" (Hindi-India)
  - `sarvam.request_config.temperature`: 0.0
  - `sarvam.request_config.response_format`: "json"
  - `sarvam.request_config.diarization`: false
  - `sarvam.request_config.punctuation`: true
- **Relationships**: Loaded by `config_loader.py` using `load_settings()` function

### API Endpoints

**src/api/upload.py** - File Upload Handler
- **Purpose**: Handles audio file uploads with SHA256-based duplicate detection
- **Endpoint**: `POST /upload-audio`
- **Constants**:
  - `ALLOWED_EXTENSIONS`: Set of allowed file formats {.wav, .mp3, .m4a, .flac, .aac}
  - `router`: FastAPI APIRouter instance
- **Functions**:
  - `generate_file_hash(file_bytes: bytes) -> str`: Generates SHA256 hash for duplicate detection using hashlib
  - `load_metadata() -> dict`: Loads metadata.json, creates empty file if not exists
  - `save_metadata(data: dict)`: Saves metadata dictionary to JSON file with indent=4
  - `upload_audio(file: UploadFile) -> dict`: Async endpoint handler for file uploads
- **Process Flow**:
  1. Validates file extension against ALLOWED_EXTENSIONS
  2. Reads file bytes and generates SHA256 hash
  3. Checks metadata for duplicate hash
  4. If duplicate: returns existing file_id and status
  5. If new: generates UUID, saves file as "{uuid}_{filename}"
  6. Updates metadata with file_id, stored_filename, status="uploaded", sarvam_job_id=None, result_file=None
- **Error Handling**: HTTPException for validation errors, generic exception logging
- **Imports**: json, uuid, hashlib, Path, FastAPI components, logger, UPLOAD_DIR, METADATA_FILE
- **Relationships**: Called by main.py router, uses config.path for directories, logs via utils.logger

**src/api/process.py** - Audio Processing Handler
- **Purpose**: Orchestrates audio transcription processing using Sarvam AI batch API
- **Endpoint**: `POST /process-audio`
- **Models**:
  - `ProcessRequest(BaseModel)`: Pydantic model with field `file_id: str`
- **Functions**:
  - `load_metadata() -> dict`: Loads metadata.json from METADATA_FILE
  - `save_metadata(data: dict)`: Saves metadata with indent=4
  - `process_audio(request: ProcessRequest) -> dict`: Main endpoint handler (blocking)
- **Process Flow**:
  1. Loads metadata and searches for file_id in all records
  2. Validates file exists (raises 404 if not found)
  3. Checks status:
     - If "completed": returns existing result_file
     - If "processing": returns current sarvam_job_id
     - If "uploaded" or "failed": proceeds to processing
  4. Validates physical file exists in UPLOAD_DIR
  5. Updates status to "processing" in metadata
  6. Calls `transcribe_with_batch(file_path, file_hash_key, METADATA_FILE)`
  7. Returns result with status, sarvam_job_id, and result_file path
- **Status State Machine**: uploaded → processing → completed/failed
- **Error Handling**: HTTPException for validation, generic exception logging in finally block
- **Imports**: FastAPI components, Pydantic, Path, json, logger, UPLOAD_DIR, transcribe_with_batch
- **Relationships**: Called by main.py router, uses sarvam_client.transcribe_with_batch() for processing

### Services Layer

**src/services/sarvam_client.py** - Sarvam AI Integration
- **Purpose**: Core service for Sarvam AI batch transcription with speaker diarization
- **Environment Variables**:
  - `SARVAM_API_KEY`: Loaded from .env file using python-dotenv (raises ValueError if missing)
- **Functions**:
  - `load_metadata(metadata_file: Path) -> dict`: Loads metadata JSON with exception handling
  - `save_metadata(metadata_file: Path, data: dict) -> None`: Saves metadata JSON with indent=4
  - `transcribe_with_batch(file_path: str, file_hash: str, metadata_file: Path) -> dict`: Main transcription orchestrator (blocking)
- **Transcription Process Flow**:
  1. Initializes SarvamAI client with api_subscription_key
  2. Creates batch job: model="saaras:v3", mode="translit", language_code="hi-IN", with_diarization=True
  3. Uploads audio file using job.upload_files([file_path])
  4. Starts job execution with job.start()
  5. Blocks until completion with job.wait_until_complete()
  6. If job_state == "Completed":
     - Creates RESULTS_DIR if not exists
     - Downloads outputs using job.download_outputs()
     - Constructs result_file path as "{audio_filename}.json"
     - Updates metadata: status="completed", result_file, sarvam_job_id
     - Returns dict with status, sarvam_job_id, result_file
  7. If failed: Updates metadata status="failed", returns dict with status and job_id
- **Error Handling**: Catches all exceptions, updates metadata status to "failed", re-raises exception
- **Imports**: os, json, Path, load_dotenv, SarvamAI, logger, ENV_PATH, RESULTS_DIR, UPLOAD_DIR
- **Relationships**: Called by process.py, uses config.path for directories, logs via utils.logger

### Utilities Layer

**utils/logger.py** - Logging Configuration
- **Purpose**: Centralized Loguru-based logging configuration for the entire application
- **Constants**:
  - `LOG_DIR`: "logs" directory (auto-created if not exists)
- **Functions**:
  - `setup_app_logger()`: Configures dual logging (console + file)
- **Console Logger Configuration**:
  - Target: sys.stderr
  - Format: Colorized with timestamp, level, name, function, line, message
  - Level: DEBUG (all logs visible)
- **File Logger Configuration**:
  - Path: logs/app_{time:YYYY-MM-DD_HH-mm-ss}.log (unique per session)
  - Rotation: 10 MB file size limit
  - Retention: 7 days (auto-deletes old logs)
  - Compression: zip format for archived logs
  - Level: INFO (excludes DEBUG from files)
  - enqueue=True: Thread-safe for async operations
  - backtrace=True: Full error stack traces
  - diagnose=True: Variable values in error logs
- **Initialization**: Calls setup_app_logger() immediately on import
- **Exports**: logger instance via __all__
- **Relationships**: Imported by all modules (upload.py, process.py, sarvam_client.py, config_loader.py, audio_utils.py, result_formatter.py)

**utils/config_loader.py** - Configuration Loader
- **Purpose**: YAML configuration file loader for application settings
- **Functions**:
  - `load_settings() -> dict`: Loads and parses settings.yaml using yaml.safe_load()
- **Process**:
  1. Opens SETTINGS_PATH from config.path
  2. Parses YAML content into Python dictionary
  3. Returns configuration dictionary
  4. Logs exception and re-raises on failure
- **Imports**: yaml, SETTINGS_PATH from config.path, logger from utils.logger
- **Relationships**: Uses config.path.SETTINGS_PATH, logs via utils.logger, can be called by any module needing settings

**utils/audio_utils.py** - Audio File Utilities
- **Purpose**: Audio file metadata extraction and analysis
- **Functions**:
  - `get_audio_duration(file_path: str) -> float`: Calculates audio duration in seconds
- **Implementation**:
  1. Opens audio file using soundfile.SoundFile context manager
  2. Calculates duration: len(audio) / audio.samplerate
  3. Logs duration information
  4. Returns duration as float
  5. Logs exception and re-raises on failure
- **Imports**: soundfile as sf, logger from utils.logger
- **Relationships**: Utility function available for any module needing audio duration (currently not actively used in main flow)

**utils/result_formatter.py** - Result Formatting
- **Purpose**: Post-processes Sarvam AI JSON output into clean structured format
- **Functions**:
  - `format_sarvam_output(result_file: Path) -> None`: Formats and overwrites result file
- **Process**:
  1. Validates result_file exists (raises FileNotFoundError if missing)
  2. Loads raw JSON with UTF-8 encoding
  3. Extracts structured fields:
     - request_id
     - transcript
     - timestamps
     - diarized_transcript
     - language_code
     - language_probability
  4. Overwrites file with json.dump(indent=4, ensure_ascii=False)
  5. ensure_ascii=False preserves Hindi/Unicode characters
- **Error Handling**: Logs exceptions and re-raises
- **Imports**: json, Path from pathlib, logger from utils.logger
- **Relationships**: Utility function for post-processing (currently not actively called in main flow)

## Data Flow

### Upload Flow
```
Client → POST /upload-audio → upload.py
  ↓
Validate file extension
  ↓
Generate SHA256 hash
  ↓
Check metadata.json for duplicates
  ↓
Save file with UUID prefix
  ↓
Update metadata.json (status: "uploaded")
  ↓
Return file_id to client
```

### Processing Flow
```
Client → POST /process-audio → process.py
  ↓
Validate file_id in metadata
  ↓
Check status (prevent duplicate processing)
  ↓
Update status to "processing"
  ↓
sarvam_client.transcribe_with_batch()
  ↓
Create Sarvam batch job
  ↓
Upload file to Sarvam
  ↓
Start job and wait for completion
  ↓
Download result JSON to uploads/results/
  ↓
Update metadata.json (status: "completed", result_file path)
  ↓
Return result to client
```

## Key Methods and Functions

### API Layer
- `upload_audio(file: UploadFile)` - Handles file upload with duplicate detection
- `process_audio(request: ProcessRequest)` - Triggers transcription processing

### Service Layer
- `transcribe_with_batch(file_path, file_hash, metadata_file)` - Orchestrates Sarvam AI batch transcription

### Utility Layer
- `generate_file_hash(file_bytes)` - SHA256 hash generation for duplicate detection
- `load_metadata()` / `save_metadata(data)` - Metadata persistence
- `setup_app_logger()` - Configures application-wide logging
- `load_settings()` - Loads YAML configuration
- `get_audio_duration(file_path)` - Calculates audio file duration
- `format_sarvam_output(result_file)` - Formats transcription results

## Dependencies

- **fastapi** - Web framework for building APIs
- **uvicorn** - ASGI server for FastAPI
- **loguru** - Advanced logging library
- **python-multipart** - File upload support
- **python-dotenv** - Environment variable management
- **sarvamai** - Sarvam AI SDK for speech-to-text
- **requests** - HTTP library for API calls
- **PyYAML** - YAML configuration parsing
- **soundfile** - Audio file reading and analysis
- **ipykernel** - Jupyter notebook support for testing

## Installation

```bash
# Create virtual environment
python -m venv at_env

# Activate virtual environment
# Windows
at_env\Scripts\activate
# Unix/MacOS
source at_env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Create `.env` file in project root:
```env
SARVAM_API_KEY=your_api_key_here
```

2. Configure `config/settings.yaml` (optional):
```yaml
sarvam:
  model: "saaras:v3"
  mode: "transcribe"
  request_config:
    language: "hi-IN"
    diarization: true
```

## Usage

### Start the Server
```bash
uvicorn main:app --reload
```

### API Endpoints

**1. Health Check**
```bash
GET http://localhost:8000/
```

**2. Upload Audio File**
```bash
POST http://localhost:8000/upload-audio
Content-Type: multipart/form-data

Body: file=@audio.wav
```

Response:
```json
{
  "message": "File uploaded successfully",
  "file_id": "uuid-here",
  "status": "uploaded"
}
```

**3. Process Audio File**
```bash
POST http://localhost:8000/process-audio
Content-Type: application/json

Body:
{
  "file_id": "uuid-here"
}
```

Response:
```json
{
  "message": "Processing completed",
  "file_id": "uuid-here",
  "status": "completed",
  "sarvam_job_id": "job-id",
  "result_file": "uploads/results/filename.json"
}
```

## Features

- ✅ Audio file upload with validation
- ✅ Duplicate file detection using SHA256 hashing
- ✅ Batch transcription using Sarvam AI
- ✅ Speaker diarization support
- ✅ Hindi and code-mixed language support
- ✅ Metadata tracking for all uploads
- ✅ Status management (uploaded → processing → completed/failed)
- ✅ Comprehensive logging with rotation and retention
- ✅ Structured JSON output for transcriptions

## File Relationships Summary

```
main.py
  ├── imports: upload.py, process.py, logger.py
  └── registers: API routers

upload.py
  ├── imports: logger.py, path.py
  └── manages: File uploads, metadata

process.py
  ├── imports: logger.py, path.py, sarvam_client.py
  └── orchestrates: Processing workflow

sarvam_client.py
  ├── imports: logger.py, path.py
  └── integrates: Sarvam AI API

logger.py
  └── provides: Logging to all modules

config_loader.py
  ├── imports: path.py, logger.py
  └── loads: settings.yaml

audio_utils.py
  ├── imports: logger.py
  └── analyzes: Audio files

result_formatter.py
  ├── imports: logger.py
  └── formats: Transcription results
```

