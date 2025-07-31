from pathlib import Path
import unittest
from app.unit_converter import normalize_blood_test_marker

class TestUnitNormalization(unittest.TestCase):
    def test_vitamin_d_ng_per_ml(self):
        self.assertEqual(
            normalize_blood_test_marker("Vitamin D", 20, "ng/mL"),
            ("Vitamin D", 20.0, "ng/mL")
        )

    def test_vitamin_d_ug_per_l(self):
        self.assertEqual(
            normalize_blood_test_marker("Vitamin D", 50, "µg/L"),
            ("Vitamin D", 20.0, "ng/mL")
        )

    def test_iron_ug_dl(self):
        self.assertEqual(
            normalize_blood_test_marker("Iron", 100, "µg/dL"),
            ("Iron", 100.0, "µg/dL")  # Assumes no normalization needed
        )

    def test_invalid_marker(self):
        self.assertEqual(
            normalize_blood_test_marker("XYZ123", 100, "unitless"),
            ("XYZ123", 100, "unitless")
        )

if __name__ == "__main__":
    unittest.main()