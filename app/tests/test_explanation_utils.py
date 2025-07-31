from pathlib import Path
import unittest
from app.data_model import SupplementRecommendation
from app.explanation_utils import build_concise_explanation, build_structured_explanation

class TestExplanationUtils(unittest.TestCase):

    def setUp(self):
        self.base_rec = SupplementRecommendation(
            name="Vitamin D",
            dosage=800,
            unit="IU",
            reason=None,
            triggered_by=["fatigue", "low mood", "poor sleep", "anxiety"],
            contraindications=["hypercalcemia"],
            inputs_triggered=[
                "goal: improve mood",
                "goal: increase energy",
                "blood_test: Vitamin D=15 ng/mL",
                "wearable: sleep_hours",
                "wearable: sunlight_exposure_minutes",
                "feedback: energy=low",
                "feedback symptom: fatigue"
            ],
            validation_flags=["⚠️ Check dosage"]
        )

    def test_build_concise_explanation_basic(self):
        explanation = build_concise_explanation(self.base_rec)
        self.assertIn("symptoms: fatigue, low mood, poor sleep", explanation)
        self.assertIn("goals: improve mood, increase energy", explanation)
        self.assertIn("lab results: Vitamin D=15 ng/mL", explanation)
        self.assertIn("low sunlight exposure", explanation)
        self.assertIn("recent feedback: energy=low, fatigue", explanation)

    def test_build_concise_explanation_no_inputs(self):
        rec = SupplementRecommendation(
            name="Magnesium",
            dosage=400,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[],
            validation_flags=[]
        )
        explanation = build_concise_explanation(rec)
        self.assertEqual(explanation, "Recommended based on your profile.")

    def test_build_structured_explanation(self):
        structured = build_structured_explanation(self.base_rec)
        self.assertEqual(structured["symptoms"], ["fatigue", "low mood", "poor sleep"])
        self.assertEqual(structured["goals"], ["improve mood", "increase energy"])
        self.assertEqual(structured["lab_results"], ["Vitamin D=15 ng/mL"])
        self.assertIn("low sunlight exposure", structured["wearable_data"])
        self.assertIn("energy=low", structured["recent_feedback"])
        self.assertIn("⚠️ Check dosage", structured["warnings"])
        self.assertIn("hypercalcemia", structured["contraindications"])

    def test_build_structured_explanation_empty(self):
        rec = SupplementRecommendation(
            name="Iron",
            dosage=30,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[],
            validation_flags=[]
        )
        structured = build_structured_explanation(rec)
        self.assertEqual(structured["symptoms"], [])
        self.assertEqual(structured["goals"], [])
        self.assertEqual(structured["lab_results"], [])
        self.assertEqual(structured["wearable_data"], [])
        self.assertEqual(structured["recent_feedback"], [])
        self.assertEqual(structured["warnings"], [])
        self.assertEqual(structured["contraindications"], [])

if __name__ == "__main__":
    unittest.main()