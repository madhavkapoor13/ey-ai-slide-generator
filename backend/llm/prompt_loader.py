"""
backend/llm/prompt_loader.py
==============================
Centralized prompt loading for all AI modules.

Loads ``backend/ai/instructions.md`` once at startup and composes module
prompts with global instructions for every LLM call.
"""

from __future__ import annotations

import threading
from pathlib import Path

_AI_DIR = Path(__file__).resolve().parents[1] / "ai"
_INSTRUCTIONS_PATH = _AI_DIR / "instructions.md"
_PROMPTS_DIR = _AI_DIR / "prompts"

_MODULE_FILES: dict[str, str] = {
    "intent": "intent.md",
    "context": "context.md",
    "process": "process.md",
    "content": "content.md",
    "validation": "validation.md",
    "presentation_planner": "presentation_planner.md",
}

_SECTION_SEPARATOR = "--------------------------------------------------"

_global_instructions: str | None = None
_prompt_cache: dict[str, str] = {}
_initialized = False
_lock = threading.Lock()


def initialize_prompts() -> None:
    """Load and cache global instructions once at application startup."""
    global _global_instructions, _initialized

    with _lock:
        if _initialized:
            return
        _global_instructions = _INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        _initialized = True


def get_global_instructions() -> str:
    """Return cached global instructions from ``instructions.md``."""
    if not _initialized:
        initialize_prompts()
    return _global_instructions or ""


def get_prompt(module_name: str) -> str:
    """Return the module-specific prompt body for ``module_name``."""
    if module_name not in _MODULE_FILES:
        raise ValueError(
            f"Unknown module prompt: {module_name!r}. "
            f"Expected one of: {', '.join(sorted(_MODULE_FILES))}"
        )

    if module_name not in _prompt_cache:
        prompt_path = _PROMPTS_DIR / _MODULE_FILES[module_name]
        _prompt_cache[module_name] = prompt_path.read_text(encoding="utf-8")

    return _prompt_cache[module_name]


def build_prompt(
    module_name: str,
    user_input: str,
    additional_context: str = "",
) -> str:
    """
    Compose a full prompt for an LLM call.

    Structure::

        GLOBAL INSTRUCTIONS  -> instructions.md
        MODULE INSTRUCTIONS  -> module prompt
        MODULE INPUT         -> optional additional_context + user_input
    """
    module_prompt = get_prompt(module_name)
    input_sections: list[str] = []

    if additional_context.strip():
        input_sections.append(additional_context.strip())
    if user_input.strip():
        input_sections.append(user_input.strip())

    module_input = "\n\n".join(input_sections)

    return "\n".join(
        [
            _SECTION_SEPARATOR,
            "",
            "GLOBAL INSTRUCTIONS",
            "",
            get_global_instructions(),
            "",
            _SECTION_SEPARATOR,
            "",
            "MODULE INSTRUCTIONS",
            "",
            module_prompt,
            "",
            _SECTION_SEPARATOR,
            "",
            "MODULE INPUT",
            "",
            module_input,
            "",
            _SECTION_SEPARATOR,
            "",
        ]
    )
