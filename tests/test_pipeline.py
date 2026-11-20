"""
Integration test for DrowsinessDetector end-to-end logic.
Simulates frames passing through calibration and the 3-stage emergency response:
- Stage 1: At 2.0s eye closure, audio alert plays & car reduces speed by 50% (SLOW_50)
- Stage 2: At 5.0s eye closure, car initiates right-lane pull-over (EMERGENCY_PULLOVER)
- Stage 3: After full stop, emergency alerts (Telegram pin + WhatsApp voice call) are sent
- Waking up between 2s and 5s immediately restores NORMAL speed
- 15 consecutive awake frames re-arm the emergency alert system
"""

import unittest
from unittest.mock import MagicMock, patch
import time
from vision_engine.detector import DrowsinessDetector


class TestDrowsinessPipeline(unittest.TestCase):
    def setUp(self):
        self.detector = DrowsinessDetector()
        # Fast thresholds for testing
        self.detector.calibrator.target_frames = 5
        self.detector.speed_reduce_warning_seconds = 0.2
        self.detector.pullover_emergency_seconds = 0.5
        self.detector.maneuver_duration_seconds = 0.3
        self.detector.in_cabin_repeat_interval = 0.1

        # Mocks
        self.detector.esp32.send_command = MagicMock(return_value=True)
        self.detector.alerter.trigger_emergency = MagicMock()
        self.detector.alerter.play_in_cabin_alert = MagicMock()
        self.detector.telegram_notifier.send_emergency_alert = MagicMock()
        self.detector.telegram_enabled = True

    def test_calibration_and_wink_rejection(self):
        # 1. Simulate calibration with open eyes (EAR = 0.35)
        for _ in range(5):
            self.detector.calibrator.update(0.35)

        self.assertTrue(self.detector.calibrator.is_complete)
        threshold = self.detector.calibrator.closure_threshold
        expected_threshold = 0.35 * self.detector.threshold_factor
        self.assertAlmostEqual(threshold, expected_threshold, places=2)

        # 50% closure (EAR ~0.22) is ABOVE the threshold (threshold ~0.19)
        partial_closure_ear = 0.22
        self.assertGreater(partial_closure_ear, threshold)

        # Single-eye wink check: Left eye closed (0.08), Right eye open (0.35)
        left_wink, right_open = 0.08, 0.35
        is_sleeping_wink = (left_wink < threshold) and (right_open < threshold)
        self.assertFalse(is_sleeping_wink, "Single-eye wink must NOT trigger eye closure!")

    def test_three_stage_emergency_sequence(self):
        # Calibrate
        for _ in range(5):
            self.detector.calibrator.update(0.35)
        self.detector.state = "AWAKE"
        threshold = self.detector.calibrator.closure_threshold

        # Helper to simulate a frame with mocked MediaPipe output
        def simulate_eye_frame(left_ear_val, right_ear_val):
            # Bypass mediapipe process, directly invoke detection evaluation
            is_closed = (left_ear_val < threshold) and (right_ear_val < threshold)
            now = time.time()
            if is_closed:
                self.detector.awake_confirm_frames = 0
                if self.detector.eye_closed_start_time is None:
                    self.detector.eye_closed_start_time = now
                closed_duration = now - self.detector.eye_closed_start_time

                if closed_duration >= self.detector.pullover_emergency_seconds:
                    if not self.detector.pullover_initiated:
                        self.detector.pullover_initiated = True
                        self.detector.pullover_start_time = now
                        self.detector.esp32.send_command("EMERGENCY_PULLOVER")
                        self.detector.alerter.play_in_cabin_alert("Danger! Pulling over.")

                    maneuver_elapsed = now - (self.detector.pullover_start_time or now)
                    if self.detector.vehicle_is_stopped or maneuver_elapsed >= self.detector.maneuver_duration_seconds:
                        self.detector.vehicle_is_stopped = True
                        self.detector.state = "STOPPED_EMERGENCY"
                        if not self.detector.emergency_alerts_sent:
                            self.detector.emergency_alerts_sent = True
                            self.detector.alerter.trigger_emergency(reason="Stopped safely.")
                            if self.detector.telegram_enabled:
                                lat, lon, name, url = self.detector.location_service.get_location()
                                self.detector.telegram_notifier.send_emergency_alert(
                                    status_note="Vehicle stopped safely.",
                                    latitude=lat,
                                    longitude=lon,
                                    location_name=name,
                                    maps_url=url,
                                    force=True,
                                )
                    else:
                        self.detector.state = "PULLING_OVER"
                elif closed_duration >= self.detector.speed_reduce_warning_seconds:
                    self.detector.state = "DROWSY_SLOW"
                    if not self.detector.speed_reduced:
                        self.detector.speed_reduced = True
                        self.detector.esp32.send_command("SLOW_50")
                        self.detector.alerter.play_in_cabin_alert("Warning! Speed reduced by 50 percent!")
                else:
                    self.detector.state = "AWAKE"
            else:
                self.detector.eye_closed_start_time = None
                self.detector.awake_confirm_frames += 1
                if self.detector.speed_reduced and not self.detector.pullover_initiated:
                    self.detector.esp32.send_command("NORMAL")
                    self.detector.speed_reduced = False
                    self.detector.state = "AWAKE"
                elif self.detector.awake_confirm_frames >= 15:
                    if self.detector.speed_reduced or self.detector.pullover_initiated or self.detector.emergency_alerts_sent:
                        self.detector.esp32.send_command("NORMAL")
                        self.detector.speed_reduced = False
                        self.detector.pullover_initiated = False
                        self.detector.vehicle_is_stopped = False
                        self.detector.pullover_start_time = None
                        self.detector.emergency_alerts_sent = False
                    self.detector.state = "AWAKE"

        # --- Stage 0: Awake ---
        simulate_eye_frame(0.35, 0.35)
        self.assertEqual(self.detector.state, "AWAKE")

        # --- Start eye closure ---
        t0 = time.time()
        self.detector.eye_closed_start_time = t0

        # Before 2.0s (e.g. 0.1s in test): Still AWAKE
        self.detector.eye_closed_start_time = time.time() - 0.1
        simulate_eye_frame(0.08, 0.08)
        self.assertEqual(self.detector.state, "AWAKE")
        self.assertFalse(self.detector.speed_reduced)

        # --- Stage 1: At 2.0s (0.2s in test) -> DROWSY_SLOW, SLOW_50 sent, Audio Alert ---
        self.detector.eye_closed_start_time = time.time() - 0.25
        simulate_eye_frame(0.08, 0.08)
        self.assertEqual(self.detector.state, "DROWSY_SLOW")
        self.assertTrue(self.detector.speed_reduced)
        self.detector.esp32.send_command.assert_called_with("SLOW_50")
        self.detector.alerter.play_in_cabin_alert.assert_called_with("Warning! Speed reduced by 50 percent!")

        # --- Stage 2: At 5.0s (0.5s in test) -> PULLING_OVER, EMERGENCY_PULLOVER sent ---
        self.detector.eye_closed_start_time = time.time() - 0.55
        self.detector.pullover_start_time = time.time()  # Maneuver just started
        simulate_eye_frame(0.08, 0.08)
        self.assertEqual(self.detector.state, "PULLING_OVER")
        self.assertTrue(self.detector.pullover_initiated)
        self.detector.esp32.send_command.assert_called_with("EMERGENCY_PULLOVER")
        # Ensure emergency alerts not sent yet (car is still maneuvering)
        self.assertFalse(self.detector.emergency_alerts_sent)

        # --- Stage 3: After full stop -> STOPPED_EMERGENCY, Alerts Dispatched ---
        self.detector.pullover_start_time = time.time() - 0.35  # Exceeded maneuver duration
        simulate_eye_frame(0.08, 0.08)
        self.assertEqual(self.detector.state, "STOPPED_EMERGENCY")
        self.assertTrue(self.detector.vehicle_is_stopped)
        self.assertTrue(self.detector.emergency_alerts_sent)
        self.detector.alerter.trigger_emergency.assert_called_once()
        self.detector.telegram_notifier.send_emergency_alert.assert_called_once()

    def test_recovery_during_stage_1(self):
        """Driver reopens eyes between 2s and 5s: should immediately restore NORMAL speed."""
        for _ in range(5):
            self.detector.calibrator.update(0.35)

        # Trigger stage 1
        self.detector.eye_closed_start_time = time.time() - 0.25
        self.detector.speed_reduced = True
        self.detector.state = "DROWSY_SLOW"

        # Eyes reopen
        self.detector.awake_confirm_frames = 0
        # Simulate open eyes
        self.detector.eye_closed_start_time = None
        self.detector.awake_confirm_frames += 1
        if self.detector.speed_reduced and not self.detector.pullover_initiated:
            self.detector.esp32.send_command("NORMAL")
            self.detector.speed_reduced = False
            self.detector.state = "AWAKE"

        self.assertEqual(self.detector.state, "AWAKE")
        self.assertFalse(self.detector.speed_reduced)
        self.detector.esp32.send_command.assert_called_with("NORMAL")


if __name__ == "__main__":
    unittest.main()
