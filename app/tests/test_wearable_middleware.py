from pathlib import Path
from app.wearable_middleware import WearableMiddleware

def test_fetch_apple_health_data():
    middleware = WearableMiddleware()
    data = middleware.fetch_data(user_id="123", source="apple_health")
    assert isinstance(data, dict)
    assert "heart_rate" in data
    assert "sleep_hours" in data

def test_normalize_apple_health_data():
    middleware = WearableMiddleware()
    raw_data = {
        "heart_rate": 60,
        "sleep_hours": 7.5,
        "activity_minutes": 45,
        "blood_oxygen": 98,
    }
    normalized = middleware.normalize_data(raw_data, source="apple_health")
    assert normalized["heart_rate"] == 60
    assert normalized["sleep_hours"] == 7.5
    assert normalized["activity_level"] == 45
    assert normalized["blood_oxygen"] == 98

def test_fetch_oura_data():
    middleware = WearableMiddleware()
    data = middleware.fetch_data(user_id="abc", source="oura")
    assert isinstance(data, dict)
    assert "readiness_score" in data
    assert "sleep_quality" in data
    assert "resting_hr" in data

def test_normalize_oura_data():
    middleware = WearableMiddleware()
    raw_data = {
        "readiness_score": 75,
        "sleep_quality": 80,
        "resting_hr": 58,
    }
    normalized = middleware.normalize_data(raw_data, source="oura")
    assert normalized["heart_rate"] == 58
    assert normalized["sleep_hours"] == 8.0  # 80 / 10
    assert normalized["activity_level"] is None
    assert normalized["readiness_score"] == 75

def test_integrate_blood_test():
    middleware = WearableMiddleware()
    blood_data = {
        "Vitamin D": 30,
        "Ferritin": 50,
        "B12": 500
    }
    biomarkers = middleware.integrate_blood_test(blood_data)
    assert biomarkers["Vitamin D"] == 30
    assert biomarkers["Ferritin"] == 50
    assert biomarkers["B12"] == 500