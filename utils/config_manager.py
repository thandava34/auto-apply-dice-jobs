# dice_auto_apply/utils/config_manager.py

import os
import json
import copy
import tempfile
import threading
from pathlib import Path

_SINGLETON: "ConfigManager | None" = None
_CONFIG_LOCK = threading.RLock()

_DEFAULT_CONFIG = {
    "search_queries": ["AI ML", "Gen AI", "Agentic AI", "Data Engineer", "Data Analyst", "Machine Learning"],
    "exclude_keywords": ["Manager", "Director", ".net", "SAP", "java", "w2 only", "only w2", "no c2c"],
    "include_keywords": ["AI", "Machine Learning", "Data", "NLP", "ETL", "Python", "RAG", "LLM"],
    "resume_profiles": [],
    "headless_mode": False,
    "job_application_limit": 50,
    "save_logs": True,
    "profile_name_boost_mode": "high",
    "auto_answer_questions": False,
    "review_before_submit": False,
    "question_matching_enabled": True,
    "question_groq_ambiguity": True,
    "allow_ai_generated_application_answers": False,
    "application_answers": {},
    "minimum_ats_fit": 25.0,
    "auto_attach_missed_kws": False,
}

def get_config() -> "ConfigManager":
    """Return the process-wide ConfigManager singleton (avoids repeated disk reads)."""
    global _SINGLETON
    with _CONFIG_LOCK:
        if _SINGLETON is None:
            _SINGLETON = ConfigManager()
        return _SINGLETON

def invalidate_config_cache():
    """Force-reload on the next get_config() call (call after saving settings)."""
    global _SINGLETON
    with _CONFIG_LOCK:
        _SINGLETON = None

class ConfigManager:
    """Manages application configuration settings."""
    
    def __init__(self, config_dir: str | None = None):
        """Initialize the configuration manager."""
        self._owns_singleton = config_dir is None
        self.config_dir = config_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
        self.config_file = os.path.join(self.config_dir, "settings.json")
        self.config = self._load_config()
        
    def _load_config(self):
        """Load configuration from file."""
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Create default config if it doesn't exist
        if not os.path.exists(self.config_file):
            default_config = copy.deepcopy(_DEFAULT_CONFIG)
            
            # Write default config to file
            self._atomic_write(default_config)
            
            return default_config
        
        # Load existing config
        try:
            with _CONFIG_LOCK, open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("settings.json must contain a JSON object")
            # Backfill any keys added after initial install
            if 'profile_name_boost_mode' not in data:
                # Migrate old bool key if present
                old_val = data.pop('profile_name_boost', None)
                data['profile_name_boost_mode'] = 'off' if old_val is False else 'high'
            for key, value in _DEFAULT_CONFIG.items():
                data.setdefault(key, copy.deepcopy(value))
            return self._validate(data)
        except Exception as e:
            print(f"Error loading config: {e}")
            return copy.deepcopy(_DEFAULT_CONFIG)

    @staticmethod
    def _validate(data: dict) -> dict:
        validated = dict(data)
        for key in ("search_queries", "exclude_keywords", "include_keywords", "resume_profiles"):
            if not isinstance(validated.get(key), list):
                validated[key] = copy.deepcopy(_DEFAULT_CONFIG[key])
        if not isinstance(validated.get("application_answers"), dict):
            validated["application_answers"] = {}
        for key in (
            "headless_mode", "save_logs", "auto_answer_questions", "review_before_submit",
            "question_matching_enabled", "question_groq_ambiguity",
            "allow_ai_generated_application_answers", "auto_attach_missed_kws",
        ):
            if not isinstance(validated.get(key), bool):
                validated[key] = bool(_DEFAULT_CONFIG[key])
        try:
            validated["job_application_limit"] = max(0, int(validated.get("job_application_limit", 50)))
        except (TypeError, ValueError):
            validated["job_application_limit"] = 50
        try:
            validated["minimum_ats_fit"] = min(100.0, max(0.0, float(validated.get("minimum_ats_fit", 25))))
        except (TypeError, ValueError):
            validated["minimum_ats_fit"] = 25.0
        mode = str(validated.get("profile_name_boost_mode", "high")).lower()
        validated["profile_name_boost_mode"] = mode if mode in {"off", "low", "high", "exact"} else "high"
        return validated

    def _atomic_write(self, data: dict):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.config_dir,
                prefix="settings.", suffix=".tmp", delete=False
            ) as handle:
                temp_path = handle.name
                json.dump(data, handle, indent=4)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.config_file)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    
    def save_config(self):
        """Save configuration to file."""
        try:
            global _SINGLETON
            with _CONFIG_LOCK:
                self.config = self._validate(self.config)
                self._atomic_write(self.config)
                if self._owns_singleton:
                    _SINGLETON = self
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get(self, key, default=None):
        """Get a configuration value."""
        with _CONFIG_LOCK:
            return self.config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value."""
        with _CONFIG_LOCK:
            self.config[key] = value
            return self.save_config()
