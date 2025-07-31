from pathlib import Path
from app.data_model import SupplementRecommendation, UserFeedback, UserProfile
from app.feedback_loop import label_recommendations_with_feedback

def test_no_feedback_no_change():
    recs = [
        SupplementRecommendation(
            name="vitamin c",
            dosage=100,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[]  # Added missing argument
        )
    ]
    user = UserProfile(user_id="user1", age=25, gender="female", feedback=None)
    updated = label_recommendations_with_feedback(user, recs)
    assert updated[0].dosage == 100

def test_symptom_worse_increases_dosage():
    recs = [
        SupplementRecommendation(
            name="iron",
            dosage=10,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[]
        )
    ]
    user = UserProfile(
        user_id="user2",
        age=40,
        gender="male",
        feedback=UserFeedback(symptom_changes={"fatigue": "worse"})
    )
    updated = label_recommendations_with_feedback(user, recs, adjustment_factor=0.2)
    assert updated[0].dosage == 12  # 10 + 20%

def test_symptom_better_decreases_dosage():
    recs = [
        SupplementRecommendation(
            name="iron",
            dosage=10,
            unit="mg",
            reason=None,
            triggered_by=[],
            contraindications=[],
            inputs_triggered=[]
        )
    ]
    user = UserProfile(
        user_id="user3",
        age=40,
        gender="male",
        feedback=UserFeedback(symptom_changes={"fatigue": "better"})
    )
    updated = label_recommendations_with_feedback(user, recs, adjustment_factor=0.1)
    assert updated[0].dosage == 9  # 10 - 10%

# Add more tests as needed