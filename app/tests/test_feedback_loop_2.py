from pathlib import Path
import datetime
import pytest
from app.feedback_loop import (
    update_nutrient_scores_with_feedback,
    label_recommendations_with_feedback,
    detect_trend,
    log_dose_response
)
from app.data_model import UserProfile, SupplementRecommendation
from typing import Dict

# Helper factory for user with feedback and optional symptom history
def make_user_with_feedback(symptom_changes: Dict[str, str], preseed_history=None) -> UserProfile:
    # Normalize feedback statuses to match internal representation
    def normalize_status(status):
        status = status.lower()
        if status in ["worse", "worsened"]:
            return "worsening"
        elif status in ["better", "improved"]:
            return "improving"
        elif status == "same":
            return "same"
        return status

    normalized_changes = {k: normalize_status(v) for k, v in symptom_changes.items()}

    user = UserProfile(
        user_id="testuser",
        age=30,
        gender="female",
        symptoms=list(normalized_changes.keys()),
        medical_conditions=[],
        blood_tests=[],
        wearable_data=None,
        feedback=None,
        symptom_history=preseed_history or {}
    )
    user.feedback = type("Feedback", (), {"symptom_changes": normalized_changes})
    return user

def test_update_nutrient_scores_with_feedback():
    # Patch symptom-nutrient map for test
    from symptom_scorer import SYMPTOM_NUTRIENT_MAP
    SYMPTOM_NUTRIENT_MAP["fatigue"] = ["iron", "magnesium"]

    today = datetime.date.today().isoformat()
    # Preseed symptom history with 3 worsening statuses to trigger trend detection
    preseed = {
        "fatigue": [
            {"date": today, "status": "worsening"},
            {"date": today, "status": "worsening"},
            {"date": today, "status": "worsening"},
        ]
    }

    user = make_user_with_feedback({"fatigue": "worsened"}, preseed_history=preseed)
    nutrient_scores = {"iron": 0.5, "magnesium": 0.5, "vitamin_d": 0.5}

    updated_scores = update_nutrient_scores_with_feedback(user, nutrient_scores)

    # Scores for iron and magnesium should increase by 0.2 (worsening trend)
    assert updated_scores["iron"] == pytest.approx(0.7)
    assert updated_scores["magnesium"] == pytest.approx(0.7)
    assert updated_scores["vitamin_d"] == pytest.approx(0.5)  # unchanged

def test_detect_trend_basic():
    today = datetime.date.today().isoformat()

    history = {
        "fatigue": [
            {"date": today, "status": "worsening"},
            {"date": today, "status": "worsening"},
            {"date": today, "status": "worsening"},
        ],
        "headache": [
            {"date": today, "status": "improving"},
            {"date": today, "status": "improving"},
            {"date": today, "status": "improving"},
        ],
        "nausea": [
            {"date": today, "status": "same"},
            {"date": today, "status": "same"},
            {"date": today, "status": "same"},
        ],
        "insomnia": [
            {"date": today, "status": "worsening"},
            {"date": today, "status": "improving"},
            {"date": today, "status": "same"},
        ]  # Mixed - no trend
    }

    trends = detect_trend(history)
    assert trends["fatigue"] == "worsening"
    assert trends["headache"] == "improving"
    assert trends["nausea"] == "stagnant"
    assert "insomnia" not in trends

def test_log_dose_response_adds_entries():
    user = make_user_with_feedback({})
    # Add mock recommendations
    rec1 = SupplementRecommendation(
        name="Vitamin C",
        dosage=500,
        unit="mg",
        reason=None,
        triggered_by=["fatigue"],
        contraindications=[],
        inputs_triggered=[],
        validation_flags=[]
    )
    rec2 = SupplementRecommendation(
        name="Magnesium",
        dosage=300,
        unit="mg",
        reason=None,
        triggered_by=["headache"],
        contraindications=[],
        inputs_triggered=[],
        validation_flags=[]
    )
    user.recommendations = [rec1, rec2]
    user.feedback.symptom_changes = {"fatigue": "better", "headache": "worse"}

    user.dose_response_log = []
    log_dose_response(user)

    assert len(user.dose_response_log) == 2
    assert user.dose_response_log[0].supplement == "Vitamin C"
    assert user.dose_response_log[0].outcome.get("fatigue") == "better"
    assert user.dose_response_log[1].supplement == "Magnesium"
    assert user.dose_response_log[1].outcome.get("headache") == "worse"

def test_label_recommendations_with_feedback_flags():
    user = make_user_with_feedback({"fatigue": "improved", "headache": "worsened", "nausea": "same"})
    rec1 = SupplementRecommendation(
        name="Iron",
        dosage=30,
        unit="mg",
        reason=None,
        triggered_by=["fatigue"],
        contraindications=[],
        inputs_triggered=[],
        validation_flags=[]
    )
    rec2 = SupplementRecommendation(
        name="Magnesium",
        dosage=400,
        unit="mg",
        reason=None,
        triggered_by=["headache"],
        contraindications=[],
        inputs_triggered=[],
        validation_flags=[]
    )
    rec3 = SupplementRecommendation(
        name="Vitamin C",
        dosage=500,
        unit="mg",
        reason=None,
        triggered_by=["nausea"],
        contraindications=[],
        inputs_triggered=[],
        validation_flags=[]
    )

    recs = [rec1, rec2, rec3]
    labeled_recs = label_recommendations_with_feedback(user, recs)

    assert "✅ User reported improvement" in labeled_recs[0].validation_flags
    assert "⚠️ Symptom worsened" in labeled_recs[1].validation_flags
    assert "ℹ️ No change reported" in labeled_recs[2].validation_flags

    # Use fresh instances to test no feedback case with cleared flags
    rec1_nf = SupplementRecommendation(**rec1.__dict__)
    rec1_nf.validation_flags = []
    rec2_nf = SupplementRecommendation(**rec2.__dict__)
    rec2_nf.validation_flags = []
    rec3_nf = SupplementRecommendation(**rec3.__dict__)
    rec3_nf.validation_flags = []
    recs_nf = [rec1_nf, rec2_nf, rec3_nf]

    user_no_feedback = make_user_with_feedback({})
    unlabeled = label_recommendations_with_feedback(user_no_feedback, recs_nf)
    for rec in unlabeled:
        assert rec.validation_flags == []