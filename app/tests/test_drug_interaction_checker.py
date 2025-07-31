from pathlib import Path
import pytest
from app.data_model import UserProfile, SupplementRecommendation
from app.drug_interaction_checker import attach_interaction_flags

@pytest.fixture
def user_with_medications():
    return UserProfile(
        user_id="testuser",
        age=40,
        gender="female",
        medications=["ciprofloxacin", "warfarin"]
    )

def test_no_interactions_empty_recs(user_with_medications):
    recs = []
    flagged = attach_interaction_flags(user_with_medications, recs)
    assert flagged == []

def test_flags_interactions(user_with_medications):
    recs = [
        SupplementRecommendation(
            name="Iron",
            dosage=10,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[]
        ),
        SupplementRecommendation(
            name="Vitamin K",
            dosage=50,
            unit="mcg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[]
        ),
        SupplementRecommendation(
            name="Vitamin C",
            dosage=100,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[]
        ),
    ]

    flagged = attach_interaction_flags(user_with_medications, recs, use_api=False)

    # Check Iron flagged for ciprofloxacin
    iron_flags = next(rec.validation_flags for rec in flagged if rec.name.lower() == "iron")
    assert any("ciprofloxacin" in flag.lower() for flag in iron_flags)

    # Check Vitamin K flagged for warfarin
    vitk_flags = next(rec.validation_flags for rec in flagged if rec.name.lower() == "vitamin k")
    assert any("warfarin" in flag.lower() for flag in vitk_flags)

    # Vitamin C should have no flags
    vitc_flags = next(rec.validation_flags for rec in flagged if rec.name.lower() == "vitamin c")
    assert vitc_flags == []