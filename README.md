# 1. Project Title & Description

## Audio Analyzer

Audio Analyzer is a FastAPI + Web UI project for:

1. Uploading audio files
2. Transcribing speech using Sarvam Speech-to-Text
3. Generating SRT subtitles using Gemini
4. Downloading generated `.srt` files

The app uses **session-scoped folders** under `uploads/<session_id>` to isolate user data during active sessions.

---

# 2. Demo / Output (Optional but powerful)

You can showcase this section by adding:

1. A GIF of the UI flow (save keys -> upload -> process -> download)
2. A screenshot of processing states (idle, processing animation, completed)
3. A sample generated `.srt` snippet

Current local demo URL after starting server:

- `http://127.0.0.1:8000/`

---

# 3. Features

1. Session-based processing with automatic folder lifecycle
2. Save Sarvam + Gemini keys for active session
3. Upload audio formats: `.wav`, `.mp3`, `.m4a`, `.flac`, `.aac`
4. Duplicate detection within session using SHA256 hash
5. Processing modes selectable by user:
   - `transcribe`
   - `translate`
   - `verbatim`
   - `translit`
   - `codemix`
6. Sarvam job configuration loaded from `config/settings.yaml`:
   - `sarvam.model`
   - `sarvam.request_config.diarization`
7. Gemini-powered SRT generation from diarized transcript
8. SRT download endpoint per session/file
9. UI processing indicator with animation and completion/failure status
10. Session cleanup:
    - Explicit end via UI
    - On browser leave (`sendBeacon`)
    - Idle expiry cleanup worker

---

# 4. Tech Stack

Backend:

1. FastAPI
2. Uvicorn
3. SarvamAI SDK (`sarvamai`)
4. LangChain + `langchain-google-genai` (Gemini)
5. Requests
6. Loguru
7. PyYAML
8. Python Dotenv

Frontend:

1. HTML
2. CSS
3. Vanilla JavaScript

Runtime:

1. Python 3.12+

---

# 5. Project Structure

```text
audio_analyzer/
  config/
    path.py
    settings.yaml
  src/
    api/
      session.py
      upload.py
      process.py
    services/
      session_manager.py
      sarvam_client.py
      gemini_client.py
      srt_generator.py
    jobs/
  static/
    index.html
  utils/
    logger.py
    config_loader.py
    audio_utils.py
    result_formatter.py
  uploads/
    <session_id>/
      metadata.json
      audios/
      results/
  main.py
  requirements.txt
  pyproject.toml
  plan.md
```

---

# 6. Installation & Setup

## Prerequisites

1. Python 3.12+
2. Sarvam API key
3. Gemini API key

## Create API Keys

### Sarvam API key

1. Sign up or log in to your Sarvam account.
2. Open your dashboard and go to API key/subscription key management.
3. Create a new key.
4. Copy and save the key securely.

Reference:

- `https://docs.sarvam.ai/api-reference-docs`

### Google (Gemini) API key

1. Open Google AI Studio.
2. Go to API key management.
3. Create a new Gemini API key.
4. Copy and save the key securely.

References:

- `https://ai.google.dev/gemini-api/docs/api-key`
- `https://aistudio.google.com/app/apikey`

## Setup

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run app:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

---

# 7. Usage

## UI Flow

1. Open `http://127.0.0.1:8000/`
2. Enter Sarvam and Gemini keys
3. Click **Save Keys & Start Session**
4. Upload audio file
5. Select mode (`transcribe`, `translate`, `verbatim`, `translit`, `codemix`)
6. Click **Transcribe & Generate SRT**
7. Download SRT when completed
8. Click **Clear Keys & End Session** to delete session folder

## API Endpoints

Health/UI:

1. `GET /`
2. `GET /health`

Session:

1. `POST /session/start`
2. `POST /session/heartbeat`
3. `POST /session/end`

File processing:

1. `POST /upload-audio` (multipart form: `session_id`, `file`)
2. `POST /process-audio` (`session_id`, `file_id`, `mode`)
3. `GET /download-srt/{session_id}/{file_id}`

---

# 8. Configuration

Main config file: `config/settings.yaml`

```yaml
sarvam:
  base_url: "https://api.sarvam.ai/speech-to-text"
  model: "saaras:v3"
  mode: "transcribe"
  request_config:
    language: "hi-IN"
    temperature: 0.0
    response_format: "json"
    diarization: true
    punctuation: true
```

Notes:

1. Runtime job uses:
   - `sarvam.model`
   - `sarvam.request_config.diarization`
2. Processing `mode` is chosen by user in UI/API request.
3. `language_code` is intentionally not sent in Sarvam `create_job`.

## API Keys

Primary flow:

1. Keys are entered in UI and sent to `POST /session/start`.

Fallback:

1. `.env` values (`SARVAM_API_KEY`, `GOOGLE_API_KEY`) are optional fallback if request/session key is unavailable.

---

# 9. Workflow / How It Works

1. User starts session with both keys.
2. App creates `uploads/<session_id>/` with:
   - `metadata.json`
   - `audios/`
   - `results/`
3. User uploads file (`/upload-audio`):
   - validates extension
   - computes SHA256
   - stores file in `audios/`
   - updates `metadata.json`
4. User starts processing (`/process-audio`):
   - validates session and file status
   - creates Sarvam job with selected mode
   - waits for completion
   - fetches transcript
   - generates SRT via Gemini (if diarized transcript available)
   - saves `.srt` in `results/`
   - updates metadata status
5. User downloads SRT using `/download-srt/{session_id}/{file_id}`.
6. Session cleanup deletes folder on end/leave/expiry.

---

# 10. Architecture Overview

```text
Browser UI (static/index.html)
        |
        v
 FastAPI App (main.py + routers)
   |         |         |
   |         |         +--> Process API -> Sarvam Client -> Gemini SRT
   |         +------------> Upload API
   +----------------------> Session API
        |
        v
 Session Manager (in-memory session map + cleanup thread)
        |
        v
 Local Session Storage: uploads/<session_id>/
```

Components:

1. `src/api/session.py`: session start/heartbeat/end
2. `src/api/upload.py`: upload and metadata update
3. `src/api/process.py`: process orchestration and SRT download
4. `src/services/sarvam_client.py`: Sarvam transcription + transcript fetch
5. `src/services/srt_generator.py`: Gemini SRT generation
6. `src/services/session_manager.py`: folder lifecycle + TTL cleanup

---

# 11. Data Flow

## Upload Data Flow

```text
UI -> /upload-audio
   -> validate file type
   -> hash file (SHA256)
   -> dedupe check in metadata.json
   -> write file to uploads/<session_id>/audios/
   -> update metadata.json
```

## Process Data Flow

```text
UI -> /process-audio (session_id, file_id, mode)
   -> validate session + file state
   -> Sarvam create_job(model from config, mode from request, with_diarization from config)
   -> upload + start + wait
   -> fetch transcript JSON
   -> Gemini generate SRT
   -> save uploads/<session_id>/results/<file_id>.srt
   -> update metadata.json
   -> UI enables SRT download
```

---

# 12. Limitations

1. Session state is in-memory; restart clears active sessions.
2. Current processing is synchronous in request path (not queue-based).
3. Local filesystem storage is used (not object storage).
4. No production auth/authorization layer yet.
5. No rate limiting/quota enforcement in current backend.
6. Horizontal scaling needs Redis/DB/queue architecture upgrades.
7. External API dependency (Sarvam/Gemini) can impact latency/availability.

For a production-scale upgrade plan, see:

- `plan.md`
