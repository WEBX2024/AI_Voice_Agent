"""
Real-time audio enhancement and noise detection.

Processes microphone audio chunks to:
1. Apply spectral noise suppression (via noisereduce).
2. Estimate audio metrics (VAD, SNR, speech quality).
"""

import math
import logging
import numpy as np
import noisereduce as nr

logger = logging.getLogger(__name__)


class AudioEnhancer:
    """
    Real-time audio processing pipeline.
    
    Operates on small PCM audio chunks (e.g., 100ms) to reduce background noise
    and extract metrics for the agent to use in decision making.
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        
        # Heuristics state
        self.speech_energy_threshold = 0.005
        self.noise_history = []
        self.speech_history = []
        
    def process_chunk(self, audio_bytes: bytes) -> tuple[bytes, dict]:
        """
        Process a chunk of raw 16-bit PCM audio.
        
        Returns:
            clean_bytes: The noise-suppressed audio chunk.
            metrics: A dictionary of audio metrics (speech_detected, snr, etc.)
        """
        if not audio_bytes:
            return audio_bytes, self._default_metrics()

        # Convert 16-bit PCM bytes to numpy float array [-1.0, 1.0]
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        if len(audio_array) == 0:
            return audio_bytes, self._default_metrics()

        # 1. Metric Extraction (RMS Energy)
        rms = float(np.sqrt(np.mean(audio_array**2)))
        
        # Simple VAD heuristic based on energy
        speech_detected = rms > self.speech_energy_threshold
        
        if speech_detected:
            self.speech_history.append(rms)
            if len(self.speech_history) > 50:
                self.speech_history.pop(0)
        else:
            self.noise_history.append(rms)
            if len(self.noise_history) > 50:
                self.noise_history.pop(0)
                
        # Estimate sustained levels
        noise_level = float(np.mean(self.noise_history)) if self.noise_history else 0.0001
        speech_level = float(np.mean(self.speech_history)) if self.speech_history else 0.0001
        
        # Prevent math domain error
        noise_level = max(noise_level, 1e-6)
        speech_level = max(speech_level, 1e-6)
            
        snr_estimate = 20 * math.log10(speech_level / noise_level)
        
        # Categorize intelligibility
        if snr_estimate > 15:
            intelligibility = "good"
        elif snr_estimate > 5:
            intelligibility = "fair"
        else:
            intelligibility = "poor"
            
        noise_present = noise_level > 0.002  # Threshold for noticeable noise
        
        metrics = {
            "speech_detected": bool(speech_detected),
            "speech_quality": float(min(1.0, max(0.0, snr_estimate / 30.0))), 
            "noise_present": bool(noise_present),
            "noise_level": float(noise_level),
            "snr_estimate": float(snr_estimate),
            "speech_intelligibility": intelligibility
        }
        
        # 2. Noise Suppression
        try:
            # For streaming, we use a small FFT size and stationary=True for speed
            # Note: noisereduce is primarily for offline, but works decently on chunks
            # with stationary=True and smaller n_fft.
            n_fft = min(512, len(audio_array))
            if n_fft >= 64:  # Minimum reasonable FFT size
                reduced_audio = nr.reduce_noise(
                    y=audio_array, 
                    sr=self.sample_rate, 
                    prop_decrease=0.7, 
                    stationary=True,
                    n_fft=n_fft
                )
            else:
                reduced_audio = audio_array
        except Exception as e:
            logger.debug("Noise reduction failed on chunk: %s", e)
            reduced_audio = audio_array
            
        # Convert back to 16-bit PCM bytes
        clean_bytes = (reduced_audio * 32768.0).clip(-32768, 32767).astype(np.int16).tobytes()
        
        return clean_bytes, metrics
        
    def _default_metrics(self) -> dict:
        return {
            "speech_detected": False,
            "speech_quality": 1.0,
            "noise_present": False,
            "noise_level": 0.0,
            "snr_estimate": 30.0,
            "speech_intelligibility": "good"
        }
