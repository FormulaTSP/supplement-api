from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
from app.data_model import UserProfile, BloodTestResult, WearableMetrics, SupplementRecommendation
from app.supplement_engine import generate_supplement_plan

@pytest.fixture
def mock_user():
    return UserProfile(
        user_id="testuser1",
        age=30,
        gender="male",
        symptoms=["fatigue", "headache"],
        blood_tests=[BloodTestResult(marker="vitamin_d", value=20, unit="ng/mL")],
        wearable_data=WearableMetrics(
            sleep_hours=7,
            hrv=None,
            resting_hr=60,
            activity_level=None,
            temperature_variation=None,
            spo2=None,
            sunlight_exposure_minutes=None
        ),
        feedback=None
    )

@patch("supplement_engine.score_nutrient_needs")
@patch("supplement_engine.WearableMiddleware")
@patch("feedback_loop.label_recommendations_with_feedback")  # Correct patch here
@patch("supplement_engine.determine_dosage")
def test_generate_supplement_plan(
    mock_determine_dosage,
    mock_update_feedback,
    mock_wearable_middleware,
    mock_score_needs,
    mock_user,
):
    mock_score_needs.return_value = {"vitamin_d": 0.8, "magnesium": 0.5}
    mock_determine_dosage.side_effect = [
        (2000, "IU", []),  # vitamin_d dosage
        (400, "mg", []),   # magnesium dosage
    ]
    mock_middleware_instance = MagicMock()
    mock_wearable_middleware.return_value = mock_middleware_instance
    mock_middleware_instance.integrate_blood_test.return_value = {"vitamin_d": 25}
    mock_middleware_instance.normalize_data.return_value = {"heart_rate": 60}
    mock_update_feedback.side_effect = lambda recs, user: recs

    output = generate_supplement_plan(mock_user)
    recommendations = output.recommendations

    assert isinstance(recommendations, list)
    assert all(isinstance(rec, SupplementRecommendation) for rec in recommendations)
    assert any(rec.name == "vitamin_d" for rec in recommendations)
    assert any(rec.name == "magnesium" for rec in recommendations)
    assert recommendations[0].dosage == 2000
    assert recommendations[1].dosage == 400

if __name__ == "__main__":
    pytest.main()