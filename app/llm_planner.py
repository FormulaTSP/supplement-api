# app/llm_planner.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, json, re

from openai import OpenAI

from app.data_model import UserProfile
from app.unit_converter import normalize_blood_test_marker


def _strip_code_fence(text: str) -> str:
    if not isinstance(text, str):
        return text
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\n?", "", t)
        t = re.sub(r"\n```$", "", t)
    return t


def _coerce_json(text: str) -> Dict[str, Any]:
    t = _strip_code_fence(text)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            return json.loads(m.group(0))
        raise


def _compact_user(user: UserProfile) -> Dict[str, Any]:
    """Compact user profile for the LLM; include helpful signal but no backend-imposed rules."""
    blood_tests = []
    for bt in (user.blood_tests or []):
        try:
            marker, value, unit = normalize_blood_test_marker(bt.marker, bt.value, bt.unit)
            blood_tests.append({"marker": marker, "value": value, "unit": unit})
        except Exception:
            blood_tests.append({"marker": bt.marker, "value": bt.value, "unit": bt.unit})

    wearable = None
    if user.wearable_data:
        wearable = {
            "sleep_hours": user.wearable_data.sleep_hours,
            "hrv": user.wearable_data.hrv,
            "resting_hr": user.wearable_data.resting_hr,
            "activity_level": user.wearable_data.activity_level,
            "temperature_variation": user.wearable_data.temperature_variation,
            "spo2": user.wearable_data.spo2,
            "sunlight_exposure_minutes": user.wearable_data.sunlight_exposure_minutes,
        }

    return {
        "user_id": user.user_id,
        "age": user.age,
        "gender": user.gender,
        "symptoms": user.symptoms or [],
        "goals": user.goals or [],
        "medical_history": user.medical_history or {},
        "medical_conditions": user.medical_conditions or [],
        "medications": user.medications or [],
        "lifestyle": user.lifestyle or {},
        "blood_tests": blood_tests,
        "wearable_data": wearable,
        "feedback": {
            "mood": getattr(user.feedback, "mood", None) if user.feedback else None,
            "energy": getattr(user.feedback, "energy", None) if user.feedback else None,
            "stress": getattr(user.feedback, "stress", None) if user.feedback else None,
            "symptoms": getattr(user.feedback, "symptoms", []) if user.feedback else [],
            "symptom_changes": getattr(user.feedback, "symptom_changes", {}) if user.feedback else {},
        },
    }


def _build_messages(user: UserProfile, max_supps: int, max_groceries: int, max_recipes: int) -> List[Dict[str, str]]:
    """
    Single-call, fully LLM-driven plan (supplements + groceries + recipes + timeframe).
    No catalogs, no caps, no backend guardrails. Output STRICT JSON.
    """
    user_payload = _compact_user(user)

    system = (
        "You are a clinical-grade nutrition & supplement planning assistant. "
        "Create a concise, personalized plan consisting of: "
        "(1) supplements, (2) grocery items (specific foods), (3) recipes (ingredients + steps), and (4) a single-string timeframe "
        "for how long it may take to restore nutritional balance. "
        "You are fully responsible for item choices and dosages. "
        "Return STRICT JSON only (no prose, no code fences)."
    )

    schema_hint = {
        "type": "object",
        "properties": {
            "rebalance_timeframe": {"type": "string"},
            "recommendations": {
                "type": "array",
                "description": "Supplements",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "dosage": {"type": "number"},
                        "unit": {"type": "string"},
                        "reason": {"type": "string"},
                        "triggered_by": {"type": "array", "items": {"type": "string"}},
                        "contraindications": {"type": "array", "items": {"type": "string"}},
                        "inputs_triggered": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["name", "dosage", "unit", "reason"]
                }
            },
            "grocery_recommendations": {
                "type": "array",
                "description": "Specific foods to buy and eat more often",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "reason": {"type": "string"}
                    },
                    "required": ["name"]
                }
            },
            "recipes": {
                "type": "array",
                "description": "Recipes that use the recommended foods",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "ingredients": {"type": "array", "items": {"type": "string"}},
                        "instructions": {"type": "array", "items": {"type": "string"}},
                        "nutritional_focus": {"type": "array", "items": {"type": "string"}},
                        "estimated_time_minutes": {"type": "number"}
                    },
                    "required": ["title", "ingredients", "instructions"]
                }
            }
        },
        "required": ["recommendations", "grocery_recommendations", "recipes", "rebalance_timeframe"]
    }

    user_msg = {
        "role": "user",
        "content": (
            "Return ONLY a JSON object matching this schema. No prose. No code fences.\n"
            f"Max supplements: {max_supps}. Max groceries: {max_groceries}. Max recipes: {max_recipes}.\n"
            "Supplements and foods should be aligned with the user's needs and goals. "
            "Recipes should largely use the grocery items you recommend.\n\n"
            f"schema: {json.dumps(schema_hint)}\n\n"
            f"user: {json.dumps(user_payload)}\n"
        ),
    }

    return [{"role": "system", "content": system}, user_msg]


def plan_with_llm(
    user: UserProfile,
    model: Optional[str] = None,
    max_supps: int = 6,
    max_groceries: int = 10,
    max_recipes: int = 3,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    PURE LLM planner in one call:
      - Supplements (recommendations)
      - Grocery items (grocery_recommendations)
      - Recipes (recipes)
      - Rebalance timeframe (rebalance_timeframe: string)
    Returns the raw parsed dict. No server-side guardrails.
    """
    model = model or os.getenv("LLM_PLANNER_MODEL", "gpt-4o-mini")
    client = OpenAI()
    messages = _build_messages(user, max_supps, max_groceries, max_recipes)

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1800,
    )
    content = resp.choices[0].message.content or "{}"
    data = _coerce_json(content)

    # Ensure keys exist to keep the rest of the pipeline simple
    data.setdefault("recommendations", [])
    data.setdefault("grocery_recommendations", [])
    data.setdefault("recipes", [])
    data.setdefault("rebalance_timeframe", "")

    return data