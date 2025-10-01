# app/llm_planner.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os
import json
import re

from openai import OpenAI

from app.data_model import UserProfile, SupplementRecommendation
from app.supplement_utils import load_supplement_db
from app.unit_converter import normalize_blood_test_marker


def _strip_code_fence(text: str) -> str:
    if not isinstance(text, str):
        return text
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\n?", "", t)
        t = re.sub(r"\n```$", "", t)
    return t


def _compact_user(user: UserProfile) -> Dict[str, Any]:
    # Normalize blood tests to standard units
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


def _supplement_catalog() -> List[Dict[str, Any]]:
    db = load_supplement_db()
    catalog = []
    for key, meta in db.items():
        catalog.append({
            "key": key,
            "name": meta.get("name"),
            "unit": meta.get("unit"),
            "rda_by_gender_age": meta.get("rda_by_gender_age", {}),
            "optimal_range": meta.get("optimal_range", []),
            "upper_limit": meta.get("upper_limit", None),
            "contraindications": meta.get("contraindications", []),
            "interactions": meta.get("interactions", []),
        })
    return catalog


def _build_messages(user: UserProfile, max_recs: int, cluster_hints: Optional[List[SupplementRecommendation]]) -> List[Dict[str, str]]:
    user_payload = _compact_user(user)
    catalog = _supplement_catalog()

    hints = []
    if cluster_hints:
        for rec in cluster_hints[:5]:
            hints.append({
                "name": rec.name,
                "dosage": rec.dosage,
                "unit": rec.unit,
                "reason": rec.reason or "cluster protocol"
            })

    system = (
        "You are a clinical-grade supplement planning assistant. "
        "You must propose a safe, personalized supplement plan based only on the allowed catalog provided. "
        "Never invent supplements not present in the catalog. "
        "Respect units and do not exceed upper_limit for any supplement. "
        "Avoid contraindications based on medical_history/medical_conditions. "
        "Consider potential interactions with the user's medications and between supplements (catalog provides interactions). "
        "Prefer simpler plans with fewer items. Provide clear reasons. Output strict JSON only."
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
                        "inputs_triggered": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "dosage", "unit", "reason"],
                },
            },
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["recommendations"],
    }

    user_msg = {
        "role": "user",
        "content": (
            "Return a JSON object matching this schema (no prose, no code fences).\n"
            f"Max items: {max_recs}.\n"
            "Use only supplements from 'catalog'.\n"
            "If a useful plan item would exceed upper_limit, cap at upper_limit and mention in reason.\n"
            "If an item is contraindicated, do not include it.\n"
            "If the user is on meds that interact with an item (see catalog.interactions), prefer alternatives or mention risk in reason.\n\n"
            f"schema: {json.dumps(schema_hint)}\n\n"
            f"catalog: {json.dumps(catalog)}\n\n"
            f"user: {json.dumps(user_payload)}\n\n"
            f"cluster_hints (optional): {json.dumps(hints)}\n"
        ),
    }

    return [
        {"role": "system", "content": system},
        user_msg,
    ]


def _coerce_json(text: str) -> Dict[str, Any]:
    t = _strip_code_fence(text)
    try:
        return json.loads(t)
    except Exception:
        # Try to find the first JSON object in the text
        m = re.search(r"\{[\s\S]*\}$", t)
        if m:
            return json.loads(m.group(0))
        raise


def plan_with_llm(
    user: UserProfile,
    cluster_hints: Optional[List[SupplementRecommendation]] = None,
    model: Optional[str] = None,
    max_recs: int = 8,
    temperature: float = 0.1,
) -> List[SupplementRecommendation]:
    """
    Use an LLM to propose a supplement plan. Returns a list of SupplementRecommendation.
    The caller should still run safety validations and interaction checks afterwards.
    """
    model = model or os.getenv("LLM_PLANNER_MODEL", "gpt-4o-mini")
    client = OpenAI()

    messages = _build_messages(user, max_recs, cluster_hints)

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1500,
    )

    content = resp.choices[0].message.content or "{}"
    data = _coerce_json(content)

    recs_out: List[SupplementRecommendation] = []

    # Build lookup from supplement_db by normalized name
    allowed_by_name = {}
    for meta in load_supplement_db().values():
        nm = (meta.get("name") or "").lower().strip()
        if nm:
            allowed_by_name[nm] = meta

    for item in (data.get("recommendations") or []):
        raw_name = str(item.get("name", "")).strip()
        if not raw_name:
            continue
        meta = allowed_by_name.get(raw_name.lower())
        if not meta:
            # Try removing spaces and matching
            key = next((k for k in allowed_by_name.keys() if k.replace(" ", "") == raw_name.lower().replace(" ", "")), None)
            meta = allowed_by_name.get(key) if key else None
        if not meta:
            continue  # skip unknown item

        unit = meta.get("unit", "")
        try:
            dosage = float(item.get("dosage", 0))
        except Exception:
            dosage = 0.0

        upper = meta.get("upper_limit")
        if isinstance(upper, (int, float)) and upper is not None:
            if dosage > float(upper):
                dosage = float(upper)

        reason = str(item.get("reason", "")).strip() or None
        inputs_triggered = item.get("inputs_triggered") or []

        rec = SupplementRecommendation(
            name=meta.get("name"),
            dosage=round(dosage, 2),
            unit=unit,
            reason=reason,
            triggered_by=user.symptoms or [],
            contraindications=meta.get("contraindications", []),
            inputs_triggered=[str(x) for x in inputs_triggered],
            source="llm",
        )
        rec.explanation = reason
        recs_out.append(rec)

    return recs_out