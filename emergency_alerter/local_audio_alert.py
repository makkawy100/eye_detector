"""Local-only audible alarm. Generates a pulsing two-tone warning, not speech."""

import logging
import math
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger("LocalAudioAlert")


class LocalAudioAlert:
    def __init__(self, minimum_interval_seconds: float = 2.8):
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_play_time = 0.0
        self._playing = False
        self._lock = threading.Lock()

    @staticmethod
    def _make_alarm(path: Path, duration_seconds: float = 1.2, sample_rate: int = 22050):
        """Write a short alternating two-tone alarm WAV using only the standard library."""
        frames = bytearray()
        total = int(duration_seconds * sample_rate)
        for index in range(total):
            t = index / sample_rate
            # Alternate 880 Hz and 660 Hz in 150 ms pulses, with short edge fades.
            segment = int(t / 0.15)
            frequency = 880.0 if segment % 2 == 0 else 660.0
            local_t = t % 0.15
            edge = min(1.0, local_t / 0.012, (0.15 - local_t) / 0.012)
            envelope = max(0.0, edge)
            sample = int(12000 * envelope * math.sin(2.0 * math.pi * frequency * t))
            frames.extend(struct.pack("<h", sample))
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(frames)

    def play_alert(self, _message: str = ""):
        """Play a short local alarm sound without speech or network requests."""
        now = time.time()
        with self._lock:
            if now - self._last_play_time < self.minimum_interval_seconds or self._playing:
                return False
            self._last_play_time = now
            self._playing = True

        def play():
            try:
                player = shutil.which("paplay") or shutil.which("aplay")
                if player:
                    with tempfile.TemporaryDirectory(prefix="eye-detector-alarm-") as temp_dir:
                        alarm = Path(temp_dir) / "warning.wav"
                        self._make_alarm(alarm)
                        subprocess.run([player, str(alarm)], check=False, timeout=4)
                else:
                    # Terminal bell is a non-verbal fallback when no audio player exists.
                    print("\a", end="", flush=True)
            except Exception as exc:
                logger.debug("Local alarm playback failed: %s", exc)
                print("\a", end="", flush=True)
            finally:
                with self._lock:
                    self._playing = False

        threading.Thread(target=play, daemon=True).start()
        return True
