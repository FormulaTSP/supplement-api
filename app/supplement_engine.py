# app/supplement_engine.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from app.data_model import UserProfile
from app.llm_planner import plan_with_llm


class PlanningError(Exception):
    pass


def _coerce_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def generate_supplement_plan(
    user: UserProfile,
    grocery_context: Optional[List[Dict[str, Any]]] = None,
    grocery_nutrients: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Single entry point called by the API. Fully LLM-driven.
    Returns a dict with:
      - user_id
      - recommendations (supplements, normalized to our typical shape)
      - grocery_recommendations (pass-through from LLM)
      - recipes (pass-through from LLM)
      - rebalance_timeframe (string)
      - confidence_score
      - cluster_id = None
    """
    try:
        # Try new planner signature first (with grocery context)
        try:
            data = plan_with_llm(
                user=user,
                max_supps=6,
                max_groceries=10,
                max_recipes=3,
                temperature=0.2,
                grocery_context=grocery_context,
                grocery_nutrients=grocery_nutrients,
            )
        except TypeError:
            # Deployed planner might be older; retry without the new kwargs
            data = plan_with_llm(
                user=user,
                max_supps=6,
                max_groceries=10,
                max_recipes=3,
                temperature=0.2,
            )
    except Exception as e:
        raise PlanningError(f"LLM planning failed: {e}")

    # Normalize supplements to our familiar output shape
    out_recs: List[Dict[str, Any]] = []
    for item in data.get("recommendations", []):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        dosage = _coerce_float(item.get("dosage", 0))
        unit = str(item.get("unit", "")).strip()
        reason = (str(item.get("reason") or "").strip()) or None
        triggered_by = item.get("triggered_by") or []
        contraindications = item.get("contraindications") or []
        inputs_triggered = item.get("inputs_triggered") or []

        out_recs.append({
            "name": name,
            "dosage": round(dosage, 2),
            "unit": unit,
            "reason": reason,
            "triggered_by": [str(x) for x in triggered_by],
            "contraindications": [str(x) for x in contraindications],
            "inputs_triggered": [str(x) for x in inputs_triggered],
            "source": "llm",
            "validation_flags": [],
            "explanation": reason,
        })

    return {
        "user_id": user.user_id,
        "recommendations": out_recs,
        "grocery_recommendations": data.get("grocery_recommendations", []),
        "recipes": data.get("recipes", []),
        "rebalance_timeframe": data.get("rebalance_timeframe", ""),
        "confidence_score": 0.9,
        "cluster_id": None,
    }