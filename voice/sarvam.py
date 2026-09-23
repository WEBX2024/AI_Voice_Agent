"""
Sarvam AI STT and TTS provider.

Uses Sarvam's WebSocket streaming APIs for real-time speech-to-text
and text-to-speech. Falls back to REST API where streaming is not feasible.
"""

import asyncio
import base64
import json
import logging
import aiohttp

from agent.config import Config

logger = logging.getLogger(__name__)

# Sarvam WebSocket endpoints
SARVAM_STT_WS_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
SARVAM_TTS_WS_URL = "wss://api.sarvam.ai/text-to-speech/ws"

# Sarvam REST endpoints (fallback)
SARVAM_STT_REST_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_REST_URL = "https://api.sarvam.ai/text-to-speech"


class SarvamSTT:
    """
    Sarvam AI streaming speech-to-text using WebSocket.

    Sends audio chunks over WebSocket and receives interim/final transcripts.
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.sarvam_api_key
        self.model = config.sarvam_stt_model
        self.language_code = config.sarvam_language_code
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None

    async def connect(self):
        """Establish WebSocket connection to Sarvam STT."""
        headers = {"Api-Subscription-Key": self.api_key}
        self._session = aiohttp.ClientSession()

        try:
            # Sarvam configures the session via query parameters
            url = f"{SARVAM_STT_WS_URL}?language_code={self.language_code}&model={self.model}"
            self._ws = await self._session.ws_connect(
                url, headers=headers
            )
            logger.info("Connected to Sarvam STT WebSocket")

        except Exception as e:
            logger.error("Failed to connect to Sarvam STT: %s", e)
            raise

    async def send_audio(self, audio_chunk: bytes):
        """Send an audio chunk to the STT WebSocket."""
        if self._ws is None:
            raise RuntimeError("STT WebSocket not connected")

        # Sarvam expects base64-encoded audio in an audio_input event
        audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
        msg = {"event": "audio_input", "audio": audio_b64}
        await self._ws.send_json(msg)

    async def receive_transcript(self) -> dict | None:
        """
        Receive a transcript message from the WebSocket.

        Returns a dict with keys:
        - "transcript": the transcribed text
        - "is_final": whether this is a final (stable) transcript
        """
        if self._ws is None:
            return None

        try:
            msg = await asyncio.wait_for(self._ws.receive(), timeout=0.1)

            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                
                event = data.get("event")
                if event in ["transcript.partial", "transcript.final"]:
                    return {
                        "transcript": data.get("text", ""),
                        "is_final": event == "transcript.final",
                    }
                elif event == "error":
                    logger.error("STT event error: %s", data.get("message"))
                    return None
                    
                return None
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.warning("STT WebSocket closed/error: %s", msg.type)
                return None

        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error("STT receive error: %s", e)
            return None

    async def close(self):
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Sarvam STT connection closed")

    async def transcribe_audio(self, audio_data: bytes) -> str:
        """
        One-shot transcription via REST API (non-streaming fallback).

        Useful for short audio clips where streaming is not needed.
        """
        headers = {
            "Api-Subscription-Key": self.api_key,
        }

        form_data = aiohttp.FormData()
        form_data.add_field(
            "file", audio_data, filename="audio.wav", content_type="audio/wav"
        )
        form_data.add_field("model", self.model.replace("-realtime", ""))
        form_data.add_field("language_code", self.language_code)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                SARVAM_STT_REST_URL, headers=headers, data=form_data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("transcript", "")
                else:
                    error = await resp.text()
                    logger.error("Sarvam STT REST error %d: %s", resp.status, error)
                    return ""


class SarvamTTS:
    """
    Sarvam AI streaming text-to-speech using WebSocket.

    Sends text chunks and receives audio data in real-time.
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.sarvam_api_key
        self.model = config.sarvam_tts_model
        self.speaker = config.sarvam_tts_speaker
        self.language_code = config.sarvam_language_code

    async def synthesize(self, text: str) -> bytes:
        """
        One-shot TTS via REST API (non-streaming fallback).

        Returns raw audio bytes.
        """
        headers = {
            "Api-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "inputs": [text],
            "model": self.model,
            "speaker": self.speaker,
            "target_language_code": self.language_code,
            "speech_sample_rate": self.config.audio_sample_rate,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                SARVAM_TTS_REST_URL, headers=headers, json=payload
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    audios = result.get("audios", [])
                    if audios and len(audios) > 0:
                        audio_data = base64.b64decode(audios[0])
                        # If it's a WAV file, strip the 44-byte RIFF header so we get raw PCM
                        if audio_data.startswith(b"RIFF"):
                            audio_data = audio_data[44:]
                        return audio_data
                    return b""
                else:
                    error = await resp.text()
                    logger.error("Sarvam TTS REST error %d: %s", resp.status, error)
                    return b""

    async def close(self):
        """Close the TTS resources."""
        pass
