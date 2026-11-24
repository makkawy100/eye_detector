#!/usr/bin/env python3
"""Driver drowsiness detection and emergency alert launcher."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from emergency_alerter.location_service import LocationService
from emergency_alerter.telegram_notifier import TelegramNotifier
from vision_engine.detector import DrowsinessDetector


def test_telegram_alert(config_path: str):
    """Send a Telegram test alert using credentials supplied in the environment."""
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    vehicle = config.get("vehicle", {})
    telegram = config.get("alerter", {}).get("telegram", {})
    token = os.getenv(telegram.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
    chat_id = os.getenv(telegram.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
    if not token or not chat_id:
        print("Set the Telegram bot token and chat ID in the configured environment variables first.")
        return

    location = LocationService(
        default_lat=vehicle.get("latitude", 0.0),
        default_lon=vehicle.get("longitude", 0.0),
        default_location_name=vehicle.get("location_name", ""),
        maps_url=vehicle.get("maps_url"),
        use_fixed_location=vehicle.get("use_fixed_location", True),
        gps_serial_port=vehicle.get("gps_serial_port"),
    )
    latitude, longitude, location_name, maps_url = location.refresh_location()
    notifier = TelegramNotifier(
        bot_token=token,
        chat_id=chat_id,
        car_number=vehicle.get("car_number", ""),
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        repeat_interval_seconds=0,
        send_native_map_pin=telegram.get("send_native_map_pin", True),
        include_url_in_message=telegram.get("include_url_in_message", False),
        show_location_name=vehicle.get("show_location_name", False),
    )
    notifier.send_emergency_alert(
        status_note="Location test: driver safe, system operational.",
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        maps_url=maps_url,
        force=True,
        wait=True,
    )


def main():
    parser = argparse.ArgumentParser(description="Driver Drowsiness Detection & Emergency Alert System")
    parser.add_argument("--config", default="config.json", help="Path to configuration file")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test Telegram alert and exit")
    parser.add_argument("--esp-cam", type=str, help="Override camera with ESP32-CAM stream URL")
    args = parser.parse_args()

    if args.test_telegram:
        test_telegram_alert(args.config)
        return

    detector = DrowsinessDetector(config_path=args.config)
    if args.esp_cam:
        detector.config.setdefault("camera", {})["source"] = "esp32_cam"
        detector.config["camera"]["esp32_cam_url"] = args.esp_cam
    detector.run()


if __name__ == "__main__":
    main()
