# System Architecture & Workflow Charts: Driver Drowsiness Emergency Brake System

This document provides visual flowcharts, state machine diagrams, sequence diagrams, and mathematical models explaining the entire architecture of the Driver Drowsiness Detection & Autonomous Emergency Response System.

---

## 1. High-Level System Architecture

```mermaid
flowchart TD
    subgraph SENSING["1. SENSING LAYER"]
        CAM["Live Video Stream\n(USB WebCam or ESP32-CAM)"]
        GPS["Location Provider\n(Fixed / GPS Serial / IP)"]
    end

    subgraph VISION["2. VISION & AI ENGINE"]
        MP["MediaPipe 468 Face Mesh\n(Real-time Landmark Tracking)"]
        EAR["EAR Calculator\n(6-point Euclidean Math)"]
        CALIB["Dynamic Calibrator\n(90-frame baseline @ 0.55 factor)"]
        DET["Drowsiness State Machine\n(Two-Eye Verification & 3 Stages)"]
    end

    subgraph CONTROL["3. VEHICLE CONTROL LAYER"]
        BRIDGE["ESP32 Serial Bridge\n(UART 115200 / Software Sim)"]
        ESP["ESP32 Microcontroller\n(Motors, Steering Servo, Hazards)"]
    end

    subgraph ALERTING["4. ZERO-COST EMERGENCY DISPATCH"]
        TG["Telegram Bot @Driver7_bot\n(Chat 1605794011 - Text + Native GPS Pin)"]
        CB["CallMeBot WhatsApp\n(Automated Voice Call TTS + WhatsApp Text)"]
        CABIN["In-Cabin Audio Alarm\n(spd-say / espeak repeated every 3s)"]
    end

    CAM --> MP
    MP --> EAR
    EAR --> CALIB
    CALIB --> DET
    GPS --> TG

    DET -- "Stage 1 (>= 2s): SLOW_50" --> BRIDGE
    DET -- "Stage 2 (>= 5s): EMERGENCY_PULLOVER" --> BRIDGE
    DET -- "Stage 3 (Stopped): Dispatch" --> TG
    DET -- "Stage 3 (Stopped): Call" --> CB
    DET -- "Stage 1 & 3: Voice Alert" --> CABIN
    BRIDGE --> ESP
    ESP -- "STATUS:STOPPED" --> BRIDGE
```

---

## 2. 3-Stage Emergency Response Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Driver as "Driver (Camera)"
    participant Vision as "Vision Engine (detector.py)"
    participant ESP as "ESP32 / Car Simulation"
    participant Audio as "In-Cabin Audio"
    participant TG as "Telegram (@Driver7_bot)"
    participant WA as "WhatsApp (CallMeBot)"

    Note over Driver,Vision: Normal Driving State (Cruising 100% Speed)

    Driver->>Vision: Both eyes close (EAR < Threshold)
    Note over Vision: Timer starts counting closure duration

    rect rgb(255, 245, 210)
        Note over Vision,Audio: STAGE 1: 2.0s Eye Closure Reached
        Vision->>ESP: Command: SLOW_50
        ESP-->>ESP: Motor speed reduced to 50% PWM
        Vision->>Audio: Play: "Warning! Wake up! Speed reduced by 50%"
    end

    alt Driver Wakes Up Between 2.0s and 5.0s
        Driver->>Vision: Driver opens eyes
        Vision->>ESP: Command: NORMAL (Cruising 100% restored)
        Note over Driver,Vision: System immediately returns to AWAKE
    else Eyes Remain Closed >= 5.0s
        rect rgb(255, 220, 200)
            Note over Vision,ESP: STAGE 2: 5.0s Eye Closure Reached
            Vision->>ESP: Command: EMERGENCY_PULLOVER
            ESP-->>ESP: Steer 30° right -> Counter-steer 30° left -> Center
            ESP-->>ESP: Progressive braking to 0 PWM (Full Stop) + Hazards ON
            Vision->>Audio: Play: "Danger! Five seconds closure! Pulling over!"
        end

        ESP->>Vision: Serial feedback: "STATUS:STOPPED"

        rect rgb(255, 200, 200)
            Note over Vision,WA: STAGE 3: Vehicle Safely Stopped in Right Lane
            par Concurrent Emergency Alerting
                Vision->>TG: Send Emergency Message (Car EGY-7894 + Coordinates)
                Vision->>TG: sendLocation (Native Interactive GPS Pin)
            and
                Vision->>WA: Trigger Automated WhatsApp Voice Call (TTS)
                Vision->>WA: Send WhatsApp Emergency Text
            and
                loop Every 3 seconds while asleep
                    Vision->>Audio: Play: "Warning! Driver sleeping! Vehicle stopped!"
                end
            end
        end
    end

    opt Driver wakes up after full stop
        Driver->>Vision: Eyes open for 15 consecutive frames
        Vision->>ESP: Command: NORMAL (Release brakes, hazards OFF)
        Vision->>TG: Reset alert cooldown (Re-armed)
        Note over Driver,Vision: Safe driving state restored
    end
```

---

## 3. Finite State Machine (FSM) Diagram

```mermaid
stateDiagram-v2
    [*] --> CALIBRATING: System Launch
    CALIBRATING --> AWAKE: 90 Open-Eye Frames Analyzed (Baseline EAR Calculated)
    
    AWAKE --> AWAKE: Single Eye Wink / 50% Squint (Filtered by 0.55 Factor)
    AWAKE --> DROWSY_SLOW: Both Eyes Closed >= 2.0s\n[Action: SLOW_50 + Voice Alert]
    
    DROWSY_SLOW --> AWAKE: Eyes Reopen Before 5.0s\n[Action: NORMAL 100% Speed Restored]
    DROWSY_SLOW --> PULLING_OVER: Eyes Remain Closed >= 5.0s\n[Action: EMERGENCY_PULLOVER sent]
    
    PULLING_OVER --> STOPPED_EMERGENCY: ESP32 Confirms "STATUS:STOPPED" (or 4.8s elapsed)\n[Action: Send Telegram GPS Pin + WhatsApp Voice Call]
    
    STOPPED_EMERGENCY --> AWAKE: Driver Confirmed Awake (15 frames open)\n[Action: Release brakes, NORMAL speed, Re-arm alerts]
```

---

## 4. Eye Aspect Ratio (EAR) Mathematical Model

```
       P2          P3
        •──────────•
       /            \
  P1  •              •  P4
  (Outer) \        /   (Inner)
        •──────────•
       P6          P5
```

$$\text{EAR} = \frac{\|P_2 - P_6\| + \|P_3 - P_5\|}{2 \times \|P_1 - P_4\|}$$

### Two-Eye Threshold Logic:
- **Baseline EAR**: Calibrated dynamically per driver ($\approx 0.30 - 0.36$).
- **Threshold**: $\text{Baseline} \times 0.55$ ($\approx 0.17 - 0.20$).
- **Wink & Squint Immunity**:
  $$\text{Is Closed} = (\text{Left EAR} < \text{Threshold}) \land (\text{Right EAR} < \text{Threshold})$$
  - If driver winks one eye: $\text{Left} = 0.08, \text{Right} = 0.35 \implies \text{FALSE}$ (Driver remains `AWAKE`).
  - If driver squints 50%: $\text{EAR} = 0.22 > 0.19 \implies \text{FALSE}$ (Driver remains `AWAKE`).
  - If driver sleeps: $\text{Left} = 0.08, \text{Right} = 0.08 \implies \text{TRUE}$ (Drowsiness timer activates).

---

## 5. File Structure & Responsibilities

| File Path | Primary Function | Interactions |
| :--- | :--- | :--- |
| [main.py](file:///home/jo/eye/main.py) | Application entry point, CLI flags (`--test-call`, `--test-telegram`, `--esp-cam`) | Launches `detector.py`, `callmebot_notifier.py`, `telegram_notifier.py` |
| [detector.py](file:///home/jo/eye/vision_engine/detector.py) | Central vision loop, 3-stage state machine, on-screen HUD overlay | Calls `ear_calculator`, `calibrator`, `esp32_serial_bridge`, `alerters` |
| [ear_calculator.py](file:///home/jo/eye/vision_engine/ear_calculator.py) | 6-point Euclidean landmark math for Left and Right EAR | Consumed by `detector.py` and `test_ear.py` |
| [calibrator.py](file:///home/jo/eye/vision_engine/calibrator.py) | Dynamic open-eye baseline calculation over 90 frames | Sets personal closure threshold using 0.55 multiplier |
| [esp32_serial_bridge.py](file:///home/jo/eye/vision_engine/esp32_serial_bridge.py) | USB UART serial communication at 115200 baud with software simulation | Sends `SLOW_50`, `EMERGENCY_PULLOVER`, `NORMAL`; listens for `STATUS:STOPPED` |
| [telegram_notifier.py](file:///home/jo/eye/emergency_alerter/telegram_notifier.py) | High-priority Telegram Bot API dispatcher (@Driver7_bot) | Dispatches text alert + `sendLocation` interactive map pin |
| [callmebot_notifier.py](file:///home/jo/eye/emergency_alerter/callmebot_notifier.py) | WhatsApp automated voice call (TTS) & in-cabin continuous alarm | Calls CallMeBot API (`/call.php`) & local `spd-say`/`espeak` |
| [location_service.py](file:///home/jo/eye/emergency_alerter/location_service.py) | Multi-source location resolver (Fixed GPS / Serial GPS / IP) | Supplies coordinates (`31.209093, 29.923094`) to alert dispatchers |
| [config.json](file:///home/jo/eye/config.json) | Centralized configuration for timings, car plate, credentials, and modes | Read by all modules on startup |
