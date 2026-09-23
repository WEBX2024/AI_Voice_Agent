"""
Audio stream manager using sounddevice.

Handles local microphone capture and speaker playback.
Provides async-friendly interfaces via callbacks and queues.
"""

import logging
import queue
import threading

import numpy as np
import sounddevice as sd

from agent.config import Config

logger = logging.getLogger(__name__)

# Audio dtype for 16-bit PCM
DTYPE = "int16"
BYTES_PER_SAMPLE = 2


class AudioStream:
    """
    Manages local microphone input and speaker output via sounddevice.

    Audio is captured via a callback-based input stream and placed into
    a queue for async consumption. Playback is handled via an output queue.
    """

    def __init__(self, config: Config):
        self.config = config
        self.sample_rate = config.audio_sample_rate
        self.channels = config.audio_channels
        self.chunk_size = config.audio_chunk_size

        self._input_stream: sd.InputStream | None = None
        self._output_stream: sd.OutputStream | None = None

        # Queues for async communication
        self.input_queue: queue.Queue[bytes | None] = queue.Queue()
        self.output_queue: queue.Queue[bytes | None] = queue.Queue()

        # Control flags
        self._recording = False
        self._playing = False
        self._play_thread: threading.Thread | None = None

        # Interruption support
        self._interrupted = threading.Event()

    def _input_callback(self, indata, frames, time_info, status):
        """Callback for the input stream — called by sounddevice."""
        if status:
            logger.warning("Audio input status: %s", status)
        if self._recording:
            # Convert numpy array to raw bytes
            self.input_queue.put(bytes(indata))

    def start(self):
        """Initialize and open input/output streams."""
        logger.info(
            "Starting audio: %dHz, %dch, chunk=%d frames",
            self.sample_rate, self.channels, self.chunk_size,
        )

        try:
            # Open input stream (microphone) with callback
            self._input_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=DTYPE,
                blocksize=self.chunk_size,
                callback=self._input_callback,
            )
            logger.info("Microphone stream created")
        except Exception as e:
            logger.error("Failed to create microphone stream: %s", e)
            raise

        try:
            # Open output stream (speaker) — we write to it from the play loop
            self._output_stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=DTYPE,
                blocksize=self.chunk_size,
            )
            logger.info("Speaker stream created")
        except Exception as e:
            logger.error("Failed to create speaker stream: %s", e)
            raise

    def start_recording(self):
        """Start capturing microphone audio."""
        if self._recording:
            return
        self._recording = True
        if self._input_stream:
            self._input_stream.start()
        logger.info("Recording started")

    def stop_recording(self):
        """Stop the microphone capture."""
        self._recording = False
        if self._input_stream and self._input_stream.active:
            self._input_stream.stop()
        # Signal end of stream
        self.input_queue.put(None)
        logger.info("Recording stopped")

    def start_playback(self):
        """Start the speaker playback loop in a background thread."""
        if self._playing:
            return
        self._playing = True
        self._interrupted.clear()
        if self._output_stream:
            self._output_stream.start()
        self._play_thread = threading.Thread(
            target=self._play_loop, daemon=True, name="audio-play"
        )
        self._play_thread.start()
        logger.info("Playback started")

    def stop_playback(self):
        """Stop the speaker playback loop."""
        self._playing = False
        if self._play_thread:
            self._play_thread.join(timeout=2.0)
            self._play_thread = None
        if self._output_stream and self._output_stream.active:
            self._output_stream.stop()
        # Drain the output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Playback stopped")

    def interrupt_playback(self):
        """Signal that playback should be interrupted (user started speaking)."""
        self._interrupted.set()
        # Drain remaining audio
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Playback interrupted")

    def play_audio(self, audio_data: bytes):
        """Queue audio data for playback."""
        self.output_queue.put(audio_data)

    def read_chunk(self, timeout: float = 1.0) -> bytes | None:
        """Read a chunk of audio from the microphone queue."""
        try:
            return self.input_queue.get(timeout=timeout)
        except queue.Empty:
            return b""

    def _play_loop(self):
        """Background loop: dequeue audio chunks and write to speaker."""
        while self._playing:
            if self._interrupted.is_set():
                self._interrupted.clear()
                continue

            try:
                data = self.output_queue.get(timeout=0.1)
                if data is None:
                    break

                # Convert bytes to numpy array for sounddevice
                audio_array = np.frombuffer(data, dtype=DTYPE)
                # Reshape to (samples, channels)
                if self.channels == 1:
                    audio_array = audio_array.reshape(-1, 1)
                else:
                    audio_array = audio_array.reshape(-1, self.channels)

                self._output_stream.write(audio_array)

            except queue.Empty:
                continue
            except Exception as e:  # noqa: BLE001
                if self._playing:
                    logger.error("Playback error: %s", e)
                break

    def stop(self):
        """Shut down all audio resources."""
        self.stop_recording()
        self.stop_playback()

        if self._input_stream:
            self._input_stream.close()
            self._input_stream = None

        if self._output_stream:
            self._output_stream.close()
            self._output_stream = None

        logger.info("Audio streams closed")
