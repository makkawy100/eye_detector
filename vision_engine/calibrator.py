"""
Personalized Eye Aspect Ratio (EAR) Calibrator
Computes individualized baseline and dynamic closure threshold for the driver.
"""

from typing import Optional, List


class EARCalibrator:
    def __init__(self, target_frames: int = 90, threshold_factor: float = 0.55, min_ear_floor: float = 0.14):
        """
        :param target_frames: Number of valid open-eye frames needed to calibrate (~3-4 seconds at 30 fps)
        :param threshold_factor: Multiplier applied to baseline EAR (default: 0.55 to avoid triggering on 50% closure/squinting)
        :param min_ear_floor: Absolute minimum sanity floor for EAR threshold
        """
        self.target_frames = target_frames
        self.threshold_factor = threshold_factor
        self.min_ear_floor = min_ear_floor
        self.collected_values: List[float] = []
        self.baseline_ear: Optional[float] = None
        self.closure_threshold: Optional[float] = None
        self.is_complete = False

    def reset(self):
        """Resets calibration state to calibrate again."""
        self.collected_values.clear()
        self.baseline_ear = None
        self.closure_threshold = None
        self.is_complete = False

    def update(self, current_ear: float) -> bool:
        """
        Adds an EAR observation during the calibration phase.
        Discards extreme low values (blinks) during calibration.
        Returns True when calibration completes.
        """
        if self.is_complete:
            return True

        # Only accumulate if eyes appear reasonably open (prevent calibrating while blinking)
        if current_ear > 0.18:
            self.collected_values.append(current_ear)

        if len(self.collected_values) >= self.target_frames:
            self.baseline_ear = sum(self.collected_values) / len(self.collected_values)
            # Threshold requires actual significant closure (~45%+ closure)
            calculated_threshold = self.baseline_ear * self.threshold_factor
            self.closure_threshold = max(calculated_threshold, self.min_ear_floor)
            self.is_complete = True
            return True

        return False

    def get_openness_percentage(self, ear: float) -> int:
        """Calculates approximate eye openness from 0% (closed) to 100% (fully open)."""
        if not self.baseline_ear or self.baseline_ear == 0:
            return 100
        # Assume closed eye is ~0.10
        closed_floor = 0.10
        span = self.baseline_ear - closed_floor
        if span <= 0:
            return 100
        ratio = (ear - closed_floor) / span
        return int(max(0, min(100, ratio * 100)))

    @property
    def progress_ratio(self) -> float:
        """Returns calibration progress between 0.0 and 1.0."""
        if self.is_complete:
            return 1.0
        return min(1.0, len(self.collected_values) / float(self.target_frames))
