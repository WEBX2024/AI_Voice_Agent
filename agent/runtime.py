"""
Runtime orchestrator.

The main async event loop that ties together:
  Microphone → STT → LLM Agent → TTS → Speaker

Handles the streaming pipeline, turn management, and interruption detection.
"""

import asyncio
import logging
import json
import time
from pathlib import Path

from agent.config import Config
from agent.agent import VoiceAgent
from voice.stream import AudioStream
from voice.sarvam import SarvamSTT, SarvamTTS
from voice.deepgram import DeepgramSTT, DeepgramTTS
from voice.enhancement import AudioEnhancer

logger = logging.getLogger(__name__)

# Silence threshold (seconds) — how long silence = user done speaking
SILENCE_THRESHOLD = 0.7
# Maximum seconds to wait for speech before prompting
MAX_SILENCE = 15.0


class VoiceRuntime:
    """
    Async orchestrator for the voice agent pipeline.

    Flow:
    1. Capture audio from microphone (AudioStream)
    2. Stream audio to STT provider (Sarvam or Deepgram)
    3. Accumulate transcript until user finishes speaking
    4. Send transcript to VoiceAgent (Groq LLM)
    5. Stream LLM response to TTS provider
    6. Play synthesized audio through speaker
    """

    def __init__(self, config: Config):
        self.config = config
        self.agent = VoiceAgent(config)
        self.audio = AudioStream(config)
        self.enhancer = AudioEnhancer(config.audio_sample_rate)

        # Initialize STT provider
        if config.stt_provider == "sarvam":
            self.stt = SarvamSTT(config)
        else:
            self.stt = DeepgramSTT(config)

        # Initialize TTS provider
        if config.tts_provider == "sarvam":
            self.tts = SarvamTTS(config)
        else:
            self.tts = DeepgramTTS(config)

        self._running = False
        self._is_speaking = False  # True when agent TTS is playing

    async def start(self):
        """Initialize all components and start the voice loop."""
        logger.info("Starting voice runtime: %s", self.config)

        # Start audio streams
        self.audio.start()
        self.audio.start_recording()
        self.audio.start_playback()

        # Connect to STT/TTS providers
        await self.stt.connect()
        logger.info("STT provider connected (%s)", self.config.stt_provider)

        # TTS WebSocket connection (if using streaming)
        if hasattr(self.tts, 'connect'):
            try:
                await self.tts.connect()
                logger.info("TTS provider connected (%s)", self.config.tts_provider)
            except Exception as e:
                logger.warning("TTS streaming connect failed, will use REST fallback: %s", e)

        self._running = True
        print("\n🎙️  Voice Agent is ready!\n")
        print("   Press Ctrl+C to end the conversation.\n")

        # Speak an opening greeting so the user knows the agent is live
        await self._greet()

        try:
            await self._main_loop()
        except KeyboardInterrupt:
            print("\n\n📞 Ending conversation...")
        finally:
            await self.stop()

    async def _greet(self):
        """Speak an opening greeting so the user knows the agent is live."""
        greeting = "Hello! I'm your voice assistant. How can I help you today?"
        print(f"🤖 Agent: {greeting}")
        try:
            await self._speak(greeting)
        except Exception as e:
            logger.error("Failed to speak greeting: %s", e)

    async def _main_loop(self):
        """Main conversation loop."""
        import re
        
        while self._running:
            try:
                # Step 1: Listen and transcribe
                listen_start = time.time()
                user_text, audio_metrics = await self._listen()
                listen_elapsed = time.time() - listen_start

                if not user_text:
                    continue

                print(f"\n🗣️  You: {user_text}")
                print(f"   ⏱️  Listen: {listen_elapsed:.2f}s")
                
                # Check for fast-path goodbye keywords
                fast_exit = re.search(r'\b(bye|goodbye|end the call|hang up|talk to you later)\b', user_text.lower())

                # Step 2 & 3: Streaming LLM + Pipelined TTS
                state = await self._think_and_speak(user_text, audio_metrics)
                
                if fast_exit or state in ["ended", "closing"]:
                    print("\n📞 Call ended by agent logic.")
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Main loop error: %s", e)
                await asyncio.sleep(0.5)

    async def _listen(self) -> tuple[str, dict]:
        """
        Listen to the user via microphone + STT.

        Runs audio capture/sending and transcript receiving as concurrent
        tasks so that audio keeps flowing to the STT while we wait for
        transcripts. Accumulates transcript until the user stops speaking.
        """
        accumulated_text = ""
        partial_text = ""  # Latest partial (interim) transcript
        last_speech_time = time.time()
        got_speech = False
        latest_metrics = {}

        async def _send_audio_loop():
            """Continuously capture and send audio to STT."""
            nonlocal latest_metrics
            while self._running:
                try:
                    audio_chunk = await asyncio.get_event_loop().run_in_executor(
                        None, self.audio.read_chunk, 0.1
                    )
                    if audio_chunk and len(audio_chunk) > 0:
                        clean_chunk, latest_metrics = self.enhancer.process_chunk(audio_chunk)
                        await self.stt.send_audio(clean_chunk)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("STT send error: %s", e)
                await asyncio.sleep(0.01)

        async def _receive_transcript_loop():
            """Continuously receive and accumulate transcripts from STT."""
            nonlocal accumulated_text, partial_text, last_speech_time, got_speech
            while self._running:
                try:
                    transcript_data = await self.stt.receive_transcript()
                    if transcript_data and transcript_data.get("transcript"):
                        text = transcript_data["transcript"]
                        is_final = transcript_data.get("is_final", False)

                        if is_final:
                            accumulated_text += " " + text
                            accumulated_text = accumulated_text.strip()
                            partial_text = ""  # Clear partial after final
                            last_speech_time = time.time()
                            got_speech = True
                            logger.debug("Final transcript: %s", text)
                        else:
                            partial_text = text  # Keep latest partial
                            last_speech_time = time.time()
                            got_speech = True
                            logger.debug("Interim: %s", text)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("STT receive error: %s", e)
                    await asyncio.sleep(0.1)

        # Start both loops concurrently
        send_task = asyncio.create_task(_send_audio_loop())
        recv_task = asyncio.create_task(_receive_transcript_loop())

        try:
            # Monitor silence to decide when the user is done
            while self._running:
                silence_duration = time.time() - last_speech_time

                if got_speech and silence_duration > SILENCE_THRESHOLD:
                    logger.info("User finished speaking (%.1fs silence)", silence_duration)
                    break

                if not got_speech and silence_duration > MAX_SILENCE:
                    logger.debug("No speech detected for %.1fs", silence_duration)
                    break

                await asyncio.sleep(0.1)
        finally:
            send_task.cancel()
            recv_task.cancel()
            await asyncio.gather(send_task, recv_task, return_exceptions=True)

        # Use accumulated final text, or fall back to latest partial
        result = accumulated_text.strip()
        if not result and partial_text:
            logger.debug("Using partial transcript as fallback: %s", partial_text)
            result = partial_text.strip()

        return result, latest_metrics

    async def _think_and_speak(self, user_text: str, audio_metrics: dict = None) -> str:
        """
        Stream the LLM response, chunk it into sentences, and speak them sequentially.
        Returns the final conversation state.
        """
        import re
        think_start = time.time()
        first_token_time = None
        
        current_sentence = ""
        spoken_sentences = 0
        state = "active"
        full_response = ""

        # Run generator in an async wrapper since the underlying client is sync
        def _get_stream():
            return self.agent.process_turn_streaming(user_text, audio_metrics)

        stream = await asyncio.get_event_loop().run_in_executor(None, _get_stream)

        print(f"🤖 Agent: ", end="", flush=True)

        # Iterate over the sync generator without blocking the async event loop
        while True:
            try:
                item_type, content = await asyncio.get_event_loop().run_in_executor(None, next, stream)
            except StopIteration:
                break

            if item_type == "text":
                if not first_token_time:
                    first_token_time = time.time() - think_start
                    print(f"\n   ⏱️  First token: {first_token_time:.2f}s")
                
                print(content, end="", flush=True)
                current_sentence += content
                full_response += content

                # Split on sentence boundaries (., !, ?)
                # Also split if it gets too long without punctuation
                if re.search(r'[.!?]\s', current_sentence) or len(current_sentence) > 100:
                    sentence_to_speak = current_sentence.strip()
                    if sentence_to_speak:
                        # For first sentence, don't wait. For subsequent ones, we await speak
                        # (A full queueing system is better, but awaiting sequential sentences is a safe v1 pipeline)
                        await self._speak(sentence_to_speak)
                        spoken_sentences += 1
                    current_sentence = ""
                    
            elif item_type == "done":
                # Flush remaining text
                if current_sentence.strip():
                    await self._speak(current_sentence.strip())
                    
                if isinstance(content, dict):
                    state = content.get("conversation_state", "active")
                    
        print() # Newline after full agent response
        return state

    async def _speak(self, text: str):
        """
        Synthesize text to speech and play through the speaker.

        Uses REST TTS for v1 reliability. Can be upgraded to streaming
        TTS for lower time-to-first-byte latency.
        """
        self._is_speaking = True

        try:
            audio_data = await self.tts.synthesize(text)

            if audio_data:
                self.audio.play_audio(audio_data)
                # Wait for playback to roughly complete
                # Estimate duration from audio data size
                duration = len(audio_data) / (
                    self.config.audio_sample_rate * 2  # 16-bit = 2 bytes per sample
                )
                await asyncio.sleep(duration)
            else:
                logger.warning("TTS returned empty audio")

        except Exception as e:
            logger.error("TTS/playback error: %s", e)
        finally:
            self._is_speaking = False

    async def stop(self):
        """Shut down all components and generate call summary."""
        self._running = False

        # Generate call summary
        print("\n📋 Generating call summary...")
        summary = self.agent.generate_call_summary()

        if summary:
            # Save summary to file
            summary_dir = self.config.data_dir / "calls"
            summary_dir.mkdir(parents=True, exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            summary_file = summary_dir / f"call_{timestamp}.json"

            try:
                with open(summary_file, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2, ensure_ascii=False)
                print(f"   Summary saved to: {summary_file}")
            except Exception as e:
                logger.error("Failed to save summary: %s", e)

            # Print summary
            if isinstance(summary, dict) and "call_summary" in summary:
                cs = summary["call_summary"]
                print(f"\n   📝 {cs.get('summary', 'N/A')}")
                if cs.get("action_items"):
                    print("   📌 Action items:")
                    for item in cs["action_items"]:
                        print(f"      - {item.get('description', 'N/A')}")

        # Close connections
        await self.stt.close()
        if hasattr(self.tts, 'close'):
            await self.tts.close()
        self.audio.stop()

        print("\n✅ Voice agent stopped.\n")
