from pathlib import Path
from app.symptom_scorer import score_nutrient_needs
from app.data_model import UserProfile, UserFeedback


def test_single_symptom_scoring():
    user = UserProfile(user_id="1", age=30, gender="female", symptoms=["fatigue"])
    scores = score_nutrient_needs(user)
    assert scores["Vitamin B12"] > 0
    assert scores["Iron"] > 0
    assert scores["Magnesium"] > 0
    assert scores["CoQ10"] == 0


def test_multiple_symptoms_combination():
    user = UserProfile(user_id="2", age=35, gender="male", symptoms=["fatigue", "anxiety"])
    scores = score_nutrient_needs(user)
    assert scores["Magnesium"] > 0  # Comes from both symptoms
    assert scores["Ashwagandha"] > 0
    assert scores["Vitamin B6"] > 0


def test_feedback_symptoms_integration():
    feedback = UserFeedback(symptoms=["poor sleep"])
    user = UserProfile(user_id="3", age=28, gender="female", symptoms=[], feedback=feedback)
    scores = score_nutrient_needs(user)
    assert scores["Magnesium"] > 0
    assert scores["Melatonin"] > 0


def test_lifestyle_modifier_vegan():
    user = UserProfile(user_id="4", age=29, gender="female", symptoms=[], lifestyle=["vegan"])
    scores = score_nutrient_needs(user)
    assert scores["Vitamin B12"] > 0
    assert scores["Iron"] > 0
    assert scores["Zinc"] > 0


def test_symptoms_and_lifestyle_combined():
    feedback = UserFeedback(symptoms=["low mood"])
    user = UserProfile(user_id="5", age=32, gender="female", symptoms=["anxiety"], lifestyle=["vegan"], feedback=feedback)
    scores = score_nutrient_needs(user)
    assert scores["Magnesium"] > 0  # from anxiety
    assert scores["Vitamin D"] > 0  # from low mood
    assert scores["Vitamin B12"] > 0  # from vegan modifier


def test_normalization():
    user = UserProfile(user_id="6", age=40, gender="male", symptoms=["fatigue", "fatigue", "fatigue"])
    scores = score_nutrient_needs(user)
    assert all(0 <= v <= 1 for v in scores.values())