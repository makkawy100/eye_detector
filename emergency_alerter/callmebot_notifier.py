"""
CallMeBot WhatsApp Voice Call & Message Dispatcher
100% Free API service to trigger automated WhatsApp phone calls and alert messages.
"""

import threading
import time
import urllib.parse
import logging
import subprocess
import shutil
from typing import Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CallMeBotNotifier")


class CallMeBotNotifier:
    def __init__(
        self,
        phone_number: str,
        api_key: str,
        cooldown_seconds: int = 60,
        enable_voice_call: bool = True,
        enable_text_message: bool = True,
        spoken_message: Optional[str] = None,
        voice_lang: str = "en-US-Standard-C",
        repeat_count: int = 2,
        play_in_cabin_audio: bool = True,
    ):
        """
        :param phone_number: International phone number (+1234567890)
        :param api_key: CallMeBot API key
        :param cooldown_seconds: Minimum seconds between repeated emergency alerts
        :param enable_voice_call: Trigger automated voice call on WhatsApp
        :param enable_text_message: Send WhatsApp text message notification
        :param spoken_message: The text-to-speech voice message read aloud when call is answered
        :param voice_lang: CallMeBot TTS language/voice code (e.g. en-US-Standard-C, ar-XA-Standard-A)
        :param repeat_count: Number of times to repeat the spoken message in the call
        :param play_in_cabin_audio: Also speak the alert out loud through vehicle/PC speakers to wake driver
        """
        self.phone_number = phone_number.strip().replace(" ", "").replace("-", "")
        self.api_key = api_key.strip()
        self.cooldown_seconds = cooldown_seconds
        self.enable_voice_call = enable_voice_call
        self.enable_text_message = enable_text_message
        self.spoken_message = spoken_message or (
            "Warning! Emergency alert! The driver has fallen asleep at the wheel. "
            "Emergency braking has been activated and the vehicle is stopped in the right lane."
        )
        self.voice_lang = voice_lang
        self.repeat_count = max(1, repeat_count)
        self.play_in_cabin_audio = play_in_cabin_audio
        self.last_call_timestamp: float = 0.0
        self.last_in_cabin_play_time: float = 0.0
        self._lock = threading.Lock()
        self._speech_in_progress = False

    def is_configured(self) -> bool:
        """Returns True if user has configured valid phone number and API key."""
        return (
            bool(self.phone_number)
            and bool(self.api_key)
            and "YOUR_" not in self.api_key
            and "YOUR_" not in self.phone_number
        )

    def trigger_emergency(self, reason: str = "Driver is sleeping! Emergency stop and lane change initiated.", wait: bool = False):
        """
        Spawns a thread to initiate the emergency WhatsApp call and text.
        :param wait: If True, blocks until the dispatch finishes (useful for CLI test).
        """
        now = time.time()
        with self._lock:
            if now - self.last_call_timestamp < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - (now - self.last_call_timestamp))
                logger.info(f"Emergency alert suppressed due to cooldown ({remaining}s remaining).")
                return False
            self.last_call_timestamp = now

        # Run network dispatch in thread
        thread = threading.Thread(target=self._dispatch_calls, args=(reason,), daemon=not wait)
        thread.start()
        if wait:
            thread.join()
        return True

    def _dispatch_calls(self, reason: str):
        logger.warning(f"🚨 TRIGGERING EMERGENCY DISPATCH: {reason}")

        # Construct repeated voice script for the call
        voice_script = self.spoken_message
        if self.repeat_count > 1:
            voice_script = " . Attention: ".join([self.spoken_message] * self.repeat_count)

        # 1. Play in-cabin audio alert through speakers to wake up the driver immediately
        if self.play_in_cabin_audio:
            self._play_in_cabin_alert(self.spoken_message)

        # 2. Check if credentials are set
        if not self.is_configured():
            logger.warning(
                "[SIMULATION MODE] CallMeBot API credentials not yet set in config.json. "
                "Simulating automated emergency call to phone."
            )
            print("\a")  # Terminal bell
            print("\n" + "=" * 65)
            print(f"📞 [MOCK WHATSAPP VOICE CALL] Would call: {self.phone_number or '[UNCONFIGURED]'}")
            print(f"🔊 Spoken Voice Message Played In Call ({self.voice_lang}):")
            print(f"   \"{voice_script}\"")
            print(f"💬 WhatsApp Text Message:")
            print(f"   \"🚨 EMERGENCY: {reason}\"")
            print("=" * 65 + "\n")
            return

        # 3. Trigger WhatsApp Voice Call with the spoken voice message
        if self.enable_voice_call:
            self._make_voice_call(voice_script)

        # 4. Trigger WhatsApp Text Message
        if self.enable_text_message:
            self._send_whatsapp_message(f"🚨 EMERGENCY ALERT: {reason}")

    def play_in_cabin_alert(self, message: Optional[str] = None):
        """
        Plays repeating audio/TTS warning inside the cabin to wake the sleeping driver.
        Non-blocking and prevents overlapping audio streams.
        """
        if not self.play_in_cabin_audio:
            return

        now = time.time()
        with self._lock:
            # Enforce at least 3 seconds between speech attempts so audio does not overlap
            if now - self.last_in_cabin_play_time < 2.8 or self._speech_in_progress:
                return
            self.last_in_cabin_play_time = now
            self._speech_in_progress = True

        msg = message or "Warning! Wake up! Emergency brakes engaged!"

        def _speak():
            try:
                print("\a", end="", flush=True)  # System bell
                if shutil.which("spd-say"):
                    subprocess.run(["spd-say", "-r", "15", "-p", "30", msg], check=False)
                elif shutil.which("espeak"):
                    subprocess.run(["espeak", "-s", "160", msg], check=False)
                else:
                    logger.warning(f"🔊 [IN-CABIN VOICE ALARM]: {msg}")
            except Exception as e:
                logger.debug(f"In-cabin speech dispatch info: {e}")
            finally:
                with self._lock:
                    self._speech_in_progress = False

        threading.Thread(target=_speak, daemon=True).start()

    def _play_in_cabin_alert(self, message: str):
        self.play_in_cabin_alert(message)

    def _make_voice_call(self, voice_script: str):
        """Calls CallMeBot voice call endpoint: /call.php with voice message text & language."""
        try:
            encoded_text = urllib.parse.quote(voice_script)
            call_url = (
                f"https://api.callmebot.com/call.php?"
                f"phone={self.phone_number}&text={encoded_text}&apikey={self.api_key}&lang={self.voice_lang}"
            )
            logger.info(f"Placing free WhatsApp voice call to {self.phone_number} with voice message...")
            response = requests.get(call_url, timeout=12)
            if response.status_code == 200:
                logger.info("WhatsApp voice call initiated successfully! The voice message will play upon answering.")
            else:
                logger.error(f"Voice call failed (HTTP {response.status_code}): {response.text[:120]}")
        except Exception as e:
            logger.error(f"Error initiating WhatsApp voice call: {e}")

    def _send_whatsapp_message(self, message: str):
        """Sends WhatsApp text message: /whatsapp.php"""
        try:
            encoded_text = urllib.parse.quote(message)
            msg_url = (
                f"https://api.callmebot.com/whatsapp.php?"
                f"phone={self.phone_number}&text={encoded_text}&apikey={self.api_key}"
            )
            logger.info(f"Sending WhatsApp alert message to {self.phone_number}...")
            response = requests.get(msg_url, timeout=10)
            if response.status_code == 200:
                logger.info("WhatsApp text alert delivered successfully!")
            else:
                logger.error(f"WhatsApp message failed (HTTP {response.status_code}): {response.text[:120]}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
