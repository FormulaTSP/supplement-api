from pathlib import Path
import os
os.environ["TESTING"] = "1"

from app.data_storage import load_all_users
from app.supplement_engine import generate_supplement_plan
from app.cluster_engine import ClusterEngine

def main():
    users = load_all_users()
    print(f"Loaded {len(users)} users.")

    # Fit cluster engine to users
    cluster_engine = ClusterEngine(n_clusters=3)
    cluster_engine.fit(users)
    print("Clustering complete.")

    # Assign clusters and update users
    for user in users:
        cluster_id = cluster_engine.assign_cluster(user)
        user.cluster_id = cluster_id
        print(f"User {user.user_id} assigned to cluster {cluster_id}")

    print("\n" + "=" * 40)
    for user in users:
        print(f"Supplement Plan for User {user.user_id} (Cluster {user.cluster_id}):")

        # Optional: Show distance to centroid for debug
        dist = cluster_engine.distance_to_centroid(user)
        print(f"Distance to centroid: {dist:.3f}")

        try:
            # Pass cluster_engine instance explicitly!
            output = generate_supplement_plan(user, cluster_engine=cluster_engine)
            for r in output.recommendations:
                print(f"- {r.name}: {r.dosage} {r.unit} (Reason: {r.reason})")

        except Exception as e:
            print(f"[ERROR] Could not generate plan: {e}")
        print("\n" + "=" * 40)

if __name__ == "__main__":
    main()