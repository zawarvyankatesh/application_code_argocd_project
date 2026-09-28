import unittest

from publish_gitops import updated_values


class UpdateValuesTest(unittest.TestCase):
    def setUp(self):
        self.original = (
            "imagePullSecrets:\n  - name: ecr-pull\n\n"
            "web:\n  image:\n    repository: old/taskboard-web\n"
            "    tag: ec180a260ddf\n    pullPolicy: IfNotPresent\n"
            "  autoscaling:\n    maxReplicas: 3\n\n"
            "api:\n  image:\n    repository: old/taskboard-api\n"
            "    tag: ec180a260ddf\n    pullPolicy: IfNotPresent\n\n"
            "redis:\n  image:\n    repository: old/taskboard-redis\n"
            "    tag: 7-alpine\n    pullPolicy: IfNotPresent\n"
            "  persistence:\n    enabled: true\n"
        )
        self.repos = {
            name: f"606075279047.dkr.ecr.ap-south-1.amazonaws.com/taskboard-{name}"
            for name in ("web", "api", "redis")
        }

    def test_updates_only_images_and_is_repeatable(self):
        updated = updated_values(self.original, self.repos, "abcdef123456")
        for name in ("web", "api", "redis"):
            self.assertIn(f"repository: {self.repos[name]}", updated)
        self.assertEqual(updated.count("tag: abcdef123456"), 2)
        self.assertIn("    tag: 7-alpine", updated)
        self.assertIn("    maxReplicas: 3", updated)
        self.assertIn("  persistence:\n    enabled: true", updated)
        self.assertEqual(updated, updated_values(updated, self.repos, "abcdef123456"))

    def test_refuses_partial_or_unconfigured_values(self):
        with self.assertRaises(ValueError):
            updated_values(self.original.replace("  - name: ecr-pull\n", ""), self.repos, "abcdef123456")
        with self.assertRaises(ValueError):
            updated_values(self.original.replace("    tag: 7-alpine\n", ""), self.repos, "abcdef123456")


if __name__ == "__main__":
    unittest.main()
