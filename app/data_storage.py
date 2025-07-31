from pathlib import Path
import json
from typing import List
from app.data_model import UserProfile, BloodTestResult, WearableMetrics, UserFeedback
import os

USERS_FILE = Path(__file__).parent / "users.json"

def blood_tests_to_list(blood_tests: List[BloodTestResult]) -> List[dict]:
    if not blood_tests:
        return []
    return [bt.__dict__ for bt in blood_tests]

def list_to_blood_tests(blood_tests_list: List[dict]) -> List[BloodTestResult]:
    if not blood_tests_list:
        return []
    return [BloodTestResult(**bt) for bt in blood_tests_list]

def wearable_to_dict(wearable: WearableMetrics) -> dict:
    if not wearable:
        return None
    return wearable.__dict__

def dict_to_wearable(data: dict) -> WearableMetrics:
    if not data:
        return None
    return WearableMetrics(**data)

def feedback_to_dict(feedback: UserFeedback) -> dict:
    if not feedback:
        return {}
    return feedback.__dict__

def dict_to_feedback(data: dict) -> UserFeedback:
    if not data:
        return None
    return UserFeedback(**data)

def user_to_dict(user: UserProfile) -> dict:
    return {
        "user_id": user.user_id,
        "age": user.age,
        "gender": user.gender,
        "symptoms": user.symptoms,
        "medical_conditions": user.medical_conditions,
        "blood_tests": blood_tests_to_list(user.blood_tests),
        "wearable_data": wearable_to_dict(user.wearable_data),
        "feedback": feedback_to_dict(user.feedback),
        "lifestyle": user.lifestyle,
        "medical_history": user.medical_history,
        "goals": user.goals,
        "medications": user.medications,
        "cluster_id": user.cluster_id,
        "weight_kg": user.weight_kg,
        "height_cm": user.height_cm,
        "diet_type": user.diet_type,
        "location": user.location
    }

def dict_to_user(data: dict) -> UserProfile:
    return UserProfile(
        user_id=data.get("user_id"),
        age=data.get("age"),
        gender=data.get("gender"),
        symptoms=data.get("symptoms", []),
        medical_conditions=data.get("medical_conditions", []),
        blood_tests=list_to_blood_tests(data.get("blood_tests", [])),
        wearable_data=dict_to_wearable(data.get("wearable_data")),
        feedback=dict_to_feedback(data.get("feedback")),
        lifestyle=data.get("lifestyle", {}),
        medical_history=data.get("medical_history", {}),
        goals=data.get("goals", []),
        medications=data.get("medications", []),
        cluster_id=data.get("cluster_id"),
        weight_kg=data.get("weight_kg"),
        height_cm=data.get("height_cm"),
        diet_type=data.get("diet_type"),
        location=data.get("location")
    )
print("Loading users from:", os.path.abspath(USERS_FILE))
def load_all_users() -> List[UserProfile]:
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        data = json.load(f)
    return [dict_to_user(d) for d in data]

def save_all_users(users: List[UserProfile]):
    with open(USERS_FILE, "w") as f:
        json.dump([user_to_dict(u) for u in users], f, indent=2)

def save_user(user: UserProfile):
    users = load_all_users()
    for i, u in enumerate(users):
        if u.user_id == user.user_id:
            users[i] = user
            break
    else:
        users.append(user)
    save_all_users(users)

# --------------------------
# Test script
# --------------------------

def test_storage():
    bt1 = BloodTestResult(marker="vitamin d", value=25.0, unit="ng/mL")
    wearable = WearableMetrics(
        sleep_hours=7.5,
        hrv=50,
        resting_hr=60,
        activity_level=3,
        temperature_variation=0.1,
        spo2=98,
        sunlight_exposure_minutes=30
    )
    feedback = UserFeedback(symptoms=["fatigue"], mood="better")
    user = UserProfile(
        user_id="user123",
        age=30,
        gender="female",
        symptoms=["fatigue", "insomnia"],
        medical_conditions=["iron deficiency"],
        blood_tests=[bt1],
        wearable_data=wearable,
        feedback=feedback
    )

    save_user(user)
    users = load_all_users()
    loaded_user = next((u for u in users if u.user_id == "user123"), None)

    assert loaded_user is not None, "User not found after loading"
    assert loaded_user.age == 30, "Age mismatch"
    assert loaded_user.blood_tests[0].marker == "vitamin d", "Blood test marker mismatch"
    assert loaded_user.wearable_data.spo2 == 98, "Wearable spo2 mismatch"
    assert loaded_user.feedback.symptoms == ["fatigue"], "Feedback symptom mismatch"

    print("Data storage test passed.")

if __name__ == "__main__":
    test_storage()

load_users = load_all_users  # Makes both names valid
