from pathlib import Path
# symptom_scorer.py

from typing import Dict
from app.data_model import UserProfile

# Symptom → Nutrient weighted relevance map
SYMPTOM_NUTRIENT_MAP: Dict[str, Dict[str, float]] = {
    "fatigue": {"Vitamin B12": 0.9, "Iron": 0.8, "Vitamin D": 0.6, "Magnesium": 0.4},
    "low energy": {"Iron": 0.7, "Vitamin B12": 0.6, "CoQ10": 0.4},
    "poor sleep": {"Magnesium": 0.8, "Melatonin": 0.7, "Vitamin B6": 0.4},
    "anxiety": {"Magnesium": 0.8, "Ashwagandha": 0.7, "Vitamin B6": 0.6},
    "low mood": {"Omega-3": 0.8, "Vitamin D": 0.7, "Folate (B9)": 0.6},
    "brain fog": {"Choline": 0.7, "Omega-3": 0.6, "Vitamin B12": 0.6},
    "frequent colds": {"Vitamin C": 0.7, "Zinc": 0.8, "Vitamin D": 0.6},
    "cramps": {"Magnesium": 0.8, "Calcium": 0.6},
    "poor recovery": {"Omega-3": 0.7, "Magnesium": 0.5},
    "hair loss": {"Iron": 0.6, "Zinc": 0.6, "Biotin": 0.5},
}

# Lifestyle → Nutrient adjustments
LIFESTYLE_NUTRIENT_MODIFIERS: Dict[str, Dict[str, float]] = {
    "vegan": {"Vitamin B12": 0.3, "Iron": 0.2, "Zinc": 0.2, "Omega-3": 0.2},
    "athlete": {"Magnesium": 0.2, "CoQ10": 0.2, "Protein": 0.3},
    "pregnant": {"Folate (B9)": 0.4, "Iron": 0.3, "Calcium": 0.2, "DHA": 0.3},
}

# Combine nutrients from both maps to cover all
ALL_NUTRIENTS = list({
    nutrient
    for mapping in SYMPTOM_NUTRIENT_MAP.values()
    for nutrient in mapping
} | {
    nutrient
    for mapping in LIFESTYLE_NUTRIENT_MODIFIERS.values()
    for nutrient in mapping
})

def score_nutrient_needs(user: UserProfile) -> Dict[str, float]:
    """
    Computes a nutrient → need score (0 to 1) based on:
      - Reported symptoms
      - Feedback symptoms (if any)
      - Lifestyle modifiers
    """
    scores = {nutrient: 0.0 for nutrient in ALL_NUTRIENTS}

    # Combine reported symptoms + feedback symptoms (if present)
    all_symptoms = [s.lower() for s in user.symptoms or []]

    if user.feedback and getattr(user.feedback, "symptoms", None):
        all_symptoms += [s.lower() for s in user.feedback.symptoms or []]

    # Symptom-based scoring
    for symptom in all_symptoms:
        if symptom in SYMPTOM_NUTRIENT_MAP:
            for nutrient, weight in SYMPTOM_NUTRIENT_MAP[symptom].items():
                scores[nutrient] += weight

    # Lifestyle can be dict or list; get keys accordingly
    if isinstance(user.lifestyle, dict):
        lifestyle_keys = user.lifestyle.keys()
    else:
        lifestyle_keys = user.lifestyle or []

    # Lifestyle-based adjustments
    for lifestyle in lifestyle_keys:
        lifestyle_lower = lifestyle.lower()
        modifiers = LIFESTYLE_NUTRIENT_MODIFIERS.get(lifestyle_lower, {})
        for nutrient, bump in modifiers.items():
            scores[nutrient] = scores.get(nutrient, 0.0) + bump

    # Normalize scores to 0–1 scale
    max_score = max(scores.values()) if scores else 1.0
    for nutrient in scores:
        normalized = scores[nutrient] / max_score if max_score > 0 else 0.0
        scores[nutrient] = round(min(normalized, 1.0), 3)

    return scores