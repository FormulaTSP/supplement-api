from pathlib import Path
import requests
import json

url = "http://127.0.0.1:8000/recommend"

payload = {
    "age": 30,
    "gender": "female",
    "symptoms": ["fatigue", "brain fog"],
    "lifestyle": {"smoking": False, "exercise_level": "moderate"},
    "medical_history": {"anemia": True},
    "medical_conditions": ["hypothyroidism"],
    "medications": ["med1"],
    "goals": ["better sleep", "more energy"],
    "blood_tests": [
        {"marker": "Vitamin D", "value": 18, "unit": "ng/mL"},
        {"marker": "Iron", "value": 40, "unit": "Âµg/dL"}
    ],
    "wearable_data": {
        "sleep_hours": 6.5,
        "activity_level": "moderate"
    },
    "feedback": {
        "mood": "okay",
        "energy": "low",
        "stress": "moderate",
        "symptoms": ["fatigue"],
        "symptom_changes": {"fatigue": "worse"}
    }
}

headers = {'Content-Type': 'application/json'}

response = requests.post(url, data=json.dumps(payload), headers=headers)

if response.ok:
    print("Response JSON:")
    print(json.dumps(response.json(), indent=4))
else:
    print(f"Request failed with status code {response.status_code}")
    print(response.text)