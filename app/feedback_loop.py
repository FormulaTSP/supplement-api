# feedback_loop.py

import datetime
from typing import Dict, List
from app.data_model import UserProfile, DoseResponseEntry, SupplementRecommendation
from app.symptom_scorer import SYMPTOM_NUTRIENT_MAP

TREND_WINDOW = 3  # Number of feedback points to evaluate trend


# 🔁 === Core Learning Engine ===
def update_nutrient_scores_with_feedback(user: UserProfile, nutrient_scores: Dict[str, float]) -> Dict[str, float]:
    """
    Adjust nutrient scores based on symptom feedback trends.
    This is part of the learning/feedback loop.
    """
    today = datetime.date.today().isoformat()
    symptom_changes = user.feedback.symptom_changes if user.feedback and user.feedback.symptom_changes else {}

    if not user.symptom_history:
        user.symptom_history = {}

    # Append current feedback to symptom history
    for symptom, status in symptom_changes.items():
        normalized_status = normalize_status(status)
        if symptom not in user.symptom_history:
            user.symptom_history[symptom] = []
        user.symptom_history[symptom].append({"date": today, "status": normalized_status})

    # Detect trends in feedback
    trends = detect_trend(user.symptom_history)

    # Adjust nutrient scores based on trends
    for symptom, trend in trends.items():
        nutrients = SYMPTOM_NUTRIENT_MAP.get(symptom.lower(), [])
        for nutrient in nutrients:
            if trend == "worsening":
                nutrient_scores[nutrient] = nutrient_scores.get(nutrient, 0) + 0.2
            elif trend == "improving":
                nutrient_scores[nutrient] = max(nutrient_scores.get(nutrient, 0) - 0.1, 0)
            elif trend == "stagnant":
                nutrient_scores[nutrient] = nutrient_scores.get(nutrient, 0) + 0.05

    log_dose_response(user)
    return nutrient_scores


def detect_trend(history: Dict[str, list]) -> Dict[str, str]:
    """
    Detect symptom trend based on last TREND_WINDOW statuses.
    Returns a dict of symptom -> trend ("worsening", "improving", "stagnant").
    """
    trends = {}
    for symptom, entries in history.items():
        if len(entries) < TREND_WINDOW:
            continue
        last_statuses = [entry["status"] for entry in entries[-TREND_WINDOW:]]
        if all(s == "worsening" for s in last_statuses):
            trends[symptom] = "worsening"
        elif all(s == "improving" for s in last_statuses):
            trends[symptom] = "improving"
        elif all(s == "same" for s in last_statuses):
            trends[symptom] = "stagnant"
    return trends


def log_dose_response(user: UserProfile):
    """
    Logs the user's dose response entries based on current recommendations and feedback.
    """
    today = datetime.date.today().isoformat()
    feedback_changes = user.feedback.symptom_changes if user.feedback else {}

    if not hasattr(user, "dose_response_log") or user.dose_response_log is None:
        user.dose_response_log = []

    if not hasattr(user, "recommendations") or not user.recommendations:
        return

    for rec in user.recommendations:
        entry = DoseResponseEntry(
            date=today,
            supplement=rec.name,
            dose=rec.dosage,
            unit=rec.unit,
            symptoms_targeted=rec.triggered_by or [],
            outcome={symptom: feedback_changes.get(symptom, "unknown")
                     for symptom in rec.triggered_by or []}
        )
        user.dose_response_log.append(entry)


# Helper to normalize different feedback status strings
def normalize_status(status: str) -> str:
    status = status.lower()
    if status in ["worse", "worsened"]:
        return "worsening"
    elif status in ["better", "improved"]:
        return "improving"
    elif status == "same":
        return "same"
    return status  # fallback to original if unknown


# 🆕 === UI / Display Only: Adds flags for explanations ===
def label_recommendations_with_feedback(user: UserProfile, recs: List[SupplementRecommendation]) -> List[SupplementRecommendation]:
    """
    Adds user-friendly feedback flags to supplement recommendations.
    This is for display purposes — does not alter logic or scoring.
    """
    if not user.feedback or not user.feedback.symptom_changes:
        return recs

    symptom_changes = user.feedback.symptom_changes
    for rec in recs:
        for symptom, change in symptom_changes.items():
            normalized = normalize_status(change)
            if normalized == "improving":
                flag = "✅ User reported improvement"
            elif normalized == "worsening":
                flag = "⚠️ Symptom worsened"
            elif normalized == "same":
                flag = "ℹ️ No change reported"
            else:
                continue

            if symptom.lower() in [s.lower() for s in rec.triggered_by]:
                rec.validation_flags.append(flag)

    return recs