# app/supplement_engine.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from collections import defaultdict

from app.data_model import UserProfile
from app.llm_planner import plan_with_llm


class PlanningError(Exception):
    pass


def _coerce_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


# Very small heuristic if LLM omits nutrient_tags
_KEYWORD_TO_NUTRIENTS: List[tuple] = [
    # Omega-3
    (("salmon", "mackerel", "sardine", "anchovy", "trout", "herring", "tuna", "chia", "flax", "walnut"), ["Omega-3"]),
    # Iron
    (("spinach", "kale", "beef", "liver", "lentil", "lentils", "black bean", "kidney bean", "chickpea"), ["Iron"]),
    # Calcium
    (("milk", "yogurt", "yoghurt", "cheese", "kefir"), ["Calcium"]),
    # Magnesium
    (("almond", "pumpkin seed", "pumpkin seeds", "cashew", "spinach", "quinoa", "oats", "dark chocolate"), ["Magnesium"]),
    # Vitamin D
    (("salmon", "mackerel", "sardine", "cod liver", "fortified milk", "fortified"), ["Vitamin D"]),
    # Potassium
    (("banana", "bananas", "potato", "sweet potato", "avocado", "spinach", "beans", "yogurt"), ["Potassium"]),
    # Fiber
    (("oats", "oat", "berries", "chickpea", "lentil", "beans", "whole grain", "quinoa", "broccoli", "apple"), ["Fiber"]),
    # Zinc
    (("oyster", "beef", "pumpkin seed", "pumpkin seeds", "cashew"), ["Zinc"]),
]


def _infer_nutrient_tags_from_name(name: str) -> List[str]:
    n = (name or "").lower()
    tags: List[str] = []
    for keywords, taglist in _KEYWORD_TO_NUTRIENTS:
        if any(k in n for k in keywords):
            for t in taglist:
                if t not in tags:
                    tags.append(t)
    return tags


def _group_groceries_by_nutrient(grocery_recs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns a dict: nutrient -> list of {name, reason}
    Uses LLM-provided 'nutrient_tags' when present; otherwise falls back to keyword inference.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    seen = set()

    for rec in grocery_recs or []:
        name = rec.get("name")
        if not name:
            continue
        reason = rec.get("reason")
        tags = rec.get("nutrient_tags") or _infer_nutrient_tags_from_name(name)

        for tag in tags or []:
            key = (tag, name)
            if key in seen:
                continue
            seen.add(key)
            groups[tag].append({"name": name, "reason": reason})

    # Convert defaultdict to normal dict for JSON
    return {k: v for k, v in groups.items()}


def generate_supplement_plan(
    user: UserProfile,
    grocery_context: Optional[List[Dict[str, Any]]] = None,
    grocery_nutrients: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Single entry point called by the API. Fully LLM-driven.
    Returns a dict with:
      - user_id
      - recommendations (supplements, normalized)
      - grocery_recommendations (LLM output, plus nutrient_tags if provided by LLM)
      - recipes
      - rebalance_timeframe
      - grocery_by_nutrient  <-- NEW for frontend grouping
      - confidence_score
      - cluster_id = None
    """
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

    grocery_recs = data.get("grocery_recommendations", []) or []
    grocery_by_nutrient = _group_groceries_by_nutrient(grocery_recs)

    return {
        "user_id": user.user_id,
        "recommendations": out_recs,
        "grocery_recommendations": grocery_recs,
        "recipes": data.get("recipes", []),
        "rebalance_timeframe": data.get("rebalance_timeframe", ""),
        "grocery_by_nutrient": grocery_by_nutrient,  # <-- new field for your UI
        "confidence_score": 0.9,
        "cluster_id": None,
    }