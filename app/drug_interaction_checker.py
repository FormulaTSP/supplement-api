from pathlib import Path
# drug_interaction_checker.py

import json
from typing import List
from app.data_model import UserProfile, SupplementRecommendation

# Path to local drug-supplement interaction JSON
LOCAL_INTERACTION_DB = "drug_supp_interactions.json"

def load_local_interactions() -> dict:
    """Load drug–supplement interactions from JSON."""
    try:
        with open(LOCAL_INTERACTION_DB, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[Warning] Local interaction file {LOCAL_INTERACTION_DB} not found.")
        return {}

def check_from_local_json(user: UserProfile, recs: List[SupplementRecommendation]) -> List[str]:
    """
    Check user's medications against known supplement interactions from local DB.
    Returns a list of warning strings.
    """
    warnings = []
    interactions = load_local_interactions()

    meds = [m.lower() for m in user.medications or []]
    supps = [r.name.lower() for r in recs]

    for med in meds:
        flagged = []
        if med in interactions:
            for supp in supps:
                if supp in interactions[med]:
                    flagged.append(supp.title())
        if flagged:
            warning = f"⚠️ May interact with {med.title()}: {', '.join(flagged)}"
            warnings.append(warning)

    return warnings

def attach_interaction_flags(user: UserProfile, recs: List[SupplementRecommendation], use_api: bool = False) -> List[SupplementRecommendation]:
    """
    Attach warnings to supplement recommendations if they may interact with user's medications.
    """
    if use_api:
        warnings_map = query_external_interactions(user, recs)
    else:
        warnings_map = get_interaction_flags_local(user, recs)

    for rec in recs:
        rec_warnings = warnings_map.get(rec.name.lower(), [])
        rec.validation_flags.extend(rec_warnings)

    return recs

def get_interaction_flags_local(user: UserProfile, recs: List[SupplementRecommendation]) -> dict:
    """
    Builds a {supplement: [warnings]} map based on local JSON interactions.
    """
    interactions = load_local_interactions()
    meds = [m.lower() for m in user.medications or []]
    result = {}

    for rec in recs:
        name = rec.name.lower()
        flags = []
        for med in meds:
            if med in interactions and name in interactions[med]:
                flags.append(f"⚠️ Interacts with {med}")
        if flags:
            result[name] = flags
    return result

# Placeholder for external API integration (optional future feature)
def query_external_interactions(user: UserProfile, recs: List[SupplementRecommendation]) -> dict:
    """
    Optional: Call an external API to check drug–supplement interactions.
    This is a stub for future expansion.
    """
    # Implement with DrugBank / RxNav if needed later
    return {}