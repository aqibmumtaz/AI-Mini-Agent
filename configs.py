
# --- IMPORTS ---
import os
from dotenv import load_dotenv


 # --- CONFIGS CLASS ---
class Configs:
    """
    Configs class loads .env variables and provides class-level access.
    Usage: Configs.load_configs(); then access variables as Configs.RETELL_API_KEY
    """

    TITLE = None
    OPENAI_API_KEY = None

    JIRA_USER = None
    JIRA_API_TOKEN = None
    JIRA_BASE_URL = None
    TEMPO_API_TOKEN = None
    TEMPO_USER_KEY = None

    _TYPES = {
        "TITLE": str,
        "OPENAI_API_KEY": str,
        "JIRA_USER": str,
        "JIRA_API_TOKEN": str,
        "JIRA_BASE_URL": str,
        "TEMPO_API_TOKEN": str,
        "TEMPO_USER_KEY": str,
        "WORKLOG_API_SOURCE": str,  # "jira" or "tempo"
        # "MAX_CALLS": int,
        # "THRESHOLD": float,
        # "DEBUG_MODE": bool,
    }

    @classmethod
    def _convert_type(cls, value, target_type):
        if value is None:
            return None
        try:
            if target_type == int:
                return int(value)
            elif target_type == float:
                return float(value)
            elif target_type == bool:
                return value.lower() in ("true", "1", "yes")
            else:
                return value
        except Exception:
            return value

    @classmethod
    def load_configs(cls):
        load_dotenv()
        for key, typ in cls._TYPES.items():
            val = os.getenv(key)
            setattr(cls, key, cls._convert_type(val, typ))


# Ensure configs are loaded on import
Configs.load_configs()
