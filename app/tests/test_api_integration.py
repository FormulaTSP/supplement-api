from pathlib import Path
# tests/test_api_integration.py

import pytest
from fastapi.testclient import TestClient
from app.api import app

client = TestClient(app)

def valid_user_input():
    return {
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
    }

def rule_based_fallback_user():
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

def test_happy_path_recommendation():
    response = client.post("/recommend", json=valid_user_input())
    assert response.status_code == 200
    data = response.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0

def test_rule_based_fallback():
    response = client.post("/recommend", json=rule_based_fallback_user())
    assert response.status_code == 200
    data = response.json()
    assert "recommendations" in data
    # Check that expected supplements appear
    names = [rec["name"].lower() for rec in data["recommendations"]]
    assert "vitamin d" in names or "iron" in names

def test_invalid_input_missing_age():
    # Age is required, so missing it should cause validation error
    invalid_data = {"gender": "female"}
    response = client.post("/recommend", json=invalid_data)
    assert response.status_code == 422  # Unprocessable Entity
    assert "detail" in response.json()