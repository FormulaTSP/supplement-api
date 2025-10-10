# app/llm_planner.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, json, re

from openai import OpenAI

from app.data_model import UserProfile, SupplementRecommendation
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


def _build_messages(user: UserProfile, max_recs: int) -> List[Dict[str, str]]:
    """No catalog provided. The LLM is fully authoritative."""
    user_payload = _compact_user(user)

    system = (
        "You are a clinical supplement planning assistant. "
        "Create a concise, personalized supplement plan for the user based on their profile. "
        "You are fully responsible for choosing items and dosages. "
        "Output STRICT JSON only (no prose, no code fences)."
    )

    schema_hint = {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "dosage": {"type": "number"},
                        "unit": {"type": "string"},
                        "reason": {"type": "string"},
                        # optional, if the model wants to include them:
                        "triggered_by": {"type": "array", "items": {"type": "string"}},
                        "contraindications": {"type": "array", "items": {"type": "string"}},
                        "inputs_triggered": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "array", "items": {"type": "string"}},
                        "warnings": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "dosage", "unit", "reason"],
                },
            }
        },
        "required": ["recommendations"],
    }

    user_msg = {
        "role": "user",
        "content": (
            "Return ONLY a JSON object matching this schema. No prose. No code fences.\n"
            f"Max items: {max_recs}.\n"
            "If you consider risks/contraindications/medication interactions relevant, include them in your own fields.\n\n"
            f"schema: {json.dumps(schema_hint)}\n\n"
            f"user: {json.dumps(user_payload)}\n"
        ),
    }

    return [{"role": "system", "content": system}, user_msg]


def plan_with_llm(
    user: UserProfile,
    model: Optional[str] = None,
    max_recs: int = 8,
    temperature: float = 0.2,
) -> List[SupplementRecommendation]:
    """
    PURE LLM planner:
      - No catalog, no backend constraints.
      - The model decides names, dosages, units, reasons, and any metadata fields.
      - We only coerce the model's JSON into SupplementRecommendation objects.
    """
    model = model or os.getenv("LLM_PLANNER_MODEL", "gpt-4o-mini")
    client = OpenAI()
    messages = _build_messages(user, max_recs)

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1500,
    )
    content = resp.choices[0].message.content or "{}"
    data = _coerce_json(content)

    out: List[SupplementRecommendation] = []
    for item in (data.get("recommendations") or []):
        # Pull fields directly from the model output; be permissive.
        name = str(item.get("name", "")).strip()
        if not name:
            continue

        # dosage is free-form from the model
        try:
            dosage = float(item.get("dosage", 0))
        except Exception:
            dosage = 0.0

        unit = str(item.get("unit", "")).strip()
        reason = (str(item.get("reason") or "").strip()) or None

        triggered_by = item.get("triggered_by") or []
        contraindications = item.get("contraindications") or []
        inputs_triggered = item.get("inputs_triggered") or []

        rec = SupplementRecommendation(
            name=name,
            dosage=round(dosage, 2),
            unit=unit,
            reason=reason,
            triggered_by=[str(x) for x in triggered_by],
            contraindications=[str(x) for x in contraindications],
            inputs_triggered=[str(x) for x in inputs_triggered],
            source="llm",
        )
        # Keep explanation aligned with the model’s reason.
        rec.explanation = reason
        out.append(rec)

    return out