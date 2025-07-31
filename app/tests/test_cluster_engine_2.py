from pathlib import Path
import unittest
from app.cluster_engine import ClusterEngine, generate_cluster_protocol
from app.data_model import UserProfile

class TestClusterEngine(unittest.TestCase):
    def setUp(self):
        # Create some mock users with varying symptoms and ages
        self.users = [
            UserProfile(user_id="u1", age=25, gender="female", symptoms=["fatigue"], lifestyle={}, medical_conditions=[], medications=[], blood_tests=[], wearable_data=None, feedback=None),
            UserProfile(user_id="u2", age=30, gender="female", symptoms=["brain fog"], lifestyle={}, medical_conditions=[], medications=[], blood_tests=[], wearable_data=None, feedback=None),
            UserProfile(user_id="u3", age=40, gender="male", symptoms=["fatigue", "low energy"], lifestyle={}, medical_conditions=[], medications=[], blood_tests=[], wearable_data=None, feedback=None),
        ]
        self.cluster_engine = ClusterEngine(n_clusters=2)

    def test_fit_and_assign(self):
        self.cluster_engine.fit(self.users)
        self.assertTrue(self.cluster_engine.fitted)
        # Test cluster assignment for a user
        cluster_id = self.cluster_engine.assign_cluster(self.users[0])
        self.assertIn(cluster_id, range(self.cluster_engine.n_clusters))

    def test_generate_cluster_protocol(self):
        protocol = generate_cluster_protocol(self.users)
        self.assertIsInstance(protocol, list)
        self.assertGreater(len(protocol), 0)
        for rec in protocol:
            self.assertTrue(hasattr(rec, "name"))
            self.assertTrue(hasattr(rec, "dosage"))

    def test_distance_functions(self):
        self.cluster_engine.fit(self.users)
        dist = self.cluster_engine.distance_to_centroid(self.users[0])
        self.assertIsInstance(dist, float)
        dists = self.cluster_engine.distance_to_all_centroids(self.users[0])
        self.assertIsInstance(dists, list)
        self.assertEqual(len(dists), self.cluster_engine.n_clusters)

if __name__ == "__main__":
    unittest.main()