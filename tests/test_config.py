from agent.config import Config


def test_default_audio_settings():
    config = Config()

    assert config.audio_sample_rate == 16000
    assert config.audio_channels == 1
    assert config.audio_chunk_ms == 100


def test_audio_chunk_size():
    config = Config()

    assert config.audio_chunk_size == 1600

def test_validate_reports_missing_groq_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    config = Config()

    errors = config.validate()

    assert "GROQ_API_KEY is not set" in errors


def test_validate_rejects_unknown_stt_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("STT_PROVIDER", "unknown")

    config = Config()

    errors = config.validate()

    assert "Unknown STT_PROVIDER: unknown" in errors