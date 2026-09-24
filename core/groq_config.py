"""One Groq credential shared by Dice and Nvoids."""
import json
import os
from pathlib import Path

from utils.config_manager import ConfigManager


def get_groq_key(config_dir=None, legacy=True):
    directory = Path(config_dir) if config_dir else Path(__file__).resolve().parents[1] / 'config'
    try:
        data = json.loads((directory / 'settings.json').read_text(encoding='utf-8'))
        for entry in data.get('api_keys_list', []):
            if isinstance(entry, dict) and str(entry.get('provider', '')).lower() == 'groq':
                key = str(entry.get('key', '')).strip()
                if key:
                    return key
        key = str(data.get('groq_api_key', '')).strip()
        if key:
            return key
    except (OSError, ValueError, TypeError):
        pass
    key = os.getenv('GROQ_API_KEY', '').strip()
    if key:
        return key
    if legacy:
        try:
            data = json.loads((directory / 'outreach_settings.json').read_text(encoding='utf-8'))
            return str(data.get('groq_api_key', '')).strip()
        except (OSError, ValueError, TypeError):
            pass
    return ''


def save_groq_key(key, config_dir=None):
    """Update the shared Dice key while retaining all non-Groq providers."""
    directory = Path(config_dir) if config_dir else Path(__file__).resolve().parents[1] / 'config'
    manager = ConfigManager(str(directory))
    entries = [e for e in manager.get('api_keys_list', [])
               if not (isinstance(e, dict) and str(e.get('provider', '')).lower() == 'groq')]
    key = str(key or '').strip()
    if key:
        entries.append({'provider': 'Groq', 'name': 'Shared Groq Key', 'key': key})
    manager.config['api_keys_list'] = entries
    manager.config['groq_api_key'] = ''  # Remove a legacy duplicate in Dice settings.
    if not manager.save_config():
        raise OSError('Could not save shared Groq key')
