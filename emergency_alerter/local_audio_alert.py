"""Local-only audible alert. Speaks a clear "Wake up!" voice prompt, fully offline.

The voice prompt is a small WAV file bundled with the project
(``sounds/wake_up.wav``), so no speech engine, network service, or extra
package is needed at runtime. If the file is ever missing, a synthesized
two-tone alarm is used instead so the driver still gets a loud warning.
"""

import logging
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger("LocalAudioAlert")

# Bundled spoken prompt, played as-is. Natural voice, generated offline.
_VOICE_WAV = Path(__file__).resolve().parent / "sounds" / "wake_up.wav"


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

    @staticmethod
    def _play_wav(wav_path: Path) -> bool:
        """Play a WAV file locally with whatever the OS already has. True if started."""
        if sys.platform.startswith("win"):
            import winsound

            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
            return True
        if sys.platform == "darwin":
            player = shutil.which("afplay")
            if player:
                subprocess.run([player, str(wav_path)], check=False, timeout=10)
                return True
            return False
        player = shutil.which("paplay") or shutil.which("aplay")
        if player:
            subprocess.run([player, str(wav_path)], check=False, timeout=10)
            return True
        return False

    def play_alert(self, _message: str = ""):
        """Play the spoken "Wake up!" prompt locally; no network or cloud services."""
        now = time.time()
        with self._lock:
            if now - self._last_play_time < self.minimum_interval_seconds or self._playing:
                return False
            self._last_play_time = now
            self._playing = True

        def play():
            try:
                played = False
                if _VOICE_WAV.is_file():
                    played = self._play_wav(_VOICE_WAV)
                if not played:
                    # Voice file missing or no player found: fall back to the
                    # synthesized alarm so the warning is still audible.
                    player = shutil.which("paplay") or shutil.which("aplay")
                    if player and not sys.platform.startswith("win"):
                        with tempfile.TemporaryDirectory(prefix="eye-detector-alarm-") as temp_dir:
                            alarm = Path(temp_dir) / "warning.wav"
                            self._make_alarm(alarm)
                            subprocess.run([player, str(alarm)], check=False, timeout=4)
                    else:
                        print("\a", end="", flush=True)
            except Exception as exc:
                logger.debug("Local audio alert playback failed: %s", exc)
                print("\a", end="", flush=True)
            finally:
                with self._lock:
                    self._playing = False

        threading.Thread(target=play, daemon=True).start()
        return True
