"""Reproduce diagnósticos etiquetados de picadas reales y clics falsos."""

from pathlib import Path
import unittest

import numpy as np

from pescaauto.engine import Detection, SplashTracker, bite_confirmed, warm_bobber_area


DIAGNOSTICS = Path(__file__).resolve().parent.parent / "referencias" / "diagnosticos_clave"
LABELED_CASTS = {
    "lance_20261011_045739_006.npz": True,
    "lance_20261011_045746_008.npz": False,
    "lance_20261011_050323_007.npz": False,
    "lance_20261011_050333_008.npz": True,
}
REFERENCE_FIELDS = ("reference", "noise", "chroma_reference", "chroma_noise")


class DetectionTests(unittest.TestCase):
    def test_labeled_casts(self):
        for name, expected_bite in LABELED_CASTS.items():
            with self.subTest(name=name), np.load(DIAGNOSTICS / name) as data:
                frames = data["frames"]
                center = Detection(*map(int, data["center"]), 0)
                tracker = SplashTracker([frames[0]] * 5, center)
                for field in REFERENCE_FIELDS:
                    setattr(tracker, field, data["early_" + field].copy())
                late_index = int(data["late_start_index"])
                detected = False
                for index, frame in enumerate(frames):
                    if index == late_index:
                        for field in REFERENCE_FIELDS:
                            setattr(tracker, field, data[field].copy())
                        tracker.bobber_reference = warm_bobber_area(frame, tracker.bobber_area)
                        tracker.consecutive = 0
                    splash = tracker.observe(frame)
                    detected |= bite_confirmed(tracker, splash, late_index >= 0 and index >= late_index)
                self.assertEqual(detected, expected_bite)


if __name__ == "__main__":
    unittest.main()
