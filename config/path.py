from pathlib import Path

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent

# Folders
UPLOAD_DIR = BASE_DIR / "uploads"
CONFIG_DIR = BASE_DIR / "config"

# Files
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
ENV_PATH = BASE_DIR / ".env"

# Ensure upload folder exists
UPLOAD_DIR.mkdir(exist_ok=True)

# Metadata file for tracking uploads
METADATA_FILE = UPLOAD_DIR / "metadata.json"

# Session-scoped storage (one folder per active user session)
SESSION_ROOT_DIR = UPLOAD_DIR
SESSION_ROOT_DIR.mkdir(exist_ok=True)
