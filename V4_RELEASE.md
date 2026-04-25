# Audio Analyzer — V4 Release Document
## Version 4.0.0 | April 2026

---

## Overview

Version 4 fundamentally changes the session model from a single-use workflow to a persistent, continuous workspace. Users no longer manually create sessions or start fresh after each batch — instead, their session begins automatically on login and persists throughout their work session, accumulating results as they upload and process files incrementally.

**Key Changes:**
- **Auto-session on login** — session created automatically, no manual "Save Settings" step
- **Persistent session** — same session accumulates all uploads and results until logout
- **Multiple process cycles** — users can process files, upload more, process again, repeat
- **API key backend storage** — keys stored server-side, tracked for usage and quotas
- **30-minute idle logout** — replaces 10-minute session renewal
- **API usage tracking** — monitor Sarvam and Gemini consumption, block on exhaustion

---

## Problems V4 Solves

**Problem 1 — Session fragmentation**
In V3, each completed session required creating a new session to continue work. This broke continuity and made it impossible to view all work in one place.

**Problem 2 — No API usage visibility**
Users had no way to know how much of their API quota they'd consumed or when they'd hit limits.

**Problem 3 — Client-side API key storage**
API keys were stored in sessionStorage and sent with every request, exposing them in browser memory and network traffic.

**Problem 4 — Inflexible workflow**
The rigid open→processing→completed→new cycle didn't match real usage patterns where users want to iteratively add and process files.

---

## Implementation Plan

### Phase 1: Core Session & Workflow Changes

#### Task 1.1 — Auto-Session Creation

**Change:** Remove manual session creation. Session is auto-created on first authenticated action.

**Files to modify:**
- `static/index.html`
- `src/api/session.py`
- `src/services/session_manager.py`
- `utils/jwt.py`

**Implementation:**

**`src/services/session_manager.py`:**
Add new function:
```python
def get_or_create_user_session(metadata_file: Path, user_id: str) -> dict:
    """
    Get the active session for a user, or create one if none exists.
    Each user has exactly one active session at a time.
    """
    data = load_metadata(metadata_file)
    
    # Find existing active session for this user
    for session_id, session in data["sessions"].items():
        if session.get("user_id") == user_id and session["status"] != "archived":
            logger.info(f"Found active session {session_id} for user {user_id}")
            return session
    
    # No active session — create one
    session_id = str(uuid.uuid4())
    session_record = {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",  # New: replaces open/ready/completed
        "total_bytes": 0,
        "files": {}
    }
    data["sessions"][session_id] = session_record
    save_metadata(metadata_file, data)
    logger.info(f"Auto-created session {session_id} for user {user_id}")
    return session_record
```

**`src/api/session.py`:**
Replace `/session/create` with `/session/current`:
```python
@router.get("/current")
def get_current_session(current_user: dict = Depends(get_current_user)):
    """Get or create the user's active session."""
    session = get_or_create_user_session(METADATA_FILE, current_user["sub"])
    return {
        "session_id": session["session_id"],
        "status": session["status"],
        "total_files": len(session["files"]),
        "total_mb": round(session["total_bytes"] / (1024 * 1024), 2)
    }
```

**`static/index.html`:**
Remove settings panel, auto-fetch session on load:
```javascript
async function initSession() {
  try {
    const res = await Auth.apiFetch('/session/current', {}, apiBase());
    const data = await res.json();
    state.sessionId = data.session_id;
    $('session-id-text').textContent = data.session_id.slice(0, 8) + '…';
    $('session-dot').classList.add('active');
    logger.info('Session ready: ' + data.session_id);
  } catch(e) {
    toast('Failed to initialize session: ' + e.message, 5000);
  }
}

// Call on page load
window.addEventListener('load', () => {
  initSession();
  // ... rest of init
});
```

---

#### Task 1.2 — Remove Completed State & Enable Multiple Process Cycles

**Change:** Session never transitions to "completed". Files track their own completion, but the session remains "active" indefinitely.

**Files to modify:**
- `src/services/sarvam_client.py`
- `src/api/process.py`
- `static/index.html`

**Implementation:**

**`src/services/sarvam_client.py`:**
At the end of `transcribe_with_batch()`, remove the line:
```python
# REMOVE THIS:
update_session(metadata_file, session_id, {"status": "completed"})

# Session stays "active" — only individual files change status
```

**`src/api/process.py`:**
Remove the completed session check:
```python
@router.post("/process-audio")
def process_audio(request: ProcessRequest, ...):
    session = get_session_or_404(METADATA_FILE, request.session_id)
    
    # REMOVE these checks:
    # if session["status"] == "completed":
    #     return {"message": "Session already processed", ...}
    
    # Allow processing regardless of previous state
    if session["status"] == "processing":
        return {"message": "Already processing", ...}
    
    # Get only files that are in 'uploaded' status
    file_paths = [
        str(get_session_dir(request.session_id) / r["stored_filename"])
        for r in session["files"].values()
        if r["status"] == "uploaded"
    ]
    
    if not file_paths:
        raise HTTPException(400, "No new files to process")
    
    # ... rest unchanged
```

**`static/index.html`:**
Remove "Start New Session" button and logic:
```javascript
// DELETE entire startNewSession() function
// DELETE <button id="new-session-btn" onclick="startNewSession()">

// In renderResults(), remove:
// if (['completed', 'failed'].includes(data.session_status)) {
//   $('new-session-btn').style.display = 'inline-block';
// }
```

---

#### Task 1.3 — 30-Minute Idle Timeout → Auto Logout

**Change:** Increase idle timeout to 30 minutes. On expiry, logout instead of creating new session.

**Files to modify:**
- `static/index.html`

**Implementation:**

```javascript
const IDLE_MS = 30 * 60 * 1000;  // Change from 10 to 30 minutes

async function autoLogout() {
  toast('Session expired after 30 min of inactivity — logging out…', 4000);
  await Auth.logout(apiBase());
}

function resetIdleTimer() {
  idleSeconds = 0;
  clearTimeout(idleTimer);
  idleTimer = setTimeout(autoLogout, IDLE_MS);  // Changed from autoNewSession
}

function startIdleCounter() {
  clearInterval(idleCounterTimer);
  idleCounterTimer = setInterval(() => {
    idleSeconds++;
    $('idle-display').textContent = fmtTime(idleSeconds);
    if (idleSeconds === (IDLE_MS / 1000) - 60) {
      toast('You will be logged out in 1 minute due to inactivity.', 5000);
    }
  }, 1000);
}
```

---

#### Task 1.4 — Results Accumulation

**Change:** Results view shows all files ever uploaded in the session, regardless of processing state.

**Files to modify:**
- `static/index.html`

**Implementation:**

```javascript
function renderResults(data) {
  // Show total stats across ALL files, not just current batch
  const total     = data.files.length;
  const completed = data.files.filter(f => f.status === 'completed').length;
  const uploaded  = data.files.filter(f => f.status === 'uploaded').length;
  const failed    = data.files.filter(f => f.status === 'failed').length;
  
  let statusMsg = '';
  if (uploaded > 0) {
    statusMsg = `${uploaded} file${uploaded > 1 ? 's' : ''} ready to process`;
  } else if (completed === total) {
    statusMsg = `All ${total} file${total > 1 ? 's' : ''} processed`;
  } else {
    statusMsg = `${completed} / ${total} completed`;
  }
  
  setStatusBanner('idle', statusMsg);
  
  // Render ALL files, not just recently processed
  $('results-list').innerHTML = data.files
    .sort((a, b) => new Date(b.uploaded_at || 0) - new Date(a.uploaded_at || 0))
    .map(f => buildResultCard(f))
    .join('');
}
```

---

### Phase 2: API Key Management & Usage Tracking

#### Task 2.1 — Backend API Key Storage

**Change:** Store API keys in database, not sessionStorage. Keys are encrypted at rest.

**Files to create/modify:**
- `config/db_schema.yaml` — add `api_keys` table
- `src/api/api_keys.py` — new router for key management
- `src/services/api_key_service.py` — encryption, storage, retrieval

**Implementation:**

**`config/db_schema.yaml`:**
Add new table:
```yaml
  api_keys:
    description: "Encrypted API keys per user"
    columns:
      - name: id
        type: uuid
        primary_key: true
        default: gen_random_uuid()
      
      - name: user_id
        type: uuid
        nullable: false
        references:
          table: users
          column: id
          on_delete: CASCADE
      
      - name: provider
        type: varchar(50)
        nullable: false
      
      - name: encrypted_key
        type: text
        nullable: false
      
      - name: created_at
        type: timestamptz
        default: now()
      
      - name: last_used_at
        type: timestamptz
```

**`src/services/api_key_service.py`:**
```python
import os
from cryptography.fernet import Fernet
from db.connection import get_connection

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # Add to .env
cipher = Fernet(ENCRYPTION_KEY.encode())

def save_api_key(user_id: str, provider: str, plain_key: str):
    """Encrypt and store API key."""
    encrypted = cipher.encrypt(plain_key.encode()).decode()
    conn = get_connection(dbname=os.getenv("DB_NAME"))
    cur = conn.cursor()
    try:
        # Upsert
        cur.execute(f"""
            INSERT INTO audio_analyzer_1.api_keys (user_id, provider, encrypted_key)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, provider) 
            DO UPDATE SET encrypted_key = EXCLUDED.encrypted_key
        """, (user_id, provider, encrypted))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_api_key(user_id: str, provider: str) -> str | None:
    """Retrieve and decrypt API key."""
    conn = get_connection(dbname=os.getenv("DB_NAME"))
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT encrypted_key FROM audio_analyzer_1.api_keys
            WHERE user_id = %s AND provider = %s
        """, (user_id, provider))
        row = cur.fetchone()
        if not row:
            return None
        return cipher.decrypt(row[0].encode()).decode()
    finally:
        cur.close()
        conn.close()
```

**`src/api/api_keys.py`:**
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from utils.jwt import get_current_user
from src.services.api_key_service import save_api_key, get_api_key

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

class SaveKeysRequest(BaseModel):
    sarvam_key: str | None = None
    google_key: str | None = None

@router.post("/save")
def save_keys(req: SaveKeysRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    if req.sarvam_key:
        save_api_key(user_id, "sarvam", req.sarvam_key)
    if req.google_key:
        save_api_key(user_id, "gemini", req.google_key)
    return {"message": "API keys saved"}

@router.get("/status")
def key_status(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    return {
        "sarvam_configured": get_api_key(user_id, "sarvam") is not None,
        "gemini_configured": get_api_key(user_id, "gemini") is not None
    }
```

**`main.py`:**
```python
from src.api.api_keys import router as api_keys_router
app.include_router(api_keys_router)
```

**`static/index.html`:**
Change API key inputs to call `/api-keys/save`:
```javascript
async function saveApiKeys() {
  const sarvamKey = $('sarvam-api-key').value.trim();
  const googleKey = $('google-api-key').value.trim();
  
  try {
    const res = await Auth.apiFetch('/api-keys/save', {
      method: 'POST',
      body: JSON.stringify({
        sarvam_key: sarvamKey || null,
        google_key: googleKey || null
      })
    }, apiBase());
    
    if (res.ok) {
      toast('API keys saved securely ✓');
      // Clear input fields for security
      $('sarvam-api-key').value = '';
      $('google-api-key').value = '';
    }
  } catch(e) {
    toast('Failed to save keys: ' + e.message, 5000);
  }
}
```

---

#### Task 2.2 — API Usage Tracking

**Change:** Track API calls and token consumption per user.

**Files to create/modify:**
- `config/db_schema.yaml` — add `api_usage` table
- `src/services/usage_tracker.py` — new service
- `src/services/sarvam_client.py` — integrate tracking
- `src/services/gemini_client.py` — integrate tracking

**Implementation:**

**`config/db_schema.yaml`:**
```yaml
  api_usage:
    description: "Track API consumption per user"
    columns:
      - name: id
        type: uuid
        primary_key: true
        default: gen_random_uuid()
      
      - name: user_id
        type: uuid
        nullable: false
        references:
          table: users
          column: id
          on_delete: CASCADE
      
      - name: provider
        type: varchar(50)
        nullable: false
      
      - name: session_id
        type: varchar(255)
      
      - name: file_id
        type: varchar(255)
      
      - name: request_type
        type: varchar(100)
      
      - name: tokens_used
        type: integer
      
      - name: cost_estimate
        type: numeric(10, 6)
      
      - name: timestamp
        type: timestamptz
        default: now()
```

**`src/services/usage_tracker.py`:**
```python
from db.connection import get_connection
import os

def log_usage(user_id: str, provider: str, session_id: str, file_id: str, 
              request_type: str, tokens: int = 0, cost: float = 0):
    """Record API usage event."""
    conn = get_connection(dbname=os.getenv("DB_NAME"))
    cur = conn.cursor()
    try:
        cur.execute(f"""
            INSERT INTO audio_analyzer_1.api_usage 
            (user_id, provider, session_id, file_id, request_type, tokens_used, cost_estimate)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, provider, session_id, file_id, request_type, tokens, cost))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_user_usage(user_id: str, provider: str) -> dict:
    """Get total usage for a user and provider."""
    conn = get_connection(dbname=os.getenv("DB_NAME"))
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT 
                COUNT(*) as request_count,
                SUM(tokens_used) as total_tokens,
                SUM(cost_estimate) as total_cost
            FROM audio_analyzer_1.api_usage
            WHERE user_id = %s AND provider = %s
        """, (user_id, provider))
        row = cur.fetchone()
        return {
            "requests": row[0] or 0,
            "tokens": row[1] or 0,
            "cost_usd": float(row[2] or 0)
        }
    finally:
        cur.close()
        conn.close()
```

**`src/services/sarvam_client.py`:**
Wrap Sarvam calls:
```python
from src.services.usage_tracker import log_usage

def transcribe_with_batch(file_paths, session_id, metadata_file, user_id: str):
    # ... existing code ...
    
    job = client.speech_to_text_job.create_job(...)
    
    # Log job creation
    log_usage(user_id, "sarvam", session_id, None, "batch_job_create")
    
    # ... after job completes ...
    for job_detail in job_details:
        # Estimate tokens (Sarvam charges by audio duration)
        # Rough: 1 minute audio ≈ 150 tokens, $0.002/min
        duration_min = file_size_bytes / (1024 * 1024 * 2)  # Rough estimate
        tokens = int(duration_min * 150)
        cost = duration_min * 0.002
        
        log_usage(user_id, "sarvam", session_id, matched_file_id, 
                 "transcription", tokens, cost)
```

**`src/services/srt_generator.py`:**
```python
from src.services.usage_tracker import log_usage

def generate_srt_from_diarization(diarized_transcript, session_id, file_id, user_id: str):
    # ... existing code ...
    
    response = llm.invoke(prompt)
    
    # Log Gemini usage (estimate tokens from response)
    input_tokens = len(json.dumps(diarized_transcript)) // 4
    output_tokens = len(response.content) // 4
    total_tokens = input_tokens + output_tokens
    cost = (input_tokens * 0.00001 + output_tokens * 0.00003)  # Flash pricing
    
    log_usage(user_id, "gemini", session_id, file_id, "srt_generation", 
             total_tokens, cost)
    
    # ... rest unchanged
```

---

#### Task 2.3 — API Quota Enforcement

**Change:** Check usage before processing, return error if limits exceeded.

**Files to create/modify:**
- `src/services/quota_checker.py` — new service
- `src/api/process.py` — add quota check

**Implementation:**

**`src/services/quota_checker.py`:**
```python
from src.services.usage_tracker import get_user_usage
from fastapi import HTTPException

# Define free tier limits (adjust as needed)
LIMITS = {
    "sarvam": {"requests": 100, "cost_usd": 5.0},
    "gemini": {"requests": 500, "cost_usd": 10.0}
}

def check_quota(user_id: str) -> dict:
    """Check if user has quota remaining for both providers."""
    sarvam_usage = get_user_usage(user_id, "sarvam")
    gemini_usage = get_user_usage(user_id, "gemini")
    
    issues = []
    if sarvam_usage["requests"] >= LIMITS["sarvam"]["requests"]:
        issues.append(f"Sarvam request limit reached ({LIMITS['sarvam']['requests']})")
    if sarvam_usage["cost_usd"] >= LIMITS["sarvam"]["cost_usd"]:
        issues.append(f"Sarvam cost limit reached (${LIMITS['sarvam']['cost_usd']})")
    if gemini_usage["requests"] >= LIMITS["gemini"]["requests"]:
        issues.append(f"Gemini request limit reached ({LIMITS['gemini']['requests']})")
    if gemini_usage["cost_usd"] >= LIMITS["gemini"]["cost_usd"]:
        issues.append(f"Gemini cost limit reached (${LIMITS['gemini']['cost_usd']})")
    
    if issues:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "API quota exceeded",
                "issues": issues,
                "sarvam_usage": sarvam_usage,
                "gemini_usage": gemini_usage
            }
        )
    
    return {
        "sarvam": sarvam_usage,
        "gemini": gemini_usage,
        "limits": LIMITS
    }
```

**`src/api/process.py`:**
```python
from src.services.quota_checker import check_quota

@router.post("/process-audio")
def process_audio(request: ProcessRequest, ...):
    user_id = current_user["sub"]
    
    # Check quota BEFORE processing
    try:
        quota_status = check_quota(user_id)
    except HTTPException as e:
        # Return quota error to frontend
        raise e
    
    # ... rest of processing unchanged
```

**`static/index.html`:**
Handle 429 quota errors:
```javascript
async function processFiles() {
  try {
    const res = await Auth.apiFetch('/process-audio', {
      method: 'POST',
      body: JSON.stringify({ session_id: state.sessionId })
    }, apiBase());
    
    if (res.status === 429) {
      const err = await res.json();
      const issues = err.detail.issues.join('\n');
      alert(`API Quota Exceeded\n\n${issues}\n\nPlease upgrade or wait for quota reset.`);
      return;
    }
    
    if (!res.ok) throw new Error('HTTP ' + res.status);
    
    // ... rest unchanged
  } catch(e) {
    toast('Process error: ' + e.message, 5000);
  }
}
```

---

#### Task 2.4 — Usage Dashboard (Optional Enhancement)

**Change:** Add endpoint and UI to show current usage stats.

**Files to create/modify:**
- `src/api/api_keys.py` — add `/usage` endpoint
- `static/index.html` — add usage display

**Implementation:**

**`src/api/api_keys.py`:**
```python
from src.services.usage_tracker import get_user_usage
from src.services.quota_checker import LIMITS

@router.get("/usage")
def get_usage_stats(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    sarvam = get_user_usage(user_id, "sarvam")
    gemini = get_user_usage(user_id, "gemini")
    
    return {
        "sarvam": {
            **sarvam,
            "limit_requests": LIMITS["sarvam"]["requests"],
            "limit_cost": LIMITS["sarvam"]["cost_usd"],
            "percent_used": (sarvam["cost_usd"] / LIMITS["sarvam"]["cost_usd"]) * 100
        },
        "gemini": {
            **gemini,
            "limit_requests": LIMITS["gemini"]["requests"],
            "limit_cost": LIMITS["gemini"]["cost_usd"],
            "percent_used": (gemini["cost_usd"] / LIMITS["gemini"]["cost_usd"]) * 100
        }
    }
```

**`static/index.html`:**
Add usage meter in header:
```javascript
async function updateUsageDisplay() {
  const res = await Auth.apiFetch('/api-keys/usage', {}, apiBase());
  const data = await res.json();
  
  $('usage-display').innerHTML = `
    Sarvam: ${data.sarvam.requests}/${data.sarvam.limit_requests} calls
    (${data.sarvam.percent_used.toFixed(0)}%) · 
    Gemini: ${data.gemini.requests}/${data.gemini.limit_requests} calls
    (${data.gemini.percent_used.toFixed(0)}%)
  `;
}

// Call after each processing job completes
```

---

## Metadata Schema Changes

```json
{
  "sessions": {
    "session-uuid": {
      "session_id": "session-uuid",
      "user_id": "user-uuid",              // NEW: link to users table
      "created_at": "2026-04-10T10:00:00Z",
      "status": "active",                  // NEW: "active" or "archived"
      "total_bytes": 104857600,
      "files": {
        "sha256-hash": {
          "file_id": "file-uuid",
          "uploaded_at": "2026-04-10T10:05:00Z",  // NEW: track upload time
          "original_filename": "audio1.wav",
          "stored_filename": "file-uuid_audio1.wav",
          "file_size_bytes": 26214400,
          "status": "completed",           // Per-file status
          "transcript": "...",
          "diarized_transcript": {},
          "timestamps": [],
          "srt_output": "...",
          "srt_file_path": "/path/to/file.srt"
        }
      }
    }
  }
}
```

---

## Database Schema Changes

New tables added to `config/db_schema.yaml`:

1. **`api_keys`** — encrypted storage of user API keys
2. **`api_usage`** — log of all API calls with token/cost tracking

Modify `users` table:
- No changes needed

Modify `user_sessions` table:
- `status` column values change from "open/completed" to "active/archived"

---

## API Endpoint Changes

### New Endpoints
- `GET /session/current` — get or auto-create user's active session
- `POST /api-keys/save` — save encrypted API keys
- `GET /api-keys/status` — check if keys are configured
- `GET /api-keys/usage` — current usage stats

### Modified Endpoints
- `POST /process-audio` — now checks quota before processing
- `GET /results/{session_id}` — returns all files, not just current batch

### Removed Endpoints
- `POST /session/create` — replaced by auto-creation

---

## Frontend Changes Summary

**Removed:**
- "Save Settings" button and manual session creation
- "Start New Session" button
- Settings panel collapse/expand (keys saved immediately)

**Added:**
- Auto-session initialization on login
- API usage display in header
- Quota exceeded error modal
- Persistent results accumulation

**Modified:**
- Idle timeout: 10min → 30min
- Idle action: new session → logout
- Results view: shows all files ever uploaded
- Process button: allows re-processing after completion

---

## Migration Guide (V3 → V4)

1. **Database:**
   - Run `schema_loader.py` on startup — auto-creates new tables
   - Existing sessions will continue to work but won't have `user_id`
   - Optional: run migration script to link old sessions to users

2. **Environment Variables:**
   - Add `ENCRYPTION_KEY` to `.env` (generate with `Fernet.generate_key()`)

3. **Dependencies:**
   - Add `cryptography` to `requirements.txt`

4. **User Experience:**
   - First login after upgrade: users will see auto-created session
   - Old sessions remain visible in database but not linked to users

---

## Testing Checklist

**Phase 1:**
- [ ] User logs in → session auto-created
- [ ] Upload file → stays in same session
- [ ] Process files → completes, session still active
- [ ] Upload more files → still same session
- [ ] Process again → works, results accumulate
- [ ] Idle 30 min → auto logout
- [ ] Re-login → new session created

**Phase 2:**
- [ ] Save API keys → stored encrypted in database
- [ ] Keys not visible in browser storage or network tab
- [ ] Process files → usage logged
- [ ] View usage stats → accurate counts
- [ ] Exceed quota → 429 error, process blocked
- [ ] Usage resets (manual admin action for testing)

---

## Rollout Strategy

**Week 1: Phase 1 (Core Session Logic)**
- Deploy session auto-creation
- Remove completed state transitions
- Update frontend for continuous workflow
- Test thoroughly with real users

**Week 2: Phase 2 (API Management)**
- Deploy encrypted key storage
- Add usage tracking
- Implement quota enforcement
- Monitor for issues

**Week 3: Monitoring & Optimization**
- Collect usage data
- Adjust quota limits based on actual consumption
- Optimize database queries if needed

---

## Known Limitations

1. **No quota reset mechanism** — admins must manually clear `api_usage` table
2. **Usage estimates, not exact** — Sarvam charges by audio duration, we estimate
3. **No per-user quota customization** — all users share same limits
4. **Archived sessions not implemented** — old sessions remain "active" forever

Future versions can address these with proper admin tools and scheduled cleanups.

---

## File Summary

**New Files:**
- `src/api/api_keys.py`
- `src/services/api_key_service.py`
- `src/services/usage_tracker.py`
- `src/services/quota_checker.py`

**Modified Files:**
- `main.py` (add api_keys router)
- `config/db_schema.yaml` (add tables)
- `src/services/session_manager.py` (auto-creation logic)
- `src/api/session.py` (replace create with current)
- `src/api/process.py` (quota check)
- `src/services/sarvam_client.py` (usage tracking)
- `src/services/srt_generator.py` (usage tracking)
- `static/index.html` (remove manual session, add auto-init)
- `static/auth.js` (no changes needed)

**Dependencies:**
- Add `cryptography>=41.0.0` to `requirements.txt`

---

**Total Character Count: ~19,800**