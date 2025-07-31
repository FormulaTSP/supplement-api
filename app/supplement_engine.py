from pathlib import Path
from typing import List
import os

from app.data_model import UserProfile, SupplementRecommendation, RecommendationOutput
from app.symptom_scorer import score_nutrient_needs
from app.feedback_loop import label_recommendations_with_feedback
from app.dosage_calculator import determine_dosage
from app.wearable_middleware import WearableMiddleware
from app.cluster_engine import ClusterEngine
from app.safety_checks import validate_recommendations
from app.supplement_utils import get_supplement_data
from app.drug_interaction_checker import attach_interaction_flags
from app.explanation_utils import build_explanation, build_structured_explanation
from app.unit_converter import normalize_blood_test_marker  # ✅ NEW

cluster_engine = ClusterEngine(n_clusters=5)
MIN_CLUSTER_SIZE = 3
MAX_DISTANCE_THRESHOLD = 1.0

def generate_supplement_plan(
    user: UserProfile,
    cluster_engine: ClusterEngine = cluster_engine,
    structured_output: bool = False
) -> RecommendationOutput:
    recommendations = []

    if user.cluster_id is not None and cluster_engine.fitted:
        try:
            cluster_users = [u for u in cluster_engine.all_users if u.cluster_id == user.cluster_id]
            cluster_size = len(cluster_users)
            dist_to_centroid = cluster_engine.distance_to_centroid(user)

            if cluster_size >= MIN_CLUSTER_SIZE and dist_to_centroid <= MAX_DISTANCE_THRESHOLD:
                protocol = cluster_engine.get_cluster_protocol(user.cluster_id)
                if protocol:
                    print(f"[Info] Using cluster protocol for cluster {user.cluster_id} (size={cluster_size}, dist={dist_to_centroid:.3f})")
                    recommendations = []
                    for rec in protocol:
                        explanation = build_explanation(rec)  # Add explanation for cluster recs
                        structured_exp = build_structured_explanation(rec) if structured_output else None
                        new_rec = SupplementRecommendation(
                            name=rec.name,
                            dosage=rec.dosage,
                            unit=rec.unit,
                            reason=rec.reason,
                            triggered_by=user.symptoms,
                            contraindications=rec.contraindications,
                            inputs_triggered=[],
                            source="cluster",
                            explanation=explanation,
                        )
                        if structured_output:
                            setattr(new_rec, 'structured_explanation', structured_exp)
                        recommendations.append(new_rec)
        except Exception as e:
            print(f"[Warning] Cluster fallback error: {e}")

    if not recommendations:
        scores = score_nutrient_needs(user)
        middleware = WearableMiddleware()

        if user.blood_tests:
            # Normalize units first
            normalized_blood_tests = [
                normalize_blood_test_marker(bt.marker, bt.value, bt.unit)
                for bt in user.blood_tests
            ]
            blood_data = {marker.lower(): value for marker, value, unit in normalized_blood_tests}
            middleware.integrate_blood_test(blood_data)

        wearable_inputs = {}
        if user.wearable_data:
            wearable_inputs = {
                "sleep_hours": user.wearable_data.sleep_hours,
                "hrv": user.wearable_data.hrv,
                "resting_hr": user.wearable_data.resting_hr,
                "activity_level": user.wearable_data.activity_level,
                "temperature_variation": user.wearable_data.temperature_variation,
                "spo2": user.wearable_data.spo2,
                "sunlight_exposure_minutes": user.wearable_data.sunlight_exposure_minutes,
            }
            middleware.normalize_data(wearable_inputs, source="apple_health")

        for nutrient, need_score in scores.items():
            if need_score > 0:
                dose, unit, contraindications = determine_dosage(
                    nutrient,
                    need_score,
                    user,
                    bypass_upper_limit=(os.getenv("TESTING") == "1")
                )
                if dose > 0:
                    inputs_triggered = []
                    inputs_triggered += [f"symptom: {s}" for s in user.symptoms]
                    inputs_triggered += [f"goal: {g}" for g in user.goals]
                    inputs_triggered += [f"medical_history: {k}" for k in user.medical_history.keys()]

                    for k, v in wearable_inputs.items():
                        if v is not None:
                            inputs_triggered.append(f"wearable: {k}")

                    if user.feedback:
                        if user.feedback.energy:
                            inputs_triggered.append(f"feedback: energy={user.feedback.energy}")
                        if user.feedback.mood:
                            inputs_triggered.append(f"feedback: mood={user.feedback.mood}")
                        if user.feedback.stress:
                            inputs_triggered.append(f"feedback: stress={user.feedback.stress}")
                        for sym in user.feedback.symptoms:
                            inputs_triggered.append(f"feedback symptom: {sym}")

                    if user.blood_tests:
                        for bt in user.blood_tests:
                            if nutrient.lower() in bt.marker.lower():
                                inputs_triggered.append(f"blood_test: {bt.marker}={bt.value} {bt.unit}")

                    rec = SupplementRecommendation(
                        name=nutrient,
                        dosage=dose,
                        unit=unit,
                        reason=f"Need score: {need_score:.3f}",
                        triggered_by=user.symptoms,
                        contraindications=contraindications,
                        inputs_triggered=inputs_triggered,
                        source="rule-based"
                    )

                    # Build concise explanation (default)
                    rec.explanation = build_explanation(rec)

                    # Optionally build structured explanation for frontend/API
                    if structured_output:
                        rec.structured_explanation = build_structured_explanation(rec)

                    if os.getenv("TESTING") == "1":
                        supp_data = get_supplement_data(nutrient)
                        upper_limit = supp_data.get("upper_limit")
                        if upper_limit and dose > upper_limit:
                            print(f"[TESTING] {nutrient}: dose={dose} > upper_limit={upper_limit}")
                            rec.validation_flags.append("⚠️ Exceeds upper limit")

                    recommendations.append(rec)

    recommendations = label_recommendations_with_feedback(user, recommendations)
    recommendations = validate_recommendations(user, recommendations)
    recommendations = attach_interaction_flags(user, recommendations)

    return RecommendationOutput(
        user_id=user.user_id,
        recommendations=recommendations,
        confidence_score=1.0 if user.cluster_id is not None and cluster_engine.fitted else 0.7
    )