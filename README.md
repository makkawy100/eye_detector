# Driver Drowsiness Detection & Emergency Response

A computer-vision project using MediaPipe Face Mesh and Eye Aspect Ratio (EAR) to detect prolonged eye closure. It includes an ESP32 serial-control bridge, local alarm sounds, and optional Telegram emergency alerts. The project is a prototype and is not a certified or road-safe autonomous driving system.

## Detection and response

- Calibrates an open-eye baseline over 90 frames, then requires both eyes below the configured threshold.
- At 2 seconds of closure, sends `SLOW_50` to the controller and plays a local alarm sound.
- At 5 seconds, sends `EMERGENCY_PULLOVER`; after the configured maneuver interval or stop feedback, it can send a Telegram alert.
- Reopening the eyes restores normal operation and re-arms alerts.

The ESP32, steering and braking behavior depends on external hardware and firmware. This repository's software simulation does not establish that a real vehicle will pull over safely. Do not test on public roads.

## Project layout

- `main.py`: application and Telegram test command.
- `vision_engine/`: eye detection, calibration and ESP32 serial bridge.
- `emergency_alerter/telegram_notifier.py`: optional Telegram text and map-pin alerts.
- `emergency_alerter/local_audio_alert.py`: local-only alarm sound; no network calls.
- `emergency_alerter/location_service.py`: location lookup for alerts.
- `tests/`: unit and pipeline tests.
- `config.json`: non-secret settings.

## Setup

Install dependencies: `pip install -r requirements.txt`. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the process environment to enable Telegram alerts, for example by exporting them in your shell before launch. The names can be changed with `alerter.telegram.bot_token_env` and `alerter.telegram.chat_id_env` in `config.json`. Do not put credentials in tracked files. To run the detector with `python3 main.py`; to test the Telegram notifier use `python3 main.py --test-telegram`.

Run tests with `PYTHONPATH=. python3 -m unittest discover tests`.

Press `Q` to quit, `C` to recalibrate, and `R` to reset the emergency state.
