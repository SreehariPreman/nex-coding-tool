"""Configuration loader and validator for Nex CLI."""

import os
from pathlib import Path
from typing import Any, Dict, Tuple
import requests

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib

def load_config(cwd: str) -> Dict[str, Any]:
    global_path = Path.home() / ".nex" / "config.toml"
    local_path = Path(cwd) / "nex.toml"

    config: Dict[str, Any] = {
        "provider": None,
        "model": None,
        "api_key": None,
        "_source": "None"
    }

    if global_path.exists():
        try:
            with global_path.open("rb") as f:
                config.update(tomllib.load(f))
                config["_source"] = "~/.nex/config.toml"
        except Exception:
            pass

    if local_path.exists():
        try:
            with local_path.open("rb") as f:
                local_config = tomllib.load(f)
                config.update(local_config)
                config["_source"] = "nex.toml"
        except Exception:
            pass
            
    # Allow overriding api_key from environment variables as a convenience
    if config.get("provider") == "openai" and "OPENAI_API_KEY" in os.environ:
        config["api_key"] = config.get("api_key") or os.environ["OPENAI_API_KEY"]
    elif config.get("provider") == "anthropic" and "ANTHROPIC_API_KEY" in os.environ:
        config["api_key"] = config.get("api_key") or os.environ["ANTHROPIC_API_KEY"]

    return config

def validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """Returns (is_valid, error_message)."""
    provider = str(config.get("provider", "")).lower()
    api_key = config.get("api_key", "")

    if not provider or provider == "none":
        return False, "No config found / No provider specified"

    if provider == "ollama":
        # Check if local Ollama process is running
        try:
            res = requests.get("http://localhost:11434/api/tags", timeout=2)
            if res.status_code == 200:
                return True, "valid"
        except Exception:
            pass
        return False, "Ollama not running on localhost:11434"

    if not api_key:
        return False, "API key missing"

    # Minimal validations to avoid long network hangs, but check plausibility or endpoint
    if provider == "openai":
        if not api_key.startswith("sk-"): # Note: Some new standard openai keys might differ, but commonly sk-
            pass
        try:
            res = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=3
            )
            if res.status_code == 401:
                return False, "API key invalid"
        except Exception:
            pass
        return True, "valid"

    elif provider == "anthropic":
        if not api_key.startswith("sk-ant"):
            return False, "API key invalid"
        return True, "valid"

    elif provider == "google":
        if not api_key.startswith("AIza"):
            return False, "API key invalid"
        return True, "valid"

    return False, f"Unknown provider: {provider}"
