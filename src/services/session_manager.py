import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from config.path import SESSION_ROOT_DIR
from utils.logger import logger

SESSION_TTL_SECONDS = 30 * 60
_CLEANUP_INTERVAL_SECONDS = 60

_sessions: dict[str, dict[str, object]] = {}
_sessions_lock = threading.Lock()
_cleanup_worker_started = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_to_epoch(value: str | None) -> float:
    if not value:
        return 0.0

    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except Exception:
        return 0.0


def _get_session_dir(session_id: str) -> Path:
    return SESSION_ROOT_DIR / session_id


def _get_audio_dir(session_id: str) -> Path:
    return _get_session_dir(session_id) / "audios"


def _get_results_dir(session_id: str) -> Path:
    return _get_session_dir(session_id) / "results"


def _get_metadata_path(session_id: str) -> Path:
    return _get_session_dir(session_id) / "metadata.json"


def _ensure_session_folder_layout(session_id: str) -> dict[str, Path]:
    session_dir = _get_session_dir(session_id)
    audio_dir = _get_audio_dir(session_id)
    results_dir = _get_results_dir(session_id)
    metadata_file = _get_metadata_path(session_id)

    session_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)

    if not metadata_file.exists():
        metadata = {
            "session_id": session_id,
            "folder_name": session_id,
            "created_at": _utc_now_iso(),
            "last_active_at": _utc_now_iso(),
            "files": {}
        }
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

    return {
        "session_dir": session_dir,
        "audio_dir": audio_dir,
        "results_dir": results_dir,
        "metadata_file": metadata_file
    }


def _update_metadata_last_active(session_id: str) -> None:
    metadata_file = _get_metadata_path(session_id)
    if not metadata_file.exists():
        return

    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception:
        logger.exception(f"Failed to read session metadata for last-active update: {session_id}")
        return

    metadata["last_active_at"] = _utc_now_iso()

    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
    except Exception:
        logger.exception(f"Failed to write session metadata for last-active update: {session_id}")


def load_session_metadata(session_id: str) -> dict:
    metadata_file = _get_metadata_path(session_id)
    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Session metadata not found")

    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception(f"Failed to load metadata for session: {session_id}")
        raise


def save_session_metadata(session_id: str, data: dict) -> None:
    metadata_file = _get_metadata_path(session_id)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _cleanup_session_folder(session_id: str) -> None:
    session_dir = _get_session_dir(session_id)
    if not session_dir.exists():
        return

    try:
        shutil.rmtree(session_dir)
        logger.info(f"Deleted session folder: {session_dir}")
    except Exception:
        logger.exception(f"Failed to delete session folder: {session_dir}")


def _read_managed_session_metadata(session_dir: Path) -> dict | None:
    metadata_file = session_dir / "metadata.json"
    if not metadata_file.exists():
        return None

    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception:
        logger.exception(f"Failed to inspect potential session folder: {session_dir}")
        return None

    folder_name = metadata.get("folder_name")
    session_id = metadata.get("session_id")
    files = metadata.get("files")

    if folder_name != session_dir.name:
        return None
    if session_id != session_dir.name:
        return None
    if not isinstance(files, dict):
        return None

    return metadata


def cleanup_expired_sessions() -> None:
    now = time.time()
    expired_ids: list[str] = []

    with _sessions_lock:
        for session_id, record in _sessions.items():
            last_active = float(record.get("last_active_epoch", 0.0))
            if now - last_active > SESSION_TTL_SECONDS:
                expired_ids.append(session_id)

    for session_id in expired_ids:
        end_session(session_id, reason="expired")

    # Cleanup stale folders that may remain after app restarts.
    try:
        for path in SESSION_ROOT_DIR.iterdir():
            if not path.is_dir():
                continue

            metadata = _read_managed_session_metadata(path)
            if not metadata:
                # Skip folders not created by this session lifecycle manager.
                continue

            session_id = str(metadata.get("session_id"))

            with _sessions_lock:
                if session_id in _sessions:
                    continue

            last_active_epoch = _iso_to_epoch(str(metadata.get("last_active_at")))
            if last_active_epoch == 0.0:
                last_active_epoch = _iso_to_epoch(str(metadata.get("created_at")))
            if last_active_epoch == 0.0:
                continue

            if now - last_active_epoch > SESSION_TTL_SECONDS:
                _cleanup_session_folder(session_id)
    except Exception:
        logger.exception("Failed during stale session folder cleanup")


def create_session(sarvam_api_key: str, gemini_api_key: str) -> dict[str, str]:
    if not sarvam_api_key or not gemini_api_key:
        raise HTTPException(status_code=400, detail="Both API keys are required")

    cleanup_expired_sessions()

    session_id = str(uuid.uuid4())
    paths = _ensure_session_folder_layout(session_id)
    now = time.time()

    with _sessions_lock:
        _sessions[session_id] = {
            "sarvam_api_key": sarvam_api_key,
            "gemini_api_key": gemini_api_key,
            "created_epoch": now,
            "last_active_epoch": now
        }

    logger.info(f"Created session workspace: {session_id}")

    return {
        "session_id": session_id,
        "folder_name": session_id,
        "session_dir": str(paths["session_dir"])
    }


def _require_session_record(session_id: str) -> dict[str, object]:
    cleanup_expired_sessions()

    now = time.time()
    expired = False
    record_snapshot: dict[str, object] | None = None

    with _sessions_lock:
        record = _sessions.get(session_id)
        if not record:
            raise HTTPException(status_code=404, detail="Session not found or already ended")

        last_active = float(record.get("last_active_epoch", 0.0))
        if now - last_active > SESSION_TTL_SECONDS:
            expired = True
        else:
            record["last_active_epoch"] = now
            record_snapshot = dict(record)

    if expired:
        end_session(session_id, reason="expired")
        raise HTTPException(status_code=401, detail="Session expired")

    _update_metadata_last_active(session_id)
    _ensure_session_folder_layout(session_id)

    if record_snapshot is None:
        raise HTTPException(status_code=404, detail="Session not available")

    return record_snapshot


def touch_session(session_id: str) -> None:
    _require_session_record(session_id)


def get_session_keys(session_id: str) -> tuple[str, str]:
    record = _require_session_record(session_id)
    sarvam_api_key = str(record.get("sarvam_api_key", "")).strip()
    gemini_api_key = str(record.get("gemini_api_key", "")).strip()

    if not sarvam_api_key or not gemini_api_key:
        raise HTTPException(status_code=400, detail="API keys are not available for this session")

    return sarvam_api_key, gemini_api_key


def get_session_paths(session_id: str) -> dict[str, Path]:
    _require_session_record(session_id)
    return _ensure_session_folder_layout(session_id)


def end_session(session_id: str, reason: str = "manual") -> bool:
    existed = False

    with _sessions_lock:
        if session_id in _sessions:
            _sessions.pop(session_id, None)
            existed = True

    if _get_session_dir(session_id).exists():
        _cleanup_session_folder(session_id)
        existed = True

    logger.info(f"Session ended: {session_id} (reason={reason})")
    return existed


def _cleanup_worker_loop() -> None:
    logger.info("Started session cleanup worker")
    while True:
        try:
            cleanup_expired_sessions()
        except Exception:
            logger.exception("Session cleanup worker iteration failed")
        time.sleep(_CLEANUP_INTERVAL_SECONDS)


def start_cleanup_worker() -> None:
    global _cleanup_worker_started
    if _cleanup_worker_started:
        return

    _cleanup_worker_started = True
    worker = threading.Thread(target=_cleanup_worker_loop, name="session-cleanup-worker", daemon=True)
    worker.start()


start_cleanup_worker()
