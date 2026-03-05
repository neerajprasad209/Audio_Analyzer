import yaml
from config.path import SETTINGS_PATH
from utils.logger import logger


def load_settings():
    """
    Load YAML settings file.
    """
    try:
        with open(SETTINGS_PATH, "r") as file:
            return yaml.safe_load(file)
    except Exception:
        logger.exception("Failed to load settings.yaml")
        raise