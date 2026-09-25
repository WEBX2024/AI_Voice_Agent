"""
Prompt loader.

Dynamically loads prompt files from the prompts/ directory and assembles
them into a system prompt for the LLM.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_prompt_file(filepath: Path) -> str:
    """Load a single prompt file and return its content."""
    try:
        content = filepath.read_text(encoding="utf-8").strip()
        logger.debug("Loaded prompt: %s (%d chars)", filepath.name, len(content))
        return content
    except FileNotFoundError:
        logger.warning("Prompt file not found: %s", filepath)
        return ""
    except Exception as e:  # noqa: BLE001
        logger.error("Error loading prompt %s: %s", filepath, e)
        return ""


def load_system_prompt(prompts_dir: Path) -> str:
    """Load the single system prompt file."""
    system_prompt_path = prompts_dir / "system.md"
    try:
        content = system_prompt_path.read_text(encoding="utf-8").strip()
        logger.info("Loaded system prompt from %s (%d chars)", system_prompt_path.name, len(content))
        return content
    except FileNotFoundError:
        logger.warning("System prompt file not found: %s", system_prompt_path)
        return ""
    except Exception as e:  # noqa: BLE001
        logger.error("Error loading system prompt %s: %s", system_prompt_path, e)
        return ""
