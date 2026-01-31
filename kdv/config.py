"""
Configuration management for kdv.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG = {
    "paths": {
        "raw": "Raw_HoverAir_Vids",
        "broll": "BRoll",
        "proxy": "proxy",
        "archive": "archive",
        "thumbnails": ".thumbnails",
        "projects": "Projects",
        "edits": "Edits",
    },
    "conversion": {
        "target_fps": 30,
        "quality": "balanced",
    },
    "proxy": {
        "resolution": 540,
        "crf": 28,
        "preset": "ultrafast",
    },
    "thumbnails": {
        "timestamp": "00:00:03",
        "format": "jpg",
        "quality": 85,
        "contact_sheet": {
            "enabled": True,
            "cols": 4,
            "rows": 4,
            "width": 1920,
        },
    },
    "export": {
        "default_preset": "youtube-1080",
    },
    "ingest": {
        "naming_pattern": "HOVER_X1PROMAX_{seq:04d}",
        "copy_mode": "copy",
        "verify_checksum": True,
        "create_dated_folders": False,
    },
}


class Config:
    """Configuration manager for kdv."""

    def __init__(self, config_path: Optional[Path] = None):
        self.base_dir = self._find_base_dir()
        self.config_path = config_path or self.base_dir / "config" / "kdv.yaml"
        self._config = self._load_config()

    def _find_base_dir(self) -> Path:
        """Find the kdv project base directory."""
        # Start from current directory and look for kdv markers
        cwd = Path.cwd()

        # Check if we're in the Kdenlive directory
        if (cwd / "config" / "kdv.yaml").exists():
            return cwd
        if (cwd / "kdv").is_dir() and (cwd / "pyproject.toml").exists():
            return cwd

        # Check common locations
        movies_kdenlive = Path.home() / "Movies" / "Kdenlive"
        if movies_kdenlive.exists():
            return movies_kdenlive

        # Fall back to current directory
        return cwd

    def _load_config(self) -> dict:
        """Load configuration from YAML file, merging with defaults."""
        config = DEFAULT_CONFIG.copy()

        if self.config_path.exists():
            with open(self.config_path) as f:
                user_config = yaml.safe_load(f) or {}
            config = self._deep_merge(config, user_config)

        return config

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation (e.g., 'paths.raw')."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_path(self, key: str) -> Path:
        """Get a path config value as an absolute Path."""
        rel_path = self.get(f"paths.{key}")
        if rel_path:
            return self.base_dir / rel_path
        raise KeyError(f"Unknown path key: {key}")

    @property
    def raw_dir(self) -> Path:
        return self.get_path("raw")

    @property
    def broll_dir(self) -> Path:
        return self.get_path("broll")

    @property
    def proxy_dir(self) -> Path:
        return self.get_path("proxy")

    @property
    def archive_dir(self) -> Path:
        return self.get_path("archive")

    @property
    def thumbnails_dir(self) -> Path:
        return self.get_path("thumbnails")

    @property
    def projects_dir(self) -> Path:
        return self.get_path("projects")

    @property
    def edits_dir(self) -> Path:
        return self.get_path("edits")

    def get_broll_categories(self) -> dict:
        """Get B-roll category structure."""
        return self.get("broll_categories", {"motion": [], "vibes": []})

    def get_export_preset(self, name: str) -> dict:
        """Get an export preset by name."""
        presets = self.get("export.presets", {})
        if name not in presets:
            raise KeyError(f"Unknown export preset: {name}")
        return presets[name]

    def get_quality_settings(self, quality: str) -> dict:
        """Get FFmpeg settings for a quality preset."""
        presets = {
            "fast": {"crf": 23, "preset": "fast"},
            "balanced": {"crf": 18, "preset": "medium"},
            "quality": {"crf": 15, "preset": "slow"},
        }
        return presets.get(quality, presets["balanced"])


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config(config_path: Optional[Path] = None) -> Config:
    """Reload configuration from disk."""
    global _config
    _config = Config(config_path)
    return _config
