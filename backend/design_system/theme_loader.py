"""
backend/design_system/theme_loader.py
=====================================
Theme loading and caching.

Loads theme JSON files from ``backend/themes/`` and exposes the active theme
for component renderers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.design_system.theme import DesignTheme
from schemas.theme import Theme as ThemeSchema

logger = logging.getLogger(__name__)

_THEMES_DIR = Path(__file__).resolve().parents[1] / "themes"
_DEFAULT_THEME_NAME = "ey_blue"

_theme_cache: dict[str, DesignTheme] = {}
_active_theme_name: str = _DEFAULT_THEME_NAME


def load_theme(theme_name: str) -> DesignTheme:
    """
    Load a theme by name from ``backend/themes/{theme_name}.json``.

    Falls back to the default theme if the requested file is missing or
    invalid. Loaded themes are cached.
    """
    if theme_name in _theme_cache:
        return _theme_cache[theme_name]

    path = _THEMES_DIR / f"{theme_name}.json"
    if not path.exists():
        logger.warning(
            "Theme '%s' not found at %s; falling back to '%s'.",
            theme_name,
            path,
            _DEFAULT_THEME_NAME,
        )
        return load_theme(_DEFAULT_THEME_NAME)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        schema = ThemeSchema.model_validate(data)
        theme = DesignTheme(schema)
        _theme_cache[theme_name] = theme
        logger.info("design_system: loaded theme '%s'", theme_name)
        return theme
    except Exception as exc:
        logger.warning(
            "Failed to load theme '%s': %s; falling back to '%s'.",
            theme_name,
            exc,
            _DEFAULT_THEME_NAME,
        )
        return load_theme(_DEFAULT_THEME_NAME)


def get_current_theme() -> DesignTheme:
    """Return the currently active theme."""
    return load_theme(_active_theme_name)


def set_active_theme(theme_name: str) -> DesignTheme:
    """Switch the active theme and return it."""
    global _active_theme_name
    _active_theme_name = theme_name
    return load_theme(theme_name)


def clear_cache() -> None:
    """Clear the theme cache. Useful for tests."""
    global _theme_cache
    _theme_cache = {}
