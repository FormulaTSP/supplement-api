from pathlib import Path
# âœ… Updated test_dosage_calculator.py (robust to wording)

import pytest
from app.data_model import UserProfile
from app.dosage_calculator import determine_dosage

def test_unknown_nutrient():
    user = UserProfile(user_id="u1", age=30, gender="female", medical_conditions=[])
    dosage, unit, contraindications = determine_dosage("UnknownNutrient", 0.5, user)
    assert dosage == 0
    assert unit == ""
    assert contraindications == []

def test_iron_male_without_deficiency():
    user = UserProfile(user_id="u2", age=40, gender="male", medical_conditions=[])
    dosage, unit, contraindications = determine_dosage("Iron", 0.8, user)
    assert dosage == 0
    assert any("male" in c.lower() and "low symptom" in c.lower() for c in contraindications)

def test_iron_female_with_deficiency():
    user = UserProfile(user_id="u3", age=35, gender="female", medical_conditions=["iron deficiency"])
    dosage, unit, contraindications = determine_dosage("Iron", 0.9, user)
    assert dosage > 0
    assert unit == "mg"
    assert "hemochromatosis" not in [c.lower() for c in contraindications]

def test_dosage_scaling_low_need():
    user = UserProfile(user_id="u4", age=25, gender="female", medical_conditions=[])
    dosage, _, _ = determine_dosage("Vitamin D", 0.2, user)
    assert dosage == 600

def test_dosage_scaling_medium_need():
    user = UserProfile(user_id="u5", age=25, gender="female", medical_conditions=[])
    dosage, _, _ = determine_dosage("Vitamin D", 0.5, user)
    assert dosage == (600 + 1000) / 2

def test_dosage_scaling_high_need():
    user = UserProfile(user_id="u6", age=25, gender="female", medical_conditions=[])
    dosage, _, _ = determine_dosage("Vitamin D", 0.8, user)
    assert dosage == 2000

def test_dosage_does_not_exceed_ul():
    user = UserProfile(user_id="u7", age=25, gender="female", medical_conditions=[])
    dosage, _, _ = determine_dosage("Vitamin D", 1.0, user)
    assert dosage <= 4000

if __name__ == "__main__":
    pytest.main()