"""
Unit tests for Eye Aspect Ratio (EAR) calculation and calibration logic.
"""

import unittest
from collections import namedtuple
from vision_engine.ear_calculator import calculate_eye_ear, calculate_avg_ear, LEFT_EYE_LANDMARKS, RIGHT_EYE_LANDMARKS
from vision_engine.calibrator import EARCalibrator

Point = namedtuple("Point", ["x", "y"])


class TestEARMath(unittest.TestCase):
    def setUp(self):
        # Create a mock landmark map (index -> Point)
        # Using 500 dummy points
        self.landmarks = [Point(0.0, 0.0) for _ in range(500)]

    def test_open_eye_ratio(self):
        # Set up an eye with wide opening:
        # P1: (0.1, 0.5), P4: (0.3, 0.5) -> horizontal = 0.2
        # P2: (0.15, 0.44), P6: (0.15, 0.56) -> vertical_1 = 0.12
        # P3: (0.25, 0.44), P5: (0.25, 0.56) -> vertical_2 = 0.12
        # EAR = (0.12 + 0.12) / (2 * 0.2) = 0.24 / 0.40 = 0.60
        indices = LEFT_EYE_LANDMARKS
        self.landmarks[indices[0]] = Point(0.1, 0.5)
        self.landmarks[indices[1]] = Point(0.15, 0.44)
        self.landmarks[indices[2]] = Point(0.25, 0.44)
        self.landmarks[indices[3]] = Point(0.3, 0.5)
        self.landmarks[indices[4]] = Point(0.25, 0.56)
        self.landmarks[indices[5]] = Point(0.15, 0.56)

        ear = calculate_eye_ear(self.landmarks, indices)
        self.assertAlmostEqual(ear, 0.60, places=2)

    def test_closed_eye_ratio(self):
        # Set up a closed eye where upper and lower eyelids meet:
        # P1: (0.1, 0.5), P4: (0.3, 0.5) -> horizontal = 0.2
        # P2: (0.15, 0.50), P6: (0.15, 0.51) -> vertical_1 = 0.01
        # P3: (0.25, 0.50), P5: (0.25, 0.51) -> vertical_2 = 0.01
        # EAR = (0.01 + 0.01) / (2 * 0.2) = 0.02 / 0.40 = 0.05
        indices = RIGHT_EYE_LANDMARKS
        self.landmarks[indices[0]] = Point(0.1, 0.5)
        self.landmarks[indices[1]] = Point(0.15, 0.50)
        self.landmarks[indices[2]] = Point(0.25, 0.50)
        self.landmarks[indices[3]] = Point(0.3, 0.5)
        self.landmarks[indices[4]] = Point(0.25, 0.51)
        self.landmarks[indices[5]] = Point(0.15, 0.51)

        ear = calculate_eye_ear(self.landmarks, indices)
        self.assertAlmostEqual(ear, 0.05, places=2)
        self.assertLess(ear, 0.20)  # Well below normal open eye threshold


class TestCalibration(unittest.TestCase):
    def test_calibration_workflow(self):
        calibrator = EARCalibrator(target_frames=10, threshold_factor=0.75)
        self.assertFalse(calibrator.is_complete)

        # Simulate 10 frames of open eyes at 0.32 EAR
        for _ in range(10):
            calibrator.update(0.32)

        self.assertTrue(calibrator.is_complete)
        self.assertAlmostEqual(calibrator.baseline_ear, 0.32, places=3)
        # Expected threshold: 0.32 * 0.75 = 0.24
        self.assertAlmostEqual(calibrator.closure_threshold, 0.24, places=3)


if __name__ == "__main__":
    unittest.main()
