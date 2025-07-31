from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
from sklearn.cluster import KMeans
import json
import os
from collections import Counter
from app.data_model import UserProfile, SupplementRecommendation
from app.symptom_scorer import score_nutrient_needs
from app.dosage_calculator import determine_dosage
from app.explanation_utils import build_explanation  # <-- Added import here

SYMPTOM_VOCAB = sorted([
    "fatigue", "low energy", "poor sleep", "anxiety", "low mood",
    "brain fog", "frequent colds", "cramps", "poor recovery", "hair loss"
])

LIFESTYLE_VOCAB = sorted([
    "vegan", "athlete", "pregnant"
])

GENDER_VOCAB = ["male", "female", "other"]
CLUSTER_PROTOCOLS_FILE = Path(__file__).parent / "cluster_protocols.json"

def vectorize_user(user: UserProfile) -> np.ndarray:
    """
    Convert a UserProfile into a numeric vector for clustering.
    Age normalized to 0-1, one-hot encode gender, binary symptoms and lifestyle.
    """
    age_norm = (user.age or 0) / 100.0
    gender_vec = [1 if user.gender == g else 0 for g in GENDER_VOCAB]
    symptoms_lower = set(s.lower() for s in user.symptoms or [])
    symptom_vec = [1 if s in symptoms_lower else 0 for s in SYMPTOM_VOCAB]

    # Normalize lifestyle: support dict or list
    lifestyle_keys = []
    if isinstance(user.lifestyle, dict):
        lifestyle_keys = [k.lower() for k, v in user.lifestyle.items() if v]
    elif isinstance(user.lifestyle, list):
        lifestyle_keys = [str(l).lower() for l in user.lifestyle]
    lifestyle_vec = [1 if l in lifestyle_keys else 0 for l in LIFESTYLE_VOCAB]

    return np.array([age_norm] + gender_vec + symptom_vec + lifestyle_vec, dtype=float)


class ClusterEngine:
    def __init__(self, n_clusters: int = 5, random_state: int = 42):
        """
        Initialize ClusterEngine with the number of clusters and random state.
        """
        self.n_clusters = n_clusters
        self.model: Optional[KMeans] = None
        self.fitted = False
        self.protocols: Dict[int, List[SupplementRecommendation]] = self._load_protocols()
        self.random_state = random_state
        self.all_users: List[UserProfile] = []
        self.user_vectors: Optional[np.ndarray] = None

    def fit(self, users: List[UserProfile]) -> None:
        """
        Fit KMeans model to user vectors and generate cluster protocols.
        """
        if not users:
            print("[Warning] No users provided for clustering.")
            return

        self.all_users = users
        X = np.array([vectorize_user(u) for u in users])
        self.user_vectors = X
        self.model = KMeans(n_clusters=self.n_clusters, random_state=self.random_state)
        self.model.fit(X)
        self.fitted = True

        cluster_to_users: Dict[int, List[UserProfile]] = {i: [] for i in range(self.n_clusters)}
        for user in users:
            try:
                cluster_id = self.assign_cluster(user)
                cluster_to_users[cluster_id].append(user)
            except RuntimeError as e:
                print(f"[Warning] Could not assign cluster for user {user.user_id}: {e}")

        self.protocols = {
            cluster_id: generate_cluster_protocol(users_in_cluster)
            for cluster_id, users_in_cluster in cluster_to_users.items()
        }

        self._save_protocols()

    def assign_cluster(self, user: UserProfile) -> int:
        """
        Predict the cluster assignment for a user.
        Raises RuntimeError if model not fitted.
        """
        if not self.fitted or self.model is None:
            raise RuntimeError("ClusterEngine not fitted yet")
        vec = vectorize_user(user).reshape(1, -1)
        return int(self.model.predict(vec)[0])

    def distance_to_centroid(self, user: UserProfile) -> float:
        """
        Calculate Euclidean distance from user vector to assigned cluster centroid.
        """
        if not self.fitted or self.model is None:
            raise RuntimeError("ClusterEngine not fitted yet")
        vec = vectorize_user(user)
        cluster_idx = self.assign_cluster(user)
        centroid = self.model.cluster_centers_[cluster_idx]
        return np.linalg.norm(vec - centroid)

    def distance_to_all_centroids(self, user: UserProfile) -> List[float]:
        """
        Return list of distances from user vector to all cluster centroids.
        """
        if not self.fitted or self.model is None:
            raise RuntimeError("ClusterEngine not fitted yet")
        vec = vectorize_user(user)
        return [np.linalg.norm(vec - centroid) for centroid in self.model.cluster_centers_]

    def get_cluster_centroids(self) -> np.ndarray:
        """
        Return the cluster centroids.
        """
        if not self.fitted or self.model is None:
            raise RuntimeError("ClusterEngine not fitted yet")
        return self.model.cluster_centers_

    def get_cluster_protocol(self, cluster_id: int) -> List[SupplementRecommendation]:
        """
        Retrieve the supplement protocol for a given cluster.
        """
        if not self.protocols or cluster_id not in self.protocols:
            raise ValueError(f"No protocol available for cluster {cluster_id}")
        return self.protocols[cluster_id]

    def _save_protocols(self) -> None:
        """
        Save current cluster protocols to JSON file.
        """
        with open(CLUSTER_PROTOCOLS_FILE, "w") as f:
            json.dump({
                str(k): [rec.dict() if hasattr(rec, "dict") else rec.__dict__ for rec in v]
                for k, v in self.protocols.items()
            }, f, indent=2)
        print(f"[Debug] Saved cluster protocols to {CLUSTER_PROTOCOLS_FILE}")

    def _load_protocols(self) -> Dict[int, List[SupplementRecommendation]]:
        """
        Load cluster protocols from JSON file, if exists.
        """
        if not os.path.exists(CLUSTER_PROTOCOLS_FILE):
            print("[Debug] Cluster protocols file not found.")
            return {}
        with open(CLUSTER_PROTOCOLS_FILE, "r") as f:
            raw = json.load(f)
        print(f"[Debug] Loaded cluster protocols from {CLUSTER_PROTOCOLS_FILE}")
        return {
            int(k): [SupplementRecommendation(**rec) for rec in v]
            for k, v in raw.items()
        }


def generate_cluster_protocol(users_in_cluster: List[UserProfile]) -> List[SupplementRecommendation]:
    """
    Generate aggregate supplement protocol for a cluster of users.

    Aggregates nutrient need scores across users, computes average scores,
    and generates dosages based on a representative dummy user.
    """
    aggregate_scores = {}

    for user in users_in_cluster:
        scores = score_nutrient_needs(user)
        for nutrient, score in scores.items():
            aggregate_scores[nutrient] = aggregate_scores.get(nutrient, 0.0) + score

    n_users = len(users_in_cluster)
    if n_users == 0:
        return []

    avg_scores = {nutrient: total / n_users for nutrient, total in aggregate_scores.items()}

    ages = [u.age for u in users_in_cluster if u.age is not None]
    median_age = int(np.median(ages)) if ages else 40
    genders = [u.gender for u in users_in_cluster if u.gender in GENDER_VOCAB]
    gender = Counter(genders).most_common(1)[0][0] if genders else "female"

    # Determine frequent symptoms in cluster (top 3)
    symptom_counts = Counter(
        symptom.lower()
        for user in users_in_cluster
        for symptom in (user.symptoms or [])
    )
    top_symptoms = [s for s, _ in symptom_counts.most_common(3)]

    # Create dummy user for dosage calculation
    dummy_user = UserProfile(
        user_id="cluster_dummy",
        age=median_age,
        gender=gender,
        symptoms=top_symptoms,
        lifestyle=[],
        medical_conditions=[],
        medications=[],
        blood_tests=[],
        wearable_data=None,
        feedback=None
    )

    recommendations = []
    for nutrient, need_score in avg_scores.items():
        if need_score > 0:
            dose, unit, contraindications = determine_dosage(nutrient, need_score, dummy_user)
            if dose > 0:
                rec = SupplementRecommendation(
                    name=nutrient,
                    dosage=dose,
                    unit=unit,
                    reason=f"Cluster baseline need score: {round(need_score, 3)}",
                    triggered_by=top_symptoms,
                    contraindications=contraindications,
                    inputs_triggered=[],
                    source="cluster"
                )
                # Add explanation here:
                rec.explanation = build_explanation(rec)
                recommendations.append(rec)

    return recommendations
