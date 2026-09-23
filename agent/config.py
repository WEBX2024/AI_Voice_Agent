"""
Configuration loader.

Reads environment variables from .env and exposes typed configuration
for all components (API keys, provider selection, audio settings).
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
    logger.info("Loaded environment from %s", _ENV_PATH)
else:
    logger.warning("No .env file found at %s — using system environment", _ENV_PATH)


class Config:
    """Central configuration loaded from environment variables."""

    def __init__(self):
        # --- API Keys ---
        self.sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")
        self.deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")

        # --- Provider Selection ---
        self.stt_provider: str = os.getenv("STT_PROVIDER", "sarvam").lower()
        self.tts_provider: str = os.getenv("TTS_PROVIDER", "sarvam").lower()

        self.llm_primary_model: str = os.getenv("LLM_PRIMARY_MODEL", "openai/gpt-oss-120b")
        self.llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "qwen/qwen3.6-27b")

        # --- Sarvam ---
        self.sarvam_stt_model: str = os.getenv("SARVAM_STT_MODEL", "saaras:v4-realtime")
        self.sarvam_tts_model: str = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
        self.sarvam_tts_speaker: str = os.getenv("SARVAM_TTS_SPEAKER", "priya")
        self.sarvam_language_code: str = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN")

        # --- Deepgram ---
        self.deepgram_stt_model: str = os.getenv("DEEPGRAM_STT_MODEL", "nova-3")
        self.deepgram_tts_model: str = os.getenv("DEEPGRAM_TTS_MODEL", "aura-asteria-en")
        self.deepgram_language: str = os.getenv("DEEPGRAM_LANGUAGE", "en-US")

        # --- Audio ---
        self.audio_sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
        self.audio_channels: int = int(os.getenv("AUDIO_CHANNELS", "1"))
        self.audio_chunk_ms: int = int(os.getenv("AUDIO_CHUNK_MS", "100"))

        # --- Paths ---
        self.project_root: Path = _PROJECT_ROOT
        self.prompts_dir: Path = _PROJECT_ROOT / "prompts"
        self.data_dir: Path = _PROJECT_ROOT / "data"
        self.logs_dir: Path = _PROJECT_ROOT / "logs"

        # --- Logging ---
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def audio_chunk_size(self) -> int:
        """Number of audio frames per chunk based on sample rate and chunk duration."""
        return int(self.audio_sample_rate * self.audio_chunk_ms / 1000)

    def validate(self) -> list[str]:
        """Check that required configuration is present. Returns list of errors."""
        errors = []

        if not self.groq_api_key:
            errors.append("GROQ_API_KEY is not set")

        if self.stt_provider == "sarvam" and not self.sarvam_api_key:
            errors.append("STT_PROVIDER is 'sarvam' but SARVAM_API_KEY is not set")
        elif self.stt_provider == "deepgram" and not self.deepgram_api_key:
            errors.append("STT_PROVIDER is 'deepgram' but DEEPGRAM_API_KEY is not set")

        if self.tts_provider == "sarvam" and not self.sarvam_api_key:
            errors.append("TTS_PROVIDER is 'sarvam' but SARVAM_API_KEY is not set")
        elif self.tts_provider == "deepgram" and not self.deepgram_api_key:
            errors.append("TTS_PROVIDER is 'deepgram' but DEEPGRAM_API_KEY is not set")

        if self.stt_provider not in ("sarvam", "deepgram"):
            errors.append(f"Unknown STT_PROVIDER: {self.stt_provider}")
        if self.tts_provider not in ("sarvam", "deepgram"):
            errors.append(f"Unknown TTS_PROVIDER: {self.tts_provider}")

        return errors

    def __repr__(self) -> str:
        return (
            f"Config(stt={self.stt_provider}, tts={self.tts_provider}, "
            f"llm=groq/{self.llm_primary_model}, "
            f"audio={self.audio_sample_rate}Hz/{self.audio_channels}ch/{self.audio_chunk_ms}ms)"
        )
