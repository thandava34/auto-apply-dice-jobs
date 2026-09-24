import unittest

from core.application_answers import may_generate_answer, normalize_application_answers
from core.application_outcome import ApplicationOutcome, classify_application_outcome
from core.employment_classifier import c2c_skip_reason
from core.matcher import ResumeMatcher


class DiceDecisionFlowIntegrationTests(unittest.TestCase):
    def test_eligible_job_selects_resume_and_accepts_only_explicit_sensitive_answer(self):
        job_title = "Contract Data Engineer"
        description = "C2C contract role requiring Python, Airflow and ETL."
        self.assertIsNone(c2c_skip_reason(description, "C2C"))

        matcher = ResumeMatcher([{
            "id": "data",
            "name": "Data Engineer",
            "keywords": ["python", "airflow", "etl"],
            "unique_keywords": ["airflow"],
            "must_have": ["python"],
        }])
        matches = matcher.score_profiles(
            f"{job_title}\n{description}",
            job_title=job_title,
            minimum_ats_fit=25,
        )
        self.assertEqual(matches[0]["id"], "data")

        answers = normalize_application_answers({"work authorization": "User supplied answer"})
        self.assertEqual(answers["work authorization"], "User supplied answer")
        self.assertFalse(may_generate_answer("Will you require visa sponsorship?", True))
        self.assertEqual(
            classify_application_outcome(True, "Submission confirmed"),
            ApplicationOutcome.APPLIED,
        )

    def test_negative_employment_and_unanswered_required_question_block_flow(self):
        reason = c2c_skip_reason("W2 only. No C2C or third parties.", "C2C")
        self.assertIn("rejects C2C", reason)
        self.assertEqual(
            classify_application_outcome(False, "Required application questions remain unanswered"),
            ApplicationOutcome.BLOCKED,
        )


if __name__ == "__main__":
    unittest.main()
