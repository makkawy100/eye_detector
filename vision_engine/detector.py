"""
Driver Drowsiness Detector & Real-time Vision Engine
Combines MediaPipe Face Mesh, Eye Aspect Ratio (EAR), Personalized Calibration,
and automated emergency triggers (CallMeBot WhatsApp Voice Call & ESP32 control).
"""

import cv2
import mediapipe as mp
import time
import json
import os
import sys
import logging
from typing import Optional

from vision_engine.ear_calculator import (
    calculate_avg_ear,
    LEFT_EYE_LANDMARKS,
    RIGHT_EYE_LANDMARKS,
)
from vision_engine.calibrator import EARCalibrator
from emergency_alerter.callmebot_notifier import CallMeBotNotifier
from emergency_alerter.telegram_notifier import TelegramNotifier
from emergency_alerter.location_service import LocationService
from vision_engine.esp32_serial_bridge import ESP32SerialBridge

logger = logging.getLogger("DrowsinessDetector")


class DrowsinessDetector:
    def __init__(self, config_path: str = "config.json", simulated_video: bool = False):
        self.config_path = config_path
        self.simulated_video = simulated_video
        self.config = self._load_config()

        # Detection thresholds
        det_cfg = self.config.get("detection", {})
        self.calibration_frames = det_cfg.get("calibration_frames", 90)
        self.threshold_factor = det_cfg.get("ear_threshold_factor", 0.55)
        self.require_both_eyes_closed = det_cfg.get("require_both_eyes_closed", True)
        self.speed_reduce_warning_seconds = det_cfg.get("speed_reduce_warning_seconds", 2.0)
        self.pullover_emergency_seconds = det_cfg.get("pullover_emergency_seconds", 5.0)
        self.maneuver_duration_seconds = det_cfg.get("maneuver_duration_seconds", 4.8)
        self.in_cabin_repeat_interval = det_cfg.get("in_cabin_repeat_interval_seconds", 3.0)

        # Calibrator
        self.calibrator = EARCalibrator(
            target_frames=self.calibration_frames,
            threshold_factor=self.threshold_factor,
        )

        # WhatsApp Alerter
        alerter_cfg = self.config.get("alerter", {}).get("callmebot", {})
        self.alerter = CallMeBotNotifier(
            phone_number=alerter_cfg.get("phone_number", ""),
            api_key=alerter_cfg.get("api_key", ""),
            cooldown_seconds=alerter_cfg.get("cooldown_seconds", 60),
            enable_voice_call=alerter_cfg.get("enable_voice_call", True),
            enable_text_message=alerter_cfg.get("enable_whatsapp_text", True),
            spoken_message=alerter_cfg.get("spoken_message"),
            voice_lang=alerter_cfg.get("voice_language", "en-US-Standard-C"),
            repeat_count=alerter_cfg.get("repeat_count", 2),
            play_in_cabin_audio=alerter_cfg.get("play_in_cabin_audio", True),
        )

        # Location Service (Configured with user's exact coordinates)
        veh_cfg = self.config.get("vehicle", {})
        self.location_service = LocationService(
            default_lat=veh_cfg.get("latitude", 31.209093),
            default_lon=veh_cfg.get("longitude", 29.923094),
            default_location_name=veh_cfg.get("location_name", "Specialized Scientific Programs, Faculty of Engineering"),
            maps_url=veh_cfg.get("maps_url", "https://maps.app.goo.gl/BcYvS5KqdEdAYyi4A"),
            use_fixed_location=veh_cfg.get("use_fixed_location", True),
            gps_serial_port=veh_cfg.get("gps_serial_port"),
            gps_baudrate=veh_cfg.get("gps_baudrate", 9600),
        )

        # Telegram Notifier (Message only with Car Number & GPS Location)
        tg_cfg = self.config.get("alerter", {}).get("telegram", {})
        self.telegram_enabled = tg_cfg.get("enabled", False)
        self.telegram_notifier = TelegramNotifier(
            bot_token=tg_cfg.get("bot_token", ""),
            chat_id=tg_cfg.get("chat_id", ""),
            car_number=veh_cfg.get("car_number", "EGY-7894"),
            latitude=veh_cfg.get("latitude", 31.209093),
            longitude=veh_cfg.get("longitude", 29.923094),
            location_name=veh_cfg.get("location_name", "Specialized Scientific Programs, Faculty of Engineering"),
            repeat_interval_seconds=tg_cfg.get("repeat_interval_seconds", 25),
            send_native_map_pin=tg_cfg.get("send_native_map_pin", True),
            include_url_in_message=tg_cfg.get("include_url_in_message", False),
            show_location_name=veh_cfg.get("show_location_name", False),
        )

        # ESP32 Serial Controller & Motion Bridge
        esp_cfg = self.config.get("esp32", {})
        self.esp32 = ESP32SerialBridge(
            port=esp_cfg.get("port", "/dev/ttyUSB0"),
            baudrate=esp_cfg.get("baudrate", 115200),
            enabled=esp_cfg.get("enabled", True),
            on_stopped_callback=self._on_vehicle_stopped,
        )

        # Multi-stage State tracking
        self.state = "CALIBRATING"  # CALIBRATING, AWAKE, DROWSY_SLOW, PULLING_OVER, STOPPED_EMERGENCY
        self.eye_closed_start_time: Optional[float] = None
        self.pullover_start_time: Optional[float] = None
        self.speed_reduced = False
        self.pullover_initiated = False
        self.vehicle_is_stopped = False
        self.emergency_alerts_sent = False
        self.last_in_cabin_alert_time: float = 0.0
        self.awake_confirm_frames: int = 0

        # MediaPipe Face Mesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def _on_vehicle_stopped(self):
        """Callback from ESP32 confirming autonomous lane-change & full stop."""
        logger.info("ESP32 confirmed vehicle is stopped safely in the right lane.")
        self.vehicle_is_stopped = True

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return json.load(f)
        logger.warning(f"Config file {self.config_path} not found. Using defaults.")
        return {}

    def _open_camera(self) -> cv2.VideoCapture:
        cam_cfg = self.config.get("camera", {})
        source_type = cam_cfg.get("source", "usb")

        if source_type == "esp32_cam":
            url = cam_cfg.get("esp32_cam_url", "http://192.168.1.50:81/stream")
            logger.info(f"Connecting to ESP32-CAM stream: {url}")
            cap = cv2.VideoCapture(url)
        else:
            usb_index = cam_cfg.get("usb_index", 0)
            logger.info(f"Opening USB camera index {usb_index}...")
            cap = cv2.VideoCapture(usb_index)

        return cap

    def draw_hud(
        self,
        frame,
        ear: float,
        closed_duration: float,
        landmarks=None,
        left_ear: float = 0.0,
        right_ear: float = 0.0,
    ):
        """Renders real-time HUD with status, telemetry, openness, and landmarks."""
        h, w, _ = frame.shape

        # Draw eye contours if landmarks detected
        if landmarks:
            for idx in LEFT_EYE_LANDMARKS + RIGHT_EYE_LANDMARKS:
                pt = landmarks[idx]
                cx, cy = int(pt.x * w), int(pt.y * h)
                cv2.circle(frame, (cx, cy), 2, (0, 255, 255), -1)

        # Top status bar background
        cv2.rectangle(frame, (10, 10), (w - 10, 140), (25, 25, 25), -1)
        cv2.rectangle(frame, (10, 10), (w - 10, 140), (80, 80, 80), 1)

        threshold = self.calibrator.closure_threshold or 0.16
        is_one_eye_closed = (
            self.calibrator.is_complete
            and ((left_ear < threshold and right_ear >= threshold) or (right_ear < threshold and left_ear >= threshold))
        )

        # 1. State badge
        if not self.calibrator.is_complete:
            status_text = f"CALIBRATING BASELINE: {int(self.calibrator.progress_ratio * 100)}% (Look ahead normally)"
            status_color = (255, 200, 0)
        elif self.state == "STOPPED_EMERGENCY":
            status_text = "STAGE 3: CAR STOPPED IN RIGHT LANE - EMERGENCY ALERTS SENT!"
            status_color = (0, 0, 255)
        elif self.state == "PULLING_OVER":
            status_text = "STAGE 2: 5s CLOSURE - AUTONOMOUS PULL-OVER TO RIGHT LANE..."
            status_color = (0, 140, 255)
        elif self.state == "DROWSY_SLOW":
            status_text = f"STAGE 1: 2s CLOSURE - WARNING SOUNDED & SPEED REDUCED 50% ({closed_duration:.1f}s)"
            status_color = (0, 215, 255)
        elif is_one_eye_closed:
            status_text = "STATUS: AWAKE (One Eye Winking/Closed)"
            status_color = (0, 255, 200)
        else:
            status_text = "STATUS: DRIVER AWAKE (Both Eyes Open)"
            status_color = (0, 255, 0)

        cv2.putText(
            frame,
            status_text,
            (25, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.70,
            status_color,
            2,
        )

        # 2. Telemetry: Left EAR, Right EAR, Threshold & Openness %
        openness = self.calibrator.get_openness_percentage(ear)
        ear_text = f"L-EAR: {left_ear:.3f} | R-EAR: {right_ear:.3f}"
        if self.calibrator.closure_threshold:
            thresh_text = f"Thresh: {self.calibrator.closure_threshold:.3f} (55% of Base {self.calibrator.baseline_ear:.3f}) | Open: {openness}%"
        else:
            thresh_text = "Threshold: Calibrating..."

        cv2.putText(frame, ear_text, (25, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 1)
        cv2.putText(frame, thresh_text, (330, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (200, 200, 200), 1)

        # Visual Openness Bar
        bar_x = 25
        bar_y = 95
        bar_w = 260
        bar_h = 10
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (60, 60, 60), -1)
        fill_w = int((openness / 100.0) * bar_w)
        fill_color = (0, 255, 0) if openness > 45 else ((0, 165, 255) if openness > 25 else (0, 0, 255))
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), fill_color, -1)

        # 3. Instruction line
        keys_hint = "Keys: [Q] Quit | [C] Recalibrate | [T] Test Call | [R] Reset Alert"
        cv2.putText(frame, keys_hint, (25, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (170, 170, 170), 1)

        # 4. Flashing Emergency Banner
        if self.state in ("PULLING_OVER", "STOPPED_EMERGENCY"):
            border_color = (0, 0, 255) if self.state == "STOPPED_EMERGENCY" else (0, 140, 255)
            cv2.rectangle(frame, (0, 0), (w, h), border_color, 8)
            if self.state == "PULLING_OVER":
                cv2.putText(
                    frame,
                    "STAGE 2: 5s EYE CLOSURE DETECTED!",
                    (int(w * 0.05), int(h * 0.52)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.80,
                    (0, 140, 255),
                    2,
                )
                cv2.putText(
                    frame,
                    "AUTONOMOUS PULL-OVER TO RIGHT LANE & BRAKING...",
                    (int(w * 0.05), int(h * 0.62)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.68,
                    (0, 255, 255),
                    2,
                )
            else:
                cv2.putText(
                    frame,
                    "STAGE 3: VEHICLE STOPPED SAFELY IN RIGHT LANE",
                    (int(w * 0.05), int(h * 0.52)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.78,
                    (0, 0, 255),
                    3,
                )
                cv2.putText(
                    frame,
                    "EMERGENCY ALERTS DISPATCHED (TELEGRAM PIN + WHATSAPP CALL)",
                    (int(w * 0.05), int(h * 0.62)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.58,
                    (0, 0, 255),
                    2,
                )
        elif self.state == "DROWSY_SLOW":
            cv2.putText(
                frame,
                "STAGE 1: 2s CLOSURE - SPEED REDUCED 50% - AUDIO ALERT PLAYING",
                (int(w * 0.03), int(h * 0.95)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 215, 255),
                2,
            )

    def process_frame(self, frame):
        """Processes a single BGR frame and updates detection state."""
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        ear = 0.0
        left_ear = 0.0
        right_ear = 0.0
        closed_duration = 0.0
        landmarks = None

        if results.multi_face_landmarks:
            landmarks = results.multi_face_landmarks[0].landmark
            avg_ear, left_ear, right_ear = calculate_avg_ear(landmarks)
            ear = avg_ear

            # Calibration phase
            if not self.calibrator.is_complete:
                if self.calibrator.update(ear):
                    logger.info(
                        f"Calibration Complete! Baseline EAR: {self.calibrator.baseline_ear:.3f}, "
                        f"Threshold: {self.calibrator.closure_threshold:.3f}"
                    )
                self.state = "CALIBRATING"
            else:
                threshold = self.calibrator.closure_threshold

                # Eye Closure Evaluation:
                # Require BOTH eyes to be closed to prevent false alarms on winking or partial squints
                if self.require_both_eyes_closed:
                    is_closed_frame = (left_ear < threshold) and (right_ear < threshold)
                else:
                    is_closed_frame = (ear < threshold)

                if is_closed_frame:
                    self.awake_confirm_frames = 0
                    now = time.time()
                    if self.eye_closed_start_time is None:
                        self.eye_closed_start_time = now
                    closed_duration = now - self.eye_closed_start_time

                    if closed_duration >= self.pullover_emergency_seconds:
                        # STAGE 2 & 3: 5.0 seconds reached -> Pull-over to right lane and stop
                        if not self.pullover_initiated:
                            self.pullover_initiated = True
                            self.pullover_start_time = now
                            logger.warning("🚨 5s EYE CLOSURE DETECTED! Initiating autonomous right-lane pull-over...")
                            self.esp32.send_command("EMERGENCY_PULLOVER")
                            self.alerter.play_in_cabin_alert(
                                "Danger! Five seconds eye closure! Pulling over to right lane and stopping."
                            )

                        # Check if vehicle has completed stopping
                        maneuver_elapsed = now - (self.pullover_start_time or now)
                        if self.vehicle_is_stopped or maneuver_elapsed >= self.maneuver_duration_seconds:
                            self.vehicle_is_stopped = True
                            self.state = "STOPPED_EMERGENCY"

                            # STAGE 3: Send emergency alert once vehicle is stopped
                            if not self.emergency_alerts_sent:
                                self.emergency_alerts_sent = True
                                logger.warning("🛑 VEHICLE FULLY STOPPED IN RIGHT LANE! Sending emergency alerts...")

                                # 1. Trigger WhatsApp voice call & text
                                self.alerter.trigger_emergency(
                                    reason="Driver asleep for >5s! Vehicle pulled over to right lane and stopped safely."
                                )

                                # 2. Telegram Alert with interactive map pin
                                if self.telegram_enabled:
                                    real_lat, real_lon, real_loc_name, maps_url = self.location_service.get_location()
                                    self.telegram_notifier.send_emergency_alert(
                                        status_note="Vehicle pulled over to right lane and stopped safely. Driver unresponsive.",
                                        latitude=real_lat,
                                        longitude=real_lon,
                                        location_name=real_loc_name,
                                        maps_url=maps_url,
                                        force=True,
                                    )

                            # In-cabin voice alarm repeats every 3s as long as eyes remain closed
                            if now - self.last_in_cabin_alert_time >= self.in_cabin_repeat_interval:
                                self.last_in_cabin_alert_time = now
                                self.alerter.play_in_cabin_alert(
                                    "Warning! Driver sleeping! Vehicle stopped in right lane! Emergency alerts dispatched!"
                                )
                        else:
                            self.state = "PULLING_OVER"

                    elif closed_duration >= self.speed_reduce_warning_seconds:
                        # STAGE 1: 2.0 seconds reached -> Play alert and reduce speed by 50%
                        self.state = "DROWSY_SLOW"
                        if not self.speed_reduced:
                            self.speed_reduced = True
                            logger.warning("⚠️ 2s EYE CLOSURE DETECTED! Warning sounded and speed reduced by 50%.")
                            self.esp32.send_command("SLOW_50")
                            self.alerter.play_in_cabin_alert("Warning! Wake up! Speed reduced by 50 percent!")
                            self.last_in_cabin_alert_time = now
                    else:
                        self.state = "AWAKE"
                else:
                    # At least one eye is open, or both are open -> Driver can see
                    self.eye_closed_start_time = None
                    closed_duration = 0.0
                    self.awake_confirm_frames += 1

                    # Driver opened eyes during STAGE 1 (before 5s) -> immediately restore normal speed
                    if self.speed_reduced and not self.pullover_initiated:
                        logger.info("Driver opened eyes during warning stage! Restoring NORMAL speed.")
                        self.esp32.send_command("NORMAL")
                        self.speed_reduced = False
                        self.state = "AWAKE"

                    # After 15 consecutive awake frames (~0.5s), re-arm pull-over and alerts
                    elif self.awake_confirm_frames >= 15:
                        if self.speed_reduced or self.pullover_initiated or self.emergency_alerts_sent:
                            logger.info("Driver confirmed awake! Restoring NORMAL vehicle operation & re-arming alerts.")
                            self.esp32.send_command("NORMAL")
                            self.speed_reduced = False
                            self.pullover_initiated = False
                            self.vehicle_is_stopped = False
                            self.pullover_start_time = None
                            self.emergency_alerts_sent = False
                            if self.telegram_enabled:
                                self.telegram_notifier.reset_cooldown()
                        self.state = "AWAKE"
        else:
            # No face detected
            self.eye_closed_start_time = None
            if self.calibrator.is_complete:
                self.state = "AWAKE"

        self.draw_hud(frame, ear, closed_duration, landmarks, left_ear, right_ear)
        return frame

    def run(self):
        """Runs the live video capture loop."""
        cap = self._open_camera()

        if not cap.isOpened():
            logger.error("Could not open video camera! Checking if headless or no camera attached.")
            print("\n" + "!" * 60)
            print("CAMERA ERROR: Unable to access camera device.")
            print("If you are running on a machine without a physical webcam,")
            print("you can run automated simulation tests via:")
            print("   python3 -m tests.test_pipeline")
            print("!" * 60 + "\n")
            return

        logger.info("Video capture started. Look at the camera with eyes open to calibrate.")

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    logger.error("Failed to read frame from camera stream.")
                    break

                # Mirror frame for natural webcam feel
                frame = cv2.flip(frame, 1)

                processed_frame = self.process_frame(frame)
                cv2.imshow("Driver Drowsiness Detector (Press Q to quit)", processed_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    logger.info("Exiting on user request.")
                    break
                elif key == ord("c"):
                    logger.info("Resetting calibration on user request.")
                    self.calibrator.reset()
                elif key == ord("t"):
                    logger.info("Manual test of WhatsApp voice call triggered via 'T' key.")
                    self.alerter.trigger_emergency(reason="Manual test alert from Driver Safety System.")
                elif key == ord("r"):
                    logger.info("Emergency state reset on user request.")
                    self.emergency_alerts_sent = False
                    self.speed_reduced = False
                    self.pullover_initiated = False
                    self.vehicle_is_stopped = False
                    self.pullover_start_time = None
                    self.eye_closed_start_time = None
                    self.esp32.send_command("NORMAL")
                    self.state = "AWAKE"

        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.face_mesh.close()
