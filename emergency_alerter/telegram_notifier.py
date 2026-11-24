"""
Telegram Emergency Alert Notifier
Dispatches instant emergency text alerts and native GPS map pins via Telegram Bot API.
Message-only mode (No photo). Supports continuous periodic alerts while emergency is active.
"""

import threading
import time
import logging
from typing import Optional
import requests

logger = logging.getLogger("TelegramNotifier")


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        car_number: str = "EGY-7894",
        latitude: float = 30.0444,
        longitude: float = 31.2357,
        location_name: str = "Right Shoulder - Highway (KM 42)",
        repeat_interval_seconds: int = 25,
        send_native_map_pin: bool = True,
        include_url_in_message: bool = False,
        show_location_name: bool = False,
    ):
        """
        :param bot_token: Telegram bot token from environment
        :param chat_id: Telegram chat identifier from environment
        :param car_number: License plate / vehicle identifier
        :param latitude: GPS latitude
        :param longitude: GPS longitude
        :param location_name: Textual description of location
        :param repeat_interval_seconds: How often to re-send emergency message while driver is asleep
        :param send_native_map_pin: Send Telegram native location pin
        :param include_url_in_message: If True, appends URL link in text; if False, omits URL (clean text)
        :param show_location_name: If True, displays location place name; if False, disables location name
        """
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self.car_number = car_number
        self.latitude = latitude
        self.longitude = longitude
        self.location_name = location_name
        self.repeat_interval_seconds = repeat_interval_seconds
        self.send_native_map_pin = send_native_map_pin
        self.include_url_in_message = include_url_in_message
        self.show_location_name = show_location_name
        self.last_sent_timestamp: float = 0.0
        self.alert_count: int = 0
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        """Returns True if bot token and chat id are set."""
        return (
            bool(self.bot_token)
            and bool(self.chat_id)
            and "YOUR_" not in self.bot_token
            and "YOUR_" not in self.chat_id
        )

    def reset_cooldown(self):
        """Resets timestamp so the next alert fires immediately upon sleep detection."""
        with self._lock:
            self.last_sent_timestamp = 0.0
            self.alert_count = 0

    def send_emergency_alert(
        self,
        status_note: str = "Driver sleeping! Pulled to right lane & stopped.",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        location_name: Optional[str] = None,
        maps_url: Optional[str] = None,
        force: bool = False,
        wait: bool = False,
    ) -> bool:
        """
        Sends formatted emergency text message with Car Number & Real Location.
        Repeats every repeat_interval_seconds as long as emergency continues.
        """
        if not self.is_configured():
            logger.warning("[Telegram] Bot credentials are not configured in the environment.")
            return False

        now = time.time()
        with self._lock:
            if not force and (now - self.last_sent_timestamp < self.repeat_interval_seconds):
                # Suppressed because repeat interval has not elapsed yet
                return False
            self.last_sent_timestamp = now
            self.alert_count += 1
            current_count = self.alert_count

        lat = latitude if latitude is not None else self.latitude
        lon = longitude if longitude is not None else self.longitude
        loc_name = location_name if location_name is not None else self.location_name
        url = maps_url or f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"

        thread = threading.Thread(
            target=self._dispatch_emergency_message,
            args=(status_note, current_count, lat, lon, loc_name, url),
            daemon=not wait,
        )
        thread.start()
        if wait:
            thread.join()
        return True

    def _dispatch_emergency_message(
        self, status_note: str, alert_number: int, lat: float, lon: float, loc_name: str, maps_url: str
    ):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "🚨 <b>EMERGENCY ALERT: DRIVER SLEEPING!</b>\n",
            f"🚗 <b>Car Number:</b> <code>{self.car_number}</code>",
            f"⚠️ <b>Status:</b> {status_note}",
            f"🕒 <b>Time:</b> {timestamp}",
        ]
        if self.show_location_name and loc_name:
            lines.append(f"📍 <b>Location:</b> {loc_name}")
        lines.append(f"📌 <b>Coordinates:</b> <code>{lat:.6f}, {lon:.6f}</code>\n")
        lines.append(f"🔔 <i>Alert #{alert_number} - Vehicle safely stopped with hazard flashers ON.</i>")

        if self.include_url_in_message:
            lines.append(f"\n🗺 <b>Map Link:</b> {maps_url}")

        message = "\n".join(lines)

        try:
            logger.info(f"📤 Sending Telegram alert #{alert_number} to chat {self.chat_id} (Car: {self.car_number}, Location: {loc_name})...")
            # 1. Send Text Message (No web preview, clean text)
            msg_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            resp = requests.post(msg_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"✅ Telegram text alert #{alert_number} delivered successfully!")
            else:
                self._handle_api_error(resp)

            # 2. Send Native Location Pin (only on first alert to avoid cluttering chat)
            if self.send_native_map_pin and alert_number == 1:
                loc_url = f"https://api.telegram.org/bot{self.bot_token}/sendLocation"
                loc_payload = {
                    "chat_id": self.chat_id,
                    "latitude": lat,
                    "longitude": lon,
                }
                requests.post(loc_url, json=loc_payload, timeout=10)

        except Exception as e:
            logger.error(f"Failed to deliver Telegram notification: {e}")

    def _handle_api_error(self, response: requests.Response):
        err = response.json() if response.headers.get("content-type") == "application/json" else response.text
        logger.error(f"❌ Telegram API Error (HTTP {response.status_code}): {err}")
