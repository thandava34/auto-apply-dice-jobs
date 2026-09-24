import json
import os
import tempfile
import unittest

from utils.config_manager import ConfigManager


class ConfigManagerTests(unittest.TestCase):
    def test_defaults_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ConfigManager(config_dir=directory)
            self.assertFalse(manager.get("auto_answer_questions"))
            self.assertFalse(manager.get("allow_ai_generated_application_answers"))
            self.assertEqual(manager.get("application_answers"), {})

    def test_invalid_types_are_repaired_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "settings.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({
                    "search_queries": "not-a-list",
                    "job_application_limit": "bad",
                    "minimum_ats_fit": 500,
                    "application_answers": [],
                }, handle)
            manager = ConfigManager(config_dir=directory)
            self.assertIsInstance(manager.get("search_queries"), list)
            self.assertEqual(manager.get("job_application_limit"), 50)
            self.assertEqual(manager.get("minimum_ats_fit"), 100.0)
            self.assertEqual(manager.get("application_answers"), {})

    def test_save_produces_valid_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = ConfigManager(config_dir=directory)
            self.assertTrue(manager.set("minimum_ats_fit", 40))
            with open(os.path.join(directory, "settings.json"), encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertEqual(saved["minimum_ats_fit"], 40.0)


if __name__ == "__main__":
    unittest.main()
