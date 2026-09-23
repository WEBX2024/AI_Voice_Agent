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
    except Exception as e:
        logger.error("Error loading prompt %s: %s", filepath, e)
        return ""


def load_prompts_from_directory(prompts_dir: Path) -> dict[str, str]:
    """
    Recursively load all .md prompt files from the prompts directory.

    Returns a dict mapping relative path (e.g., "system/personality") to content.
    """
    prompts = {}

    if not prompts_dir.exists():
        logger.warning("Prompts directory not found: %s", prompts_dir)
        return prompts

    for md_file in sorted(prompts_dir.rglob("*.md")):
        relative = md_file.relative_to(prompts_dir)
        # Key: "system/personality", "conversation/behaviour", etc.
        key = str(relative.with_suffix("")).replace("\\", "/")
        content = load_prompt_file(md_file)
        if content:
            prompts[key] = content
            logger.info("Loaded prompt: %s", key)

    logger.info("Loaded %d prompts from %s", len(prompts), prompts_dir)
    return prompts


def assemble_system_prompt(prompts: dict[str, str]) -> str:
    """
    Assemble all loaded prompts into a single system prompt string.

    Prompts are ordered by category for logical grouping:
    1. system/* — identity and personality
    2. conversation/* — conversation behaviour
    3. interruption/* — interruption handling
    4. reasoning/* — context and intent reasoning
    5. task/* — task execution
    6. tools/* — tool selection
    7. extraction/* — information extraction
    8. summary/* — call summaries
    9. output/* — structured output format
    """
    # Define category order
    category_order = [
        "system",
        "conversation",
        "interruption",
        "reasoning",
        "task",
        "tools",
        "extraction",
        "summary",
        "output",
    ]

    sections = []

    # Add prompts in category order
    for category in category_order:
        category_prompts = {
            k: v for k, v in prompts.items() if k.startswith(category + "/")
        }
        for key in sorted(category_prompts.keys()):
            sections.append(category_prompts[key])

    # Add any prompts that don't match known categories
    known_keys = set()
    for category in category_order:
        for k in prompts:
            if k.startswith(category + "/"):
                known_keys.add(k)

    for key in sorted(prompts.keys()):
        if key not in known_keys:
            sections.append(prompts[key])

    return "\n\n---\n\n".join(sections)
