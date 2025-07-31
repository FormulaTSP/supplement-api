from pathlib import Path
# cluster_logger.py

import json
import os
from datetime import datetime, timezone
from typing import List, Dict
from app.data_model import UserProfile, SupplementRecommendation

CLUSTER_HISTORY_FILE = "cluster_history.json"
PROTOCOL_CHANGE_LOG_FILE = "protocol_change_log.json"

def log_cluster_assignments(users: List[UserProfile]) -> None:
    """Append timestamped user cluster assignments to log."""
    history = []
    if os.path.exists(CLUSTER_HISTORY_FILE):
        with open(CLUSTER_HISTORY_FILE, "r") as f:
            history = json.load(f)

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assignments": {u.user_id: u.cluster_id for u in users}
    }
    history.append(snapshot)

    with open(CLUSTER_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def log_protocol_differences(old: Dict[int, List[SupplementRecommendation]],
                             new: Dict[int, List[SupplementRecommendation]]) -> None:
    """Compare and log differences between protocol sets."""
    def rec_to_dict(rec: SupplementRecommendation) -> Dict:
        return {
            "name": rec.name,
            "dosage": rec.dosage,
            "unit": rec.unit
        }

    changes = []
    for cluster_id, new_recs in new.items():
        old_recs = old.get(cluster_id, [])
        old_dict = {r.name: rec_to_dict(r) for r in old_recs}
        new_dict = {r.name: rec_to_dict(r) for r in new_recs}

        added = [v for k, v in new_dict.items() if k not in old_dict]
        removed = [v for k, v in old_dict.items() if k not in new_dict]
        modified = [
            {
                "name": k,
                "old": old_dict[k],
                "new": new_dict[k]
            }
            for k in new_dict if k in old_dict and new_dict[k] != old_dict[k]
        ]

        if added or removed or modified:
            changes.append({
                "cluster_id": cluster_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "added": added,
                "removed": removed,
                "modified": modified
            })

    if changes:
        log = []
        if os.path.exists(PROTOCOL_CHANGE_LOG_FILE):
            with open(PROTOCOL_CHANGE_LOG_FILE, "r") as f:
                log = json.load(f)

        log.extend(changes)
        with open(PROTOCOL_CHANGE_LOG_FILE, "w") as f:
            json.dump(log, f, indent=2)