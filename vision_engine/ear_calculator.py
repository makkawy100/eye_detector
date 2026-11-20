"""
Eye Aspect Ratio (EAR) Calculator
Implements the 6-point eye landmark distance formula based on MediaPipe Face Mesh.
"""

import math
from typing import List, Tuple, Any

# MediaPipe 468/478 Face Mesh landmark indices for eyes
# Points arranged as:
# P1: Outer corner
# P2, P3: Upper eyelid
# P4: Inner corner
# P5, P6: Lower eyelid
LEFT_EYE_LANDMARKS = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_LANDMARKS = [33, 160, 158, 133, 153, 144]


def euclidean_distance(p1: Any, p2: Any) -> float:
    """Computes Euclidean distance between two landmarks (normalized or pixel coords)."""
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def calculate_eye_ear(landmarks: Any, eye_indices: List[int]) -> float:
    """
    Calculates Eye Aspect Ratio (EAR) for a single eye given 6 landmark indices:
    [P1(outer), P2(upper1), P3(upper2), P4(inner), P5(lower2), P6(lower1)]

    Formula:
        EAR = (||P2 - P6|| + ||P3 - P5||) / (2.0 * ||P1 - P4||)
    """
    p1 = landmarks[eye_indices[0]]
    p2 = landmarks[eye_indices[1]]
    p3 = landmarks[eye_indices[2]]
    p4 = landmarks[eye_indices[3]]
    p5 = landmarks[eye_indices[4]]
    p6 = landmarks[eye_indices[5]]

    vertical_1 = euclidean_distance(p2, p6)
    vertical_2 = euclidean_distance(p3, p5)
    horizontal = euclidean_distance(p1, p4)

    if horizontal == 0:
        return 0.0

    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return ear


def calculate_avg_ear(landmarks: Any) -> Tuple[float, float, float]:
    """
    Calculates left EAR, right EAR, and their average.
    Returns: (avg_ear, left_ear, right_ear)
    """
    left_ear = calculate_eye_ear(landmarks, LEFT_EYE_LANDMARKS)
    right_ear = calculate_eye_ear(landmarks, RIGHT_EYE_LANDMARKS)
    avg_ear = (left_ear + right_ear) / 2.0
    return avg_ear, left_ear, right_ear
