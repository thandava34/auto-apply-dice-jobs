import os
import tempfile
import unittest

from core.learning_engine import LearningEngine
from core.matcher import ResumeMatcher
from core.outreach.resume_picker import ResumePicker


class MatchingGuardTests(unittest.TestCase):
    def test_all_disqualified_profiles_returns_empty(self):
        matcher = ResumeMatcher([{
            "id": 1,
            "name": "AI Engineer",
            "keywords": ["python", "llm"],
            "unique_keywords": [],
            "must_have": ["langgraph"],
        }])
        self.assertEqual(matcher.score_profiles("Python LLM role", job_title="AI Engineer"), [])

    def test_minimum_absolute_fit_is_enforced(self):
        matcher = ResumeMatcher([{
            "id": 1,
            "name": "Data Engineer",
            "keywords": ["python"],
            "unique_keywords": [],
        }])
        result = matcher.score_profiles(
            "Python, Kubernetes, Terraform, Java and React",
            job_title="Data Engineer",
            minimum_ats_fit=50,
        )
        self.assertEqual(result, [])

    def test_confidence_is_absolute_not_winner_relative(self):
        matcher = ResumeMatcher([{
            "id": 1,
            "name": "Engineer",
            "keywords": ["python"],
            "unique_keywords": [],
        }])
        result = matcher.score_profiles("Python Java Terraform", job_title="Engineer")
        self.assertTrue(result)
        self.assertEqual(result[0]["confidence_pct"], result[0]["ats_score"])
        self.assertLess(result[0]["confidence_pct"], 100.0)


class LearningCacheTests(unittest.TestCase):
    def test_record_success_invalidates_boost_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = LearningEngine(os.path.join(directory, "learning.db"))
            try:
                self.assertEqual(engine.get_similarity_boost(1, "Data Engineer"), 0.0)
                engine.record_success(1, "Data Engineer", "python", source="manual")
                self.assertGreater(engine.get_similarity_boost(1, "Data Engineer"), 0.0)
            finally:
                engine.close()


class OutreachResumePickerTests(unittest.TestCase):
    def test_no_eligible_match_does_not_fall_back_to_first_profile(self):
        picker = ResumePicker([{"id": "one", "name": "Profile One"}])
        picker._semantic_initialized = True

        class NoMatch:
            @staticmethod
            def score_profiles(*args, **kwargs):
                return []

        picker.matcher = NoMatch()
        self.assertIsNone(picker.pick_resume("Unrelated Role", "Unrelated description"))


if __name__ == "__main__":
    unittest.main()
