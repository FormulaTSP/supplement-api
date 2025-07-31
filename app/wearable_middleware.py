from pathlib import Path
from typing import Dict, Any, Optional

class WearableMiddleware:
    def __init__(self):
        self.api_clients = {
            "apple_health": None,
            "oura": None,
            "whoop": None,
            "garmin": None,
        }

    def fetch_data(self, user_id: str, source: str) -> Optional[Dict[str, Any]]:
        """
        Simulate fetching wearable data from a specific API/source.
        """
        print(f"Fetching data for user '{user_id}' from source '{source}'")

        if source == "apple_health":
            data = {
                "heart_rate": 60,
                "sleep_hours": 7.5,
                "activity_minutes": 45,
                "blood_oxygen": 98,
            }
            print(f"Fetched Apple Health data: {data}")
            return data
        elif source == "oura":
            data = {
                "readiness_score": 75,
                "sleep_quality": 80,
                "resting_hr": 58,
            }
            print(f"Fetched Oura data: {data}")
            return data

        print(f"Warning: Source '{source}' not supported. Returning None.")
        return None

    def normalize_data(self, raw_data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """
        Normalize raw wearable data into a consistent format.
        Basic validation included.
        """
        print(f"Normalizing data from source '{source}'")

        normalized = {}

        if not raw_data:
            print("Warning: No raw data provided to normalize.")
            return normalized

        if source == "apple_health":
            normalized = {
                "heart_rate": self._safe_get_number(raw_data, "heart_rate"),
                "sleep_hours": self._safe_get_number(raw_data, "sleep_hours"),
                # Activity level here is in minutes; downstream should know this
                "activity_level": self._safe_get_number(raw_data, "activity_minutes"),
                "blood_oxygen": self._safe_get_number(raw_data, "blood_oxygen"),
            }
        elif source == "oura":
            sleep_quality = self._safe_get_number(raw_data, "sleep_quality")
            normalized = {
                "heart_rate": self._safe_get_number(raw_data, "resting_hr"),
                "sleep_hours": sleep_quality / 10 if sleep_quality is not None else None,
                "activity_level": None,  # Oura does not provide activity here
                "readiness_score": self._safe_get_number(raw_data, "readiness_score"),
            }
        else:
            print(f"Warning: Normalization rules for source '{source}' not defined.")
        
        print(f"Normalized data: {normalized}")
        return normalized

    def _safe_get_number(self, data: Dict[str, Any], key: str) -> Optional[float]:
        """Helper to safely extract a numeric value or None."""
        val = data.get(key)
        if val is None:
            print(f"Warning: Key '{key}' missing in data.")
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            print(f"Warning: Value for '{key}' is not numeric: {val}")
            return None

    def integrate_blood_test(self, blood_test_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process blood test data for future expansion.
        """
        biomarkers = {}
        for nutrient, value in blood_test_data.items():
            biomarkers[nutrient] = value
        return biomarkers


# Example usage
if __name__ == "__main__":
    wm = WearableMiddleware()
    user_id = "user123"
    
    raw_apple = wm.fetch_data(user_id, "apple_health")
    normalized_apple = wm.normalize_data(raw_apple, "apple_health")
    
    raw_oura = wm.fetch_data(user_id, "oura")
    normalized_oura = wm.normalize_data(raw_oura, "oura")
    
    raw_unknown = wm.fetch_data(user_id, "fitbit")
    normalized_unknown = wm.normalize_data(raw_unknown, "fitbit")