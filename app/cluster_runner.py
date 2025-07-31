from pathlib import Path
# cluster_runner.py

import json
import os
from app.data_storage import load_all_users, save_all_users
from app.cluster_engine import ClusterEngine
from app.cluster_logger import log_cluster_assignments, log_protocol_differences
from app.data_model import SupplementRecommendation

CLUSTER_PROTOCOLS_FILE = Path(__file__).parent / "cluster_protocols.json"

def load_old_protocols():
    if os.path.exists(CLUSTER_PROTOCOLS_FILE):
        with open(CLUSTER_PROTOCOLS_FILE, "r") as f:
            raw = json.load(f)
            return {
                int(cid): [
                    SupplementRecommendation(
                        name=s["name"],
                        dosage=s["dosage"],
                        unit=s["unit"],
                        reason=s.get("reason", "N/A"),
                        triggered_by=s.get("triggered_by", []),
                        contraindications=s.get("contraindications", []),
                        inputs_triggered=s.get("inputs_triggered", [])
                    )
                    for s in supps
                ]
                for cid, supps in raw.items()
            }
    return {}

def run_clustering():
    users = load_all_users()
    if not users:
        print("No users to cluster.")
        return

    # Load old protocols from file
    old_protocols = load_old_protocols()

    # Fit and assign with updated engine
    cluster_engine = ClusterEngine(n_clusters=5)
    cluster_engine.fit(users)

    for user in users:
        cluster = cluster_engine.assign_cluster(user)
        user.cluster_id = cluster

    save_all_users(users)

    # Log new assignments and any protocol differences
    log_cluster_assignments(users)
    new_protocols = load_old_protocols()  # Load updated protocols
    log_protocol_differences(old_protocols, new_protocols)

    print(f"âœ… Assigned clusters for {len(users)} users and logged protocol changes.")

if __name__ == "__main__":
    run_clustering()
