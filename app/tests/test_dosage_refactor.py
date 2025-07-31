from pathlib import Path
from app.data_model import UserProfile
from app.dosage_calculator import determine_dosage

# Create a mock user
user = UserProfile(
    user_id="test_user_1",
    age=35,
    gender="female",
    medical_conditions=["iron deficiency"],
    symptoms=["fatigue"]
)

# Test iron dosage with a high need score
dosage, unit, contraindications = determine_dosage("iron", 0.9, user)

# Print result
print(f"Recommended dosage for Iron: {dosage} {unit}")
print(f"Contraindications: {contraindications}")