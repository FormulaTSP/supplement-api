from typing import List, Optional

from app.data_model import UserProfile, SupplementRecommendation, RecommendationOutput
from app.feedback_loop import label_recommendations_with_feedback
from app.safety_checks import validate_recommendations
from app.drug_interaction_checker import attach_interaction_flags
from app.llm_planner import plan_with_llm


class PlanningError(Exception):
    """Raised when the LLM-based planning fails."""
    pass


def generate_supplement_plan(
    user: UserProfile,
    cluster_engine: Optional[object] = None,  # kept for signature compatibility; unused
    structured_output: bool = False,
) -> RecommendationOutput:
    """
    Generate a supplement plan exclusively via the LLM planner, then apply
    post-processing safeguards. No rule-based or clustering logic is used.
    """
    try:
        # LLM is now the sole planning engine; no cluster hints are used
        recommendations: List[SupplementRecommendation] = plan_with_llm(user, cluster_hints=None)
    except Exception as e:
        # Surface a clear error so API can respond appropriately
        raise PlanningError(f"LLM planning failed: {e}")

    # Post-processing: feedback labels, safety validation, and interaction flags
    recommendations = label_recommendations_with_feedback(user, recommendations)
    recommendations = validate_recommendations(user, recommendations)
    recommendations = attach_interaction_flags(user, recommendations)

    # Confidence is uniform now that clustering fallback is removed
    return RecommendationOutput(
        user_id=user.user_id,
        recommendations=recommendations,
        confidence_score=0.9,
        cluster_id=None,
    )