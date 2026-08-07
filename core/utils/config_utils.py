import os
import threading
from ruamel.yaml import YAML

_lock = threading.Lock()
yaml = YAML()
yaml.preserve_quotes = True

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.yaml")

def load_config():
    with _lock:
        if not os.path.exists(CONFIG_PATH):
            return {}
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.load(f)

def load_key(key_path: str):
    """
    Load a specific key from config. Example: load_key("api.google_genai_key")
    """
    config = load_config()
    keys = key_path.split(".")
    for k in keys:
        if isinstance(config, dict) and k in config:
            config = config[k]
        else:
            return None
    return config

def update_key(key_path: str, value):
    """
    Update a specific key in config. Example: update_key("api.google_genai_key", "new_key")
    """
    with _lock:
        if not os.path.exists(CONFIG_PATH):
            config = {}
        else:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.load(f)
                
        if config is None:
            config = {}
            
        keys = key_path.split(".")
        current = config
        for i, k in enumerate(keys[:-1]):
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
        
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
