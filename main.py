#!/usr/bin/env python3
"""
Main launcher for Driver Drowsiness Emergency Brake System.
Phase 1: Eye Detection (MediaPipe Face Mesh + EAR) & Free WhatsApp Voice Call Alerter.
"""

import argparse
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vision_engine.detector import DrowsinessDetector
from emergency_alerter.callmebot_notifier import CallMeBotNotifier
from emergency_alerter.telegram_notifier import TelegramNotifier
from emergency_alerter.location_service import LocationService
import json


def test_whatsapp_call(config_path: str):
    """Utility to test the WhatsApp voice call endpoint without starting camera."""
    print("Testing WhatsApp Voice Call / Message...")
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, "r") as f:
        cfg = json.load(f)

    bot_cfg = cfg.get("alerter", {}).get("callmebot", {})
    notifier = CallMeBotNotifier(
        phone_number=bot_cfg.get("phone_number", ""),
        api_key=bot_cfg.get("api_key", ""),
        cooldown_seconds=0,
        enable_voice_call=bot_cfg.get("enable_voice_call", True),
        enable_text_message=bot_cfg.get("enable_whatsapp_text", True),
        spoken_message=bot_cfg.get("spoken_message"),
        voice_lang=bot_cfg.get("voice_language", "en-US-Standard-C"),
        repeat_count=bot_cfg.get("repeat_count", 2),
        play_in_cabin_audio=bot_cfg.get("play_in_cabin_audio", True),
    )

    if not notifier.is_configured():
        print("\n" + "=" * 65)
        print("NOTE: CallMeBot credentials are not yet configured in config.json.")
        print("To receive real WhatsApp voice calls & messages:")
        print("  1. Save bot phone number to your contacts on WhatsApp.")
        print("  2. Send WhatsApp message: 'I allow callmebot to send me messages'")
        print("  3. CallMeBot will reply with your personal API Key.")
        print("  4. Put your phone number and API key in config.json.")
        print("=" * 65 + "\n")

    notifier.trigger_emergency("Test emergency alert from Driver Drowsiness System.", wait=True)
    print("Test trigger completed successfully.")


def test_telegram_alert(config_path: str):
    """Utility to test Telegram notification with real location."""
    print("Testing Telegram Alert Dispatcher with Real Location...")
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, "r") as f:
        cfg = json.load(f)

    veh_cfg = cfg.get("vehicle", {})
    tg_cfg = cfg.get("alerter", {}).get("telegram", {})

    loc_service = LocationService(
        default_lat=veh_cfg.get("latitude", 31.209093),
        default_lon=veh_cfg.get("longitude", 29.923094),
        default_location_name=veh_cfg.get("location_name", "Specialized Scientific Programs, Faculty of Engineering"),
        maps_url=veh_cfg.get("maps_url", "https://maps.app.goo.gl/BcYvS5KqdEdAYyi4A"),
        use_fixed_location=veh_cfg.get("use_fixed_location", True),
        gps_serial_port=veh_cfg.get("gps_serial_port"),
    )

    real_lat, real_lon, real_loc_name, maps_url = loc_service.refresh_location()
    print(f"📍 Location Configured: {real_loc_name} ({real_lat:.6f}, {real_lon:.6f})")
    print(f"🗺 Google Maps Link: {maps_url}")

    notifier = TelegramNotifier(
        bot_token=tg_cfg.get("bot_token", ""),
        chat_id=tg_cfg.get("chat_id", ""),
        car_number=veh_cfg.get("car_number", "EGY-7894"),
        latitude=real_lat,
        longitude=real_lon,
        location_name=real_loc_name,
        repeat_interval_seconds=0,
        send_native_map_pin=tg_cfg.get("send_native_map_pin", True),
        include_url_in_message=tg_cfg.get("include_url_in_message", False),
        show_location_name=veh_cfg.get("show_location_name", False),
    )

    notifier.send_emergency_alert(
        status_note="Real location test: Driver safe, system operational.",
        latitude=real_lat,
        longitude=real_lon,
        location_name=real_loc_name,
        maps_url=maps_url,
        force=True,
        wait=True,
    )
    print("✅ Fixed location alert dispatched to Telegram!")


def main():
    parser = argparse.ArgumentParser(description="Driver Drowsiness Detection & Emergency Alert System")
    parser.add_argument("--config", default="config.json", help="Path to configuration file")
    parser.add_argument("--test-call", action="store_true", help="Send a test WhatsApp voice call & exit")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test Telegram message & exit")
    parser.add_argument("--esp-cam", type=str, help="Override camera with ESP32-CAM stream URL")
    args = parser.parse_args()

    if args.test_call:
        test_whatsapp_call(args.config)
        return

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
