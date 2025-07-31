from pathlib import Path
from app.data_model import UserProfile, BloodTestResult, WearableMetrics, UserFeedback
from app.data_storage import save_user
import random
import uuid
from typing import List, Optional

def generate_random_user(index: int) -> UserProfile:
    genders = ["male", "female"]
    all_symptoms = [
        "fatigue", "brain fog", "poor sleep", "low energy",
        "bloating", "dry skin", "mood swings", "low libido"
    ]
    medical_conditions = [
        [], ["hypothyroidism"], ["pcos"], ["depression"],
        ["anemia"], ["insulin resistance"]
    ]
    markers = [
        ("vitamin d", 20.0, "ng/mL"),
        ("iron", 50.0, "µg/dL"),
        ("b12", 300.0, "pg/mL"),
        ("ferritin", 30.0, "ng/mL")
    ]

    wearable = WearableMetrics(
        sleep_hours=round(random.uniform(5.0, 8.5), 1),
        hrv=round(random.uniform(20.0, 60.0), 1),
        resting_hr=round(random.uniform(55.0, 75.0), 1),
        activity_level=round(random.uniform(2.0, 7.0), 1),
        temperature_variation=round(random.uniform(0.1, 0.5), 2),
        spo2=round(random.uniform(95.0, 99.0), 1),
        sunlight_exposure_minutes=random.randint(10, 90)
    )

    feedback = UserFeedback(
        mood=random.choice(["better", "same", "worse"]),
        energy=random.choice(["low", "normal", "high"]),
        stress=random.choice(["low", "medium", "high"]),
        symptoms=random.sample(all_symptoms, k=2),
        symptom_changes={
            sym: random.choice(["better", "same", "worse"])
            for sym in random.sample(all_symptoms, k=2)
        }
    )

    return UserProfile(
        user_id=f"mock_user_{index}_{uuid.uuid4().hex[:6]}",
        age=random.randint(20, 50),
        gender=random.choice(genders),
        symptoms=random.sample(all_symptoms, k=3),
        medical_conditions=random.choice(medical_conditions),
        blood_tests=[
            BloodTestResult(
                marker=m[0],
                value=round(m[1] + random.uniform(-10, 10), 2),
                unit=m[2]
            ) for m in markers
        ],
        wearable_data=wearable,
        feedback=feedback,
        cluster_id=None
    )

def generate_multiple_users(count: int, seed: Optional[int] = None) -> List[UserProfile]:
    if seed is not None:
        random.seed(seed)
    users = [generate_random_user(i) for i in range(count)]
    return users

def save_multiple_users(users: List[UserProfile]) -> None:
    for user in users:
        save_user(user)
        print(f"✅ Saved mock user: {user.user_id}")

def main(count: int = 4, seed: Optional[int] = None) -> List[UserProfile]:
    users = generate_multiple_users(count, seed)
    save_multiple_users(users)
    return users

if __name__ == "__main__":
    main()