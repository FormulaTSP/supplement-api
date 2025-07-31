import os
from typing import Tuple, List, Optional
from app.data_model import UserProfile
from app.supplement_utils import determine_dosage_from_db

def determine_dosage(
    nutrient: str,
    need_score: float,
    user: UserProfile,
    other_supplements: Optional[List[str]] = None,
    bypass_upper_limit: bool = False  # ✅ Explicitly added
) -> Tuple[float, str, List[str]]:
    """
    Determines personalized dosage for a nutrient.
    Returns: (dosage, unit, [contraindications or notes])
    """
    other_supplements = other_supplements or []

    # Custom logic: restrict Iron for males without strong justification
    if nutrient.lower() == "iron" and user.gender == "male":
        if user.blood_tests:
            ferritin_low = any(
                ("ferritin" in bt.marker.lower() or "iron" in bt.marker.lower())
                and bt.value < 60
                for bt in user.blood_tests
            )
            if not ferritin_low:
                return 0.0, "mg", ["❌ Male without iron deficiency (labs normal)"]
        else:
            if need_score < 0.9:
                return 0.0, "mg", ["❌ Male without labs and low symptom score"]

    # ✅ Core dosage logic from DB
    dosage, unit, contraindications, _ = determine_dosage_from_db(
        nutrient_key=nutrient,
        need_score=need_score,
        user_gender=user.gender,
        user_age=user.age,
        other_supplements=other_supplements,
        bypass_upper_limit=bypass_upper_limit  # ✅ Explicitly passed through
    )

    # 🛠 Filter out irrelevant iron warnings for females with known iron deficiency
    if nutrient.lower() == "iron":
        if "iron deficiency" in [c.lower() for c in user.medical_conditions]:
            contraindications = [c for c in contraindications if "hemochromatosis" not in c.lower()]

    return dosage, unit, contraindications