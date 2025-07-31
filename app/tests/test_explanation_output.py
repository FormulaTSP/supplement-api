from app.data_model import UserProfile, BloodTestResult, WearableMetrics, UserFeedback
from app.supplement_engine import generate_supplement_plan

# ✅ Single UserProfile object (not wrapped in a list)
test_user = UserProfile(
    user_id="test001",
    age=32,
    gender="female",
    weight_kg=65,
    height_cm=168,
    diet_type="omnivore",
    location="San Francisco",
    goals=["improve energy"],
    symptoms=["fatigue"],
    medical_history={"hypothyroidism": True},
    medications=["ciprofloxacin"],  # Triggers interaction flag with iron
    blood_tests=[
        BloodTestResult(marker="Vitamin D", value=18, unit="ng/mL")
    ],
    wearable_data=WearableMetrics(
        sleep_hours=6.5,
        sunlight_exposure_minutes=30
    ),
    feedback=UserFeedback(
        energy="low",
        symptoms=["brain fog"]
    )
)

# ✅ Call the function directly with the object (not a list)
result = generate_supplement_plan(test_user)

# 🔍 Print results
print("\n--- SUPPLEMENT PLAN ---")
for rec in result.recommendations:
    print(f"\n▶ {rec.name.upper()}")
    print(f"  Dose: {rec.dosage} {rec.unit}")
    print(f"  Reason: {rec.reason}")
    print(f"  Explanation: {rec.explanation}")
    if rec.validation_flags:
        print(f"  ⚠️ Flags: {rec.validation_flags}")
    if rec.contraindications:
        print(f"  Contraindications: {rec.contraindications}")