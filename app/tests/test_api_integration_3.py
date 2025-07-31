from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.api import app
from app.data_model import UserProfile, WearableMetrics, BloodTestResult, UserFeedback

client = TestClient(app)

def create_rule_based_fallback_user():
    return {
        "age": 30,
        "gender": "female",
        "symptoms": ["fatigue", "headache"],
        "medical_conditions": [],
        "medical_history": {},
        "medications": [],
        "goals": ["improve energy"],
        "blood_tests": [
            {"marker": "Vitamin D", "value": 15, "unit": "ng/mL"},
            {"marker": "Iron", "value": 40, "unit": "Âµg/dL"}
        ],
        "wearable_data": {
            "sleep_hours": 6,
            "hrv": 45,
            "resting_hr": 60,
            "activity_level": "moderate",
            "temperature_variation": 0.2,
            "spo2": 98,
            "sunlight_exposure_minutes": 20
        },
        "feedback": {
            "mood": "same",
            "energy": "low",
            "stress": "moderate",
            "symptoms": ["fatigue"],
            "symptom_changes": {"fatigue": "worse"}
        }
    }

def test_cluster_based_recommendation():
    # Assuming you have a user that fits a cluster
    response = client.post("/recommend", json={
        "age": 35,
        "gender": "male",
        "symptoms": ["fatigue", "brain fog"],
        "medical_conditions": [],
        "medical_history": {},
        "medications": [],
        "goals": ["improve cognition"],
        "blood_tests": [],
        "wearable_data": {},
        "feedback": {}
    })
    assert response.status_code == 200
    data = response.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0
    # You can add more asserts on response structure/content

def test_rule_based_fallback_recommendation():
    user = create_rule_based_fallback_user()
    response = client.post("/recommend", json=user)
    assert response.status_code == 200
    data = response.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0
    # Check at least one recommendation matches expected nutrient keys
    nutrients = {rec["name"].lower() for rec in data["recommendations"]}
    assert "vitamin d" in nutrients or "iron" in nutrients

def test_invalid_input_returns_400():
    # Missing required field 'age'
    response = client.post("/recommend", json={"gender": "female"})
    assert response.status_code == 422 or response.status_code == 400