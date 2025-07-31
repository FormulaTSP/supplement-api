from pathlib import Path
# data_model.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union

# --- Supplement and Health Models ---

@dataclass
class BloodTestResult:
    marker: str         # Name of the blood marker, e.g., 'Vitamin D'
    value: float        # Numeric value of the test result
    unit: str           # Unit of measurement, e.g., 'ng/mL'

@dataclass
class WearableMetrics:
    sleep_hours: Optional[float] = None
    hrv: Optional[float] = None
    resting_hr: Optional[float] = None
    activity_level: Optional[str] = None
    temperature_variation: Optional[float] = None
    spo2: Optional[float] = None
    sunlight_exposure_minutes: Optional[int] = None

@dataclass
class UserFeedback:
    mood: Optional[str] = None
    energy: Optional[str] = None
    stress: Optional[str] = None
    symptoms: List[str] = field(default_factory=list)
    symptom_changes: Optional[Dict[str, str]] = field(default_factory=dict)

@dataclass
class DoseResponseEntry:
    date: str                                # e.g., "2025-07-28"
    supplement: str                          # e.g., "Vitamin D"
    dose: float                              # e.g., 2000
    unit: str                                # e.g., "IU"
    symptoms_targeted: List[str]             # e.g., ["fatigue", "mood"]
    outcome: Dict[str, str]                  # e.g., {"fatigue": "better", "mood": "same"}

# --- Core User Model ---

@dataclass
class UserProfile:
    user_id: str
    age: int
    gender: str  # "male", "female", or other
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    diet_type: Optional[str] = None
    location: Optional[str] = None

    lifestyle: Optional[Dict[str, Union[str, float, int]]] = field(default_factory=dict)
    medical_history: Optional[Dict[str, Union[str, bool, float]]] = field(default_factory=dict)

    goals: List[str] = field(default_factory=list)
    symptoms: List[str] = field(default_factory=list)
    medical_conditions: List[str] = field(default_factory=list
    )
    medications: List[str] = field(default_factory=list)

    wearable_data: Optional[WearableMetrics] = None
    blood_tests: List[BloodTestResult] = field(default_factory=list)
    feedback: Optional[UserFeedback] = None
    cluster_id: Optional[int] = None

    symptom_history: Optional[Dict[str, List[Dict[str, str]]]] = field(default_factory=dict)

    dose_response_log: List[DoseResponseEntry] = field(default_factory=list)

    # Optional field that can be injected at runtime
    recommendations: Optional[List["SupplementRecommendation"]] = None  # runtime only


@dataclass
class SupplementRecommendation:
    name: str
    dosage: float
    unit: str
    reason: Optional[str]
    triggered_by: List[str]
    contraindications: List[str]
    inputs_triggered: List[str]
    source: Optional[str] = "rule-based"
    validation_flags: List[str] = field(default_factory=list)
    explanation: Optional[str] = None  # ✅ NEW — for human-friendly output


@dataclass
class RecommendationOutput:
    user_id: str
    recommendations: List[SupplementRecommendation]
    confidence_score: float  # Confidence 0 (low) to 1 (high)
    cluster_id: Optional[int] = None  # ✅ NEW — included in output