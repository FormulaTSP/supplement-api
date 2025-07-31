from pathlib import Path
from typing import List
from app.data_model import UserProfile, SupplementRecommendation
from app.supplement_utils import get_supplement_data

def validate_recommendations(user: UserProfile, recommendations: List[SupplementRecommendation]) -> List[SupplementRecommendation]:
    validated = []
    user_conditions = {k.lower(): v for k, v in user.medical_history.items() if v is True}

    for rec in recommendations:
        supplement = get_supplement_data(rec.name)
        flags = []

        # A. Upper limit check
        if rec.dosage > supplement.get("upper_limit", float("inf")):
            flags.append("⚠️ Exceeds upper limit")

        # B. Contraindication check
        for condition in supplement.get("contraindications", []):
            if condition.lower() in user_conditions:
                flags.append(f"❌ Contraindicated for: {condition}")

        # C. Bi-directional interaction check
        interactions = set()

        for other in recommendations:
            if other.name.lower() == rec.name.lower():
                continue

            other_supp = get_supplement_data(other.name)

            # Check if current supplement lists the other as an interaction
            if other.name.lower() in [i.lower() for i in supplement.get("interactions", [])]:
                interactions.add(other.name)

            # Check if the other supplement lists the current one as an interaction
            if rec.name.lower() in [i.lower() for i in other_supp.get("interactions", [])]:
                interactions.add(other.name)

        if interactions:
            joined = ", ".join(sorted(interactions))
            flags.append(f"⚠️ May interact with: {joined}")

        rec.validation_flags = flags
        validated.append(rec)

    return validated