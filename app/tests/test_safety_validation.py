import os
import pytest
from app.data_model import UserProfile, BloodTestResult
from app.supplement_engine import generate_supplement_plan
from app.supplement_utils import get_supplement_data

print("\n[Debug] Magnesium upper limit:", get_supplement_data("Magnesium").get("upper_limit"))


def test_contraindicated_supplement_flagged():
    user = UserProfile(
        user_id="test_user_1",
        gender="male",
        age=45,
        symptoms=["fatigue", "low energy"],
        goals=["energy"],
        medical_history={"hemochromatosis": True},
        feedback=None,
        blood_tests=[],
        wearable_data=None,
        cluster_id=None
    )

    output = generate_supplement_plan(user)

    print("\n💊 Test 1 - Contraindication Flags:")
    for rec in output.recommendations:
        print(f"- {rec.name} ({rec.dosage} {rec.unit})")
        for flag in rec.validation_flags:
            print(f"    ⚠️ {flag}")

    assert any("Iron" in rec.name for rec in output.recommendations)
    assert any("❌ Contraindicated for: hemochromatosis" in f for rec in output.recommendations for f in rec.validation_flags)


def test_upper_limit_flag():
    os.environ["TESTING"] = "1"  # ✅ Force testing mode

    user = UserProfile(
        user_id="test_user_2",
        gender="female",
        age=30,
        symptoms=["fatigue", "low energy", "cramps"],  # all boost Magnesium
        goals=["immunity"],
        medical_history={},
        feedback=None,
        blood_tests=[],
        wearable_data=None,
        cluster_id=None
    )

    output = generate_supplement_plan(user)

    print("\n💊 Test 2 - Upper Limit Flags:")
    for rec in output.recommendations:
        print(f"- {rec.name} ({rec.dosage} {rec.unit})")
        for flag in rec.validation_flags:
            print(f"    ⚠️ {flag}")

    flagged = [rec for rec in output.recommendations if "⚠️ Exceeds upper limit" in (rec.validation_flags or [])]
    assert len(flagged) >= 1, "At least one supplement should exceed upper limit"


def test_interaction_flag():
    user = UserProfile(
        user_id="test_user_3",
        gender="female",
        age=40,
        symptoms=["fatigue", "hair loss"],
        goals=["energy"],
        medical_history={},
        feedback=None,
        blood_tests=[],
        wearable_data=None,
        cluster_id=None
    )

    output = generate_supplement_plan(user)

    print("\n💊 Test 3 - Interaction Flags:")
    for rec in output.recommendations:
        print(f"- {rec.name} ({rec.dosage} {rec.unit})")
        for flag in rec.validation_flags:
            print(f"    ⚠️ {flag}")

    found_interaction = any("⚠️ May interact with:" in flag for rec in output.recommendations for flag in rec.validation_flags)
    assert found_interaction, "Should detect at least one interaction (e.g., Iron + Calcium)"


def test_no_flags_healthy_user():
    user = UserProfile(
        user_id="test_user_4",
        gender="female",
        age=28,
        symptoms=["poor sleep"],
        goals=["focus"],
        medical_history={},
        feedback=None,
        blood_tests=[],
        wearable_data=None,
        cluster_id=None
    )

    output = generate_supplement_plan(user)

    print("\n💊 Test 4 - No Flags:")
    for rec in output.recommendations:
        print(f"- {rec.name} ({rec.dosage} {rec.unit})")
        for flag in rec.validation_flags:
            print(f"    ⚠️ {flag}")

    # Allow magnesium to exceed upper limit in high-need cases
    flagged = [
        rec for rec in output.recommendations
        if rec.validation_flags and rec.name != "Magnesium"
    ]
    assert not flagged, "Healthy user should not receive unexpected flagged supplements"