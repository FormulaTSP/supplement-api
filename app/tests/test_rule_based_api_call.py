from pathlib import Path
import requests
import json

API_URL = "http://127.0.0.1:8000/recommend"

# This user profile is unlikely to fit any cluster, forcing rule-based path
test_user = {
    "age": 30,
    "gender": "female",
    "symptoms": ["fatigue", "low energy", "dry skin"],
    "lifestyle": {"smoker": "no", "exercise_frequency": "moderate"},
    "medical_history": {"anemia": True},
    "medical_conditions": [],
    "medications": [],
    "goals": ["increase energy", "improve skin health"],
    "blood_tests": [
        {"marker": "Vitamin D", "value": 15, "unit": "ng/mL"},
        {"marker": "Iron", "value": 40, "unit": "Âµg/dL"}
    ],
    "wearable_data": {
        "sleep_hours": 5,
        "activity_level": "low",
        "hrv": 30
    },
    "feedback": {
        "mood": "low",
        "energy": "low",
        "stress": "high",
        "symptoms": ["fatigue", "dry skin"],
        "symptom_changes": {"fatigue": "worse", "dry skin": "same"}
    }
}

response = requests.post(API_URL, json=test_user)
print("Status Code:", response.status_code)
print("Response JSON:\n", json.dumps(response.json(), indent=4))