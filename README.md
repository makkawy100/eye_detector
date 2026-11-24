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

## How to launch

Open a terminal in the project folder, then install the dependencies and start the detector:

```bash
git clone https://github.com/makkawy100/eye_detector.git
cd eye_detector
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 main.py
```

The detector can run without Telegram credentials. To enable optional Telegram alerts, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your shell environment before starting it. Do not save those values in the repository. To send a Telegram test alert and exit, run `python3 main.py --test-telegram` after setting them.
Run tests with `PYTHONPATH=. python3 -m unittest discover tests`.

Press `Q` to quit, `C` to recalibrate, and `R` to reset the emergency state.
