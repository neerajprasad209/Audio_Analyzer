# Audio Analyzer

Audio Analyzer is a FastAPI app with a built-in web UI for:
1. Saving Sarvam + Gemini API keys per active session.
2. Uploading audio.
3. Running Sarvam speech-to-text in a selected mode.
4. Generating SRT subtitles with Gemini.
5. Downloading the generated `.srt`.

Each active user/session gets an isolated folder under `uploads/<session_id>`, and that folder is deleted when the session ends, when the user leaves the UI, or after idle expiry.

## Current Features

- Web UI served directly by backend at `GET /`.
- Session lifecycle endpoints (`/session/start`, `/session/heartbeat`, `/session/end`).
- Per-session workspace folder under `uploads/<session_id>`.
- Audio upload with extension validation (`.wav`, `.mp3`, `.m4a`, `.flac`, `.aac`).
- Duplicate detection by SHA256 hash within the same session.
- Processing modes selectable by user:
  - `transcribe` (default)
  - `translate`
  - `verbatim`
  - `translit`
  - `codemix`
- Process panel shows animated state while running, then `Completed`/`Failed`.
- Sarvam job config from `config/settings.yaml`:
  - `sarvam.model`
  - `sarvam.request_config.diarization`
- `language_code` is intentionally not sent in `create_job`.
- Gemini-based SRT generation from diarized transcript.
- SRT download endpoint: `GET /download-srt/{session_id}/{file_id}`.
- Background cleanup worker removes expired sessions (30-minute TTL, checks every 60 seconds).

## Session Folder Layout

For each active session:

```text
uploads/
  <session_id>/
    metadata.json
    audios/
      <file_id>_<original_filename>
    results/
      <file_id>.srt
```

`metadata.json` is the primary source of truth for uploaded files and processing status in that session.

## API Endpoints

### Health + UI

- `GET /` -> serves UI (`static/index.html`)
- `GET /health` -> health payload

### Session APIs

- `POST /session/start`

Request body:

```json
{
  "sarvam_api_key": "your_sarvam_key",
  "gemini_api_key": "your_gemini_key"
}
```

Response (example):

```json
{
  "message": "Session started",
  "session_id": "uuid",
  "folder_name": "uuid"
}
```

- `POST /session/heartbeat`

Request body:

```json
{
  "session_id": "uuid"
}
```

- `POST /session/end`

Request body:

```json
{
  "session_id": "uuid"
}
```

Ends session and deletes `uploads/<session_id>`.

### Upload API

- `POST /upload-audio`
- `Content-Type: multipart/form-data`
- Required form fields:
  - `session_id`
  - `file`

### Processing API

- `POST /process-audio`

Request body:

```json
{
  "session_id": "uuid",
  "file_id": "uuid",
  "mode": "transcribe"
}
```

Allowed `mode` values:
`transcribe`, `translate`, `verbatim`, `translit`, `codemix`.

Mode behavior summary:

- `transcribe`: Standard transcription in original language.
- `translate`: Indic speech to English text.
- `verbatim`: Word-for-word output without normalization.
- `translit`: Romanized/transliterated output.
- `codemix`: Code-mixed output with English words in English script.

### Download API

- `GET /download-srt/{session_id}/{file_id}`

Returns the generated `.srt` file for that session/file.

## Configuration

`config/settings.yaml`:

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

Currently used by runtime job creation:
- `sarvam.model`
- `sarvam.request_config.diarization`

`mode` comes from user input (UI/API request), not from `settings.yaml`.

## Installation

Python `>= 3.12` is recommended.

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

## Run

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:
- UI: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`

## UI Workflow

1. Enter Sarvam + Gemini keys.
2. Click **Save Keys & Start Session**.
3. Upload one audio file.
4. Choose processing mode.
5. Click **Transcribe & Generate SRT**.
6. Download SRT.
7. Click **Clear Keys & End Session** (or close tab) to delete workspace folder.

## cURL Flow Example

Start session:

```bash
curl -X POST "http://127.0.0.1:8000/session/start" \
  -H "Content-Type: application/json" \
  -d "{\"sarvam_api_key\":\"<SARVAM_KEY>\",\"gemini_api_key\":\"<GEMINI_KEY>\"}"
```

Upload:

```bash
curl -X POST "http://127.0.0.1:8000/upload-audio" \
  -F "session_id=<SESSION_ID>" \
  -F "file=@path/to/audio.wav"
```

Process:

```bash
curl -X POST "http://127.0.0.1:8000/process-audio" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"<SESSION_ID>\",\"file_id\":\"<FILE_ID>\",\"mode\":\"transcribe\"}"
```

Download SRT:

```bash
curl -L "http://127.0.0.1:8000/download-srt/<SESSION_ID>/<FILE_ID>" -o output.srt
```

End session:

```bash
curl -X POST "http://127.0.0.1:8000/session/end" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"<SESSION_ID>\"}"
```

## Notes

- Session keys are held in-memory for active sessions.
- If server restarts, active in-memory sessions are lost.
- Stale session folders are cleaned by metadata timestamps and TTL logic.
- Logger writes to `logs/` with rotation/compression.
