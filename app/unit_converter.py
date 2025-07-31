from pathlib import Path
# unit_converter.py

def normalize_blood_test_marker(marker: str, value: float, unit: str) -> tuple:
    """
    Normalize blood test marker values to standard units.
    Returns a tuple: (marker, normalized_value, normalized_unit).
    If no known conversion exists for the marker and unit, returns original values unchanged.
    """

    # Define the standard unit for each marker
    STANDARD_UNITS = {
        "vitamin d": "ng/mL",
        "iron": "µg/dL",
        "vitamin b12": "pg/mL",
        "folate": "ng/mL",
        # Add more markers and their standard units here
    }

    # Define conversion lambdas keyed by (marker_lower, from_unit_lower)
    CONVERSIONS = {
        ("vitamin d", "µg/l"): lambda v: v * 0.4,     # µg/L to ng/mL
        ("vitamin d", "nmol/l"): lambda v: v * 0.4,   # nmol/L to ng/mL (approx)
        ("vitamin d", "ng/ml"): lambda v: v,          # identity
        ("iron", "µg/dl"): lambda v: v,                # identity
        ("iron", "mg/l"): lambda v: v * 100,           # mg/L to µg/dL
        ("vitamin b12", "pmol/l"): lambda v: v * 1.355, # pmol/L to pg/mL (approx)
        ("vitamin b12", "pg/ml"): lambda v: v,         # identity
        ("folate", "nmol/l"): lambda v: v * 0.454,    # nmol/L to ng/mL (approx)
        ("folate", "ng/ml"): lambda v: v,              # identity
        # Add other markers and units as needed
    }

    marker_lower = marker.strip().lower()
    unit_lower = unit.strip().lower()

    key = (marker_lower, unit_lower)

    if key in CONVERSIONS:
        normalized_value = CONVERSIONS[key](value)
        normalized_unit = STANDARD_UNITS.get(marker_lower, unit)
        return (marker, normalized_value, normalized_unit)

    # No known conversion: return original values safely
    return (marker, value, unit)