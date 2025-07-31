from pathlib import Path
# explanation_utils.py

from typing import List, Dict, Optional, Union
from app.data_model import SupplementRecommendation

def build_concise_explanation(rec: SupplementRecommendation) -> str:
    """
    Build a concise explanation string for a SupplementRecommendation object.
    Focus on top symptoms, goals, blood tests, wearable highlights, and feedback.
    """
    parts = []

    # Limit symptoms to 3
    top_symptoms = rec.triggered_by[:3] if rec.triggered_by else []
    if top_symptoms:
        parts.append("symptoms: " + ", ".join(top_symptoms))

    # Extract goals from inputs_triggered
    goals = [s.replace("goal: ", "") for s in rec.inputs_triggered if s.startswith("goal: ")]
    top_goals = goals[:3]
    if top_goals:
        parts.append("goals: " + ", ".join(top_goals))

    # Blood test lines: look for inputs like "blood_test: Marker=Value Unit"
    blood_tests = [s for s in rec.inputs_triggered if s.startswith("blood_test: ")]
    if blood_tests:
        parts.append("lab results: " + ", ".join(bt.replace("blood_test: ", "") for bt in blood_tests))

    # Wearable highlights: look for wearables and low sunlight exposure
    wearables = [s.replace("wearable: ", "") for s in rec.inputs_triggered if s.startswith("wearable: ")]
    if any("sunlight_exposure_minutes" in s for s in rec.inputs_triggered):
        parts.append("low sunlight exposure")
    elif wearables:
        parts.append("wearable data: " + ", ".join(wearables[:3]))

    # Recent feedback highlights (energy, mood, stress)
    feedbacks = [s for s in rec.inputs_triggered if s.startswith("feedback: ") or s.startswith("feedback symptom: ")]
    if feedbacks:
        parts.append("recent feedback: " + ", ".join(fb.replace("feedback: ", "").replace("feedback symptom: ", "") for fb in feedbacks[:3]))

    if not parts:
        return "Recommended based on your profile."

    return "Recommended due to " + "; ".join(parts) + "."

def build_structured_explanation(rec: SupplementRecommendation) -> Dict[str, Union[List[str], None]]:
    """
    Create a dict representing a user-friendly explanation broken into categories.
    """
    explanation = {
        "symptoms": rec.triggered_by[:3] if rec.triggered_by else [],
        "goals": [s.replace("goal: ", "") for s in rec.inputs_triggered if s.startswith("goal: ")][:3],
        "lab_results": [s.replace("blood_test: ", "") for s in rec.inputs_triggered if s.startswith("blood_test: ")],
        "wearable_data": [],
        "recent_feedback": [],
        "warnings": rec.validation_flags or [],
        "contraindications": rec.contraindications or []
    }

    # Add wearables and low sunlight exposure
    wearables = [s.replace("wearable: ", "") for s in rec.inputs_triggered if s.startswith("wearable: ")]
    if any("sunlight_exposure_minutes" in s for s in rec.inputs_triggered):
        explanation["wearable_data"].append("low sunlight exposure")
    elif wearables:
        explanation["wearable_data"].extend(wearables[:3])

    # Add feedback
    feedbacks = [s.replace("feedback: ", "").replace("feedback symptom: ", "") for s in rec.inputs_triggered if s.startswith("feedback: ") or s.startswith("feedback symptom: ")]
    explanation["recent_feedback"].extend(feedbacks[:3])

    return explanation

def build_explanation(rec: SupplementRecommendation) -> str:
    """
    Wrapper to maintain compatibility with existing calls.
    By default, calls concise explanation builder.
    """
    return build_concise_explanation(rec)

def build_explanations_for_list(recs: List[SupplementRecommendation], structured: bool = False) -> List[Union[str, Dict]]:
    """
    Generate explanations for a list of recommendations.
    If structured=True, returns list of dicts, else list of strings.
    """
    if structured:
        return [build_structured_explanation(rec) for rec in recs]
    else:
        return [build_concise_explanation(rec) for rec in recs]

# Simple test run (uncomment to test manually)
# if __name__ == "__main__":
#     from data_model import SupplementRecommendation
#     test_rec = SupplementRecommendation(
#         name="Vitamin D",
#         dosage=800,
#         unit="IU",
#         reason=None,
#         triggered_by=["fatigue", "low mood", "poor sleep"],
#         contraindications=["hypercalcemia"],
#         inputs_triggered=[
#             "goal: improve mood",
#             "blood_test: Vitamin D=15 ng/mL",
#             "wearable: sleep_hours",
#             "feedback: energy=low"
#         ],
#         validation_flags=[]
#     )
#     print(build_concise_explanation(test_rec))
#     print(build_structured_explanation(test_rec))