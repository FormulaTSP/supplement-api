from pathlib import Path
from app.data_model import UserProfile, UserFeedback, WearableMetrics
from app.supplement_engine import generate_supplement_plan

def test_basic_recommendation():
    user = UserProfile(
        user_id="user_test",
        age=40,
        gender="male",
        symptoms=["fatigue"],
        lifestyle={"sleep_hours": 5},
        medical_history={"iron_deficiency": False},
        wearable_data=WearableMetrics(sleep_hours=6, resting_hr=65),
        feedback=UserFeedback(symptoms=["fatigue"])
    )

    output = generate_supplement_plan(user)

    print("✅ Recommendations:")
    for rec in output.recommendations:  # ✅ fix
        print(f"- {rec.name}: {rec.dosage} {rec.unit} → {rec.reason}")

if __name__ == "__main__":
    test_basic_recommendation()