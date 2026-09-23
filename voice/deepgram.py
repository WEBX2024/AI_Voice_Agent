"""
Deepgram STT and TTS provider (fallback).

Uses Deepgram's WebSocket API directly via aiohttp for streaming STT,
and the REST API for TTS. This avoids tight coupling to SDK version changes.
"""

import asyncio
import json
import logging

import aiohttp

from agent.config import Config

logger = logging.getLogger(__name__)

# Deepgram endpoints
DEEPGRAM_STT_WS_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_TTS_REST_URL = "https://api.deepgram.com/v1/speak"
DEEPGRAM_TTS_WS_URL = "wss://api.deepgram.com/v1/speak"


class DeepgramSTT:
    """
    Deepgram streaming speech-to-text via raw WebSocket.

    Connects to Deepgram's live transcription WebSocket and sends
    raw PCM audio. Receives interim and final transcripts.
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.deepgram_api_key
        self.model = config.deepgram_stt_model
        self.language = config.deepgram_language

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None

    async def connect(self):
        """Establish WebSocket connection to Deepgram STT."""
        params = (
            f"?model={self.model}"
            f"&language={self.language}"
            f"&punctuate=true"
            f"&interim_results=true"
            f"&encoding=linear16"
            f"&sample_rate={self.config.audio_sample_rate}"
            f"&channels={self.config.audio_channels}"
        )

        headers = {"Authorization": f"Token {self.api_key}"}
        self._session = aiohttp.ClientSession()

        try:
            self._ws = await self._session.ws_connect(
                DEEPGRAM_STT_WS_URL + params, headers=headers
            )
            logger.info("Connected to Deepgram STT WebSocket")
        except Exception as e:
            logger.error("Failed to connect to Deepgram STT: %s", e)
            raise

    async def send_audio(self, audio_chunk: bytes):
        """Send raw PCM audio bytes to the Deepgram WebSocket."""
        if self._ws is None:
            raise RuntimeError("Deepgram STT not connected")
        await self._ws.send_bytes(audio_chunk)

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
            msg = await asyncio.wait_for(self._ws.receive(), timeout=5.0)

            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)

                # Deepgram returns channel.alternatives[0].transcript
                channel = data.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")
                    is_final = data.get("is_final", False)
                    if transcript:
                        return {"transcript": transcript, "is_final": is_final}

                return None

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.warning("Deepgram STT WebSocket closed/error: %s", msg.type)
                return None

        except asyncio.TimeoutError:
            return None
        except Exception as e:  # noqa: BLE001
            logger.error("Deepgram STT receive error: %s", e)
            return None

    async def close(self):
        """Close the WebSocket connection."""
        if self._ws:
            # Send close message
            try:
                await self._ws.send_json({"type": "CloseStream"})
            except Exception:  # noqa: BLE001, S110
                pass
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Deepgram STT connection closed")


class DeepgramTTS:
    """
    Deepgram text-to-speech via REST API.

    Sends text and receives audio data. Uses the REST API for simplicity
    and reliability.
    """

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.deepgram_api_key
        self.model = config.deepgram_tts_model

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to audio using Deepgram's REST TTS API.

        Returns raw audio bytes (linear16 PCM).
        """
        url = (
            f"{DEEPGRAM_TTS_REST_URL}"
            f"?model={self.model}"
            f"&encoding=linear16"
            f"&sample_rate={self.config.audio_sample_rate}"
        )

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"text": text}

        try:
            async with aiohttp.ClientSession() as session, session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        logger.debug("Deepgram TTS: synthesized %d bytes", len(audio_data))
                        return audio_data
                    else:
                        error = await resp.text()
                        logger.error("Deepgram TTS error %d: %s", resp.status, error)
                        return b""
        except Exception as e:  # noqa: BLE001
            logger.error("Deepgram TTS request failed: %s", e)
            return b""

    async def synthesize_streaming(self, text: str):
        """
        Streaming TTS via WebSocket. Yields audio chunks.
        """
        url = (
            f"{DEEPGRAM_TTS_WS_URL}"
            f"?model={self.model}"
            f"&encoding=linear16"
            f"&sample_rate={self.config.audio_sample_rate}"
        )

        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            async with aiohttp.ClientSession() as session, session.ws_connect(url, headers=headers) as ws:
                    await ws.send_json({"type": "Speak", "text": text})
                    await ws.send_json({"type": "Flush"})

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            yield msg.data
                        elif msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data.get("type") == "Flushed":
                                break
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
        except Exception as e:  # noqa: BLE001
            logger.error("Deepgram TTS streaming error: %s", e)

    async def close(self):
        """No persistent connection to close for REST-based TTS."""
