from pathlib import Path
# user_update_pipeline.py

from typing import Tuple, List
from app.data_model import UserProfile
from app.data_storage import load_all_users, save_user
from app.cluster_engine import ClusterEngine
from app.cluster_logger import log_cluster_assignments, log_protocol_differences

def add_user_and_recluster(new_user_data: UserProfile) -> Tuple[UserProfile, ClusterEngine]:
    all_users: List[UserProfile] = load_all_users()
    all_users.append(new_user_data)

    old_engine = ClusterEngine(n_clusters=3)
    old_engine.fit(all_users)
    old_protocols = old_engine.protocols

    cluster_engine = ClusterEngine(n_clusters=3)
    cluster_engine.fit(all_users)
    new_protocols = cluster_engine.protocols

    for user in all_users:
        user.cluster_id = cluster_engine.assign_cluster(user)
        save_user(user)

    new_user_data.cluster_id = cluster_engine.assign_cluster(new_user_data)

    # âœ… Logging:
    log_cluster_assignments(all_users)
    log_protocol_differences(old_protocols, new_protocols)

    return new_user_data, cluster_engine