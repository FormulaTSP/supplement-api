# supplement_utils.py

import json
from typing import Tuple, List, Optional, Dict
from pathlib import Path

class SupplementDB:
    _instance = None
    _db_path = Path(__file__).parent / "supplement_db.json"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupplementDB, cls).__new__(cls)
            cls._instance._db = None
            cls._instance.load_db()
        return cls._instance

    def load_db(self, force_reload: bool = False) -> Dict[str, dict]:
        if self._db is None or force_reload:
            with open(self._db_path, "r", encoding="utf-8") as f:
                self._db = json.load(f)
        return self._db

    def get_supplement_data(self, name: str) -> dict:
        return self._db.get(name.lower(), {})

    def get_rda_key(self, gender: str, age: int) -> str:
        group = "50_plus" if age >= 50 else "18_50"
        gender = gender.lower()
        key = f"{gender}_{group}"
        valid_keys = {"female_18_50", "male_18_50", "female_50_plus", "male_50_plus"}
        return key if key in valid_keys else "female_18_50"

    def determine_dosage_from_db(
        self,
        nutrient_key: str,
        need_score: float,
        user_gender: str,
        user_age: int,
        other_supplements: Optional[List[str]] = None,
        bypass_upper_limit: bool = False
    ) -> Tuple[float, str, List[str], Optional[str]]:
        nutrient_key_norm = nutrient_key.lower().replace(" ", "_")
        nutrient = self._db.get(nutrient_key_norm)
        if not nutrient:
            return 0.0, "", [], f"Nutrient '{nutrient_key}' not found."

        unit = nutrient.get("unit", "")
        rda_key = self.get_rda_key(user_gender, user_age)
        rda = nutrient["rda_by_gender_age"].get(rda_key, 0)
        optimal_min, optimal_max = nutrient.get("optimal_range", (0, 0))
        upper_limit = nutrient.get("upper_limit", float("inf"))
        contraindications = nutrient.get("contraindications", [])

        # Determine dosage based on need score
        if need_score < 0.3:
            dose = rda
        elif need_score < 0.7:
            dose = (rda + optimal_min) / 2
        else:
            dose = optimal_max

        if not bypass_upper_limit:
            dose = min(dose, upper_limit)

        warnings = []
        if other_supplements:
            for supp in other_supplements:
                if nutrient["name"].lower() in supp.lower():
                    warnings.append(f"⚠️ Overlap: already included in '{supp}'")

        return round(dose, 2), unit, contraindications, "; ".join(warnings) if warnings else None


# Singleton instance to use throughout your app
supplement_db = SupplementDB()


# Convenience functions to keep compatibility with existing code

def load_supplement_db(force_reload: bool = False) -> Dict[str, dict]:
    return supplement_db.load_db(force_reload)

def get_supplement_data(name: str) -> dict:
    return supplement_db.get_supplement_data(name)

def determine_dosage_from_db(
    nutrient_key: str,
    need_score: float,
    user_gender: str,
    user_age: int,
    other_supplements: Optional[List[str]] = None,
    bypass_upper_limit: bool = False
) -> Tuple[float, str, List[str], Optional[str]]:
    return supplement_db.determine_dosage_from_db(
        nutrient_key,
        need_score,
        user_gender,
        user_age,
        other_supplements,
        bypass_upper_limit
    )
