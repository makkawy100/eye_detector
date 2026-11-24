# 🚗 Driver Drowsiness Emergency Brake & Autonomous Pull-Over System

An intelligent, real-time driver safety system built with **Computer Vision (MediaPipe Face Mesh + Eye Aspect Ratio)** and an **autonomous 3-stage emergency response** pipeline.

---

## 🌟 Key Features

1. **Precision Eye Tracking (MediaPipe 468 Face Mesh)**:
   - Tracks 6 landmarks per eye to calculate Eye Aspect Ratio (EAR).
   - **Two-Eye Requirement**: Requires both eyes to be closed to prevent false alarms on winking or glancing.
   - **Dynamic Personal Calibration**: Automatically calibrates to the driver's normal open-eye baseline over 90 frames, with a `0.55` threshold factor so 50% squints do not trigger false alarms.

2. **Autonomous 3-Stage Emergency Response**:
   - **Stage 1 (At 2.0s eye closure)**: Sounds an audio alert (*"Warning! Wake up! Speed reduced by 50 percent!"*) and sends `SLOW_50` to cut speed by 50%.
   - **Early Wakeup Recovery**: Reopening eyes between 2.0s and 5.0s immediately restores `NORMAL` full speed.
   - **Stage 2 (At 5.0s eye closure)**: Triggers `EMERGENCY_PULLOVER` for autonomous right-lane change maneuver and progressive braking to a full stop.
   - **Stage 3 (After Full Stop)**: Dispatches zero-cost emergency alerts:
     - **Telegram Bot (@Driver7_bot)**: High-priority message with Car Number (`EGY-7894`), exact coordinates, and interactive native GPS map pin (`sendLocation`).
     - **In-Cabin Continuous Alarm**: Repeating audio warning every 3 seconds until the driver is confirmed awake.

3. **Software Simulation & Hardware Bridge**:
   - Supports direct serial communication with ESP32 microcontrollers over USB UART (115200 baud).
   - Operates in full software simulation mode when hardware is not connected.

---

## 📁 Project Architecture

```
eye/
├── main.py                          # Application entry point & CLI diagnostic tool
├── config.json                      # System thresholds, car plate, credentials
├── requirements.txt                 # Pinned dependencies
├── EXPLANATION_CHARTS.md            # Mermaid diagrams (FSM, Sequence, Architecture)
├── vision_engine/
│   ├── detector.py                  # Real-time detection loop & 3-stage state machine
│   ├── calibrator.py                # Personalized baseline EAR calibrator
│   ├── ear_calculator.py            # 6-point Euclidean distance EAR calculations
│   └── esp32_serial_bridge.py       # Serial driver with software simulation fallback
├── emergency_alerter/
│   ├── telegram_notifier.py         # Telegram Bot dispatcher (clean text + GPS pin)
│   └── location_service.py          # Fixed / GPS / IP geolocation resolver
└── tests/
    ├── test_ear.py                  # Unit tests for EAR math & calibration
    └── test_pipeline.py             # Integration tests for 3-stage emergency sequence
```

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/makkawy100/eye_detector.git
cd eye_detector
pip install -r requirements.txt
```

### 2. Run Live Detection
```bash
python3 main.py
```

### 3. Test Emergency Dispatchers
- **Test Telegram GPS Pin & Coordinates**:
  ```bash
  python3 main.py --test-telegram
  ```
- **Test WhatsApp Voice Call**:
  ```bash
  python3 main.py --test-call
  ```

### 4. Run Automated Test Suite
```bash
PYTHONPATH=. python3 -m unittest discover tests
```

---

## ⌨️ Real-Time Keyboard Controls
- `Q`: Quit detection loop.
- `C`: Recalibrate baseline EAR.
- `T`: Trigger manual test call.
- `R`: Reset emergency state and restore normal driving.
