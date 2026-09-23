"""
Voice Agent — CLI Entry Point.

Starts the voice agent runtime for local microphone/speaker interaction.

Usage:
    python main.py
"""

import asyncio
import logging
import sys

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from agent.config import Config
from agent.runtime import VoiceRuntime


def setup_logging(level: str):
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    """Main entry point."""
    # Load configuration
    config = Config()

    # Setup logging
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    # Print banner
    print("=" * 60)
    print("  🤖 AI Voice Agent — Local CLI")
    print("=" * 60)
    print(f"  STT Provider : {config.stt_provider}")
    print(f"  TTS Provider : {config.tts_provider}")
    print(f"  LLM (Primary): Groq / {config.llm_primary_model}")
    print(f"  LLM (Fallback): Groq / {config.llm_fallback_model}")
    print(f"  Audio        : {config.audio_sample_rate}Hz, {config.audio_channels}ch")
    print("=" * 60)

    # Validate configuration
    errors = config.validate()
    if errors:
        print("\n❌ Configuration errors:")
        for error in errors:
            print(f"   • {error}")
        print("\n   Please check your .env file. See .env.example for reference.")
        sys.exit(1)

    # Ensure data directories exist
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)

    # Create and start the runtime
    runtime = VoiceRuntime(config)

    try:
        asyncio.run(runtime.start())
    except KeyboardInterrupt:
        print("\n\nGoodbye! 👋")
    except Exception:
        logger.exception("Fatal error occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()
