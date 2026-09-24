import unittest

from core.application_answers import (
    APPLICATION_QUESTION_CATALOG,
    application_question_catalog_items,
    is_sensitive_question,
    may_generate_answer,
    normalize_application_answers,
)
from core.application_outcome import ApplicationOutcome, classify_application_outcome
from core.employment_classifier import classify_employment_text, c2c_skip_reason


class EmploymentClassifierTests(unittest.TestCase):
    def test_no_c2c_overrides_contract_word(self):
        result = classify_employment_text("Six month contract. No C2C or third parties.")
        self.assertTrue(result.denies_c2c)
        self.assertFalse(result.c2c_compatible)

    def test_w2_only_overrides_contract_word(self):
        result = classify_employment_text("Contract W2 only")
        self.assertTrue(result.w2_only)
        self.assertFalse(result.c2c_compatible)

    def test_explicit_c2c_is_compatible(self):
        self.assertIsNone(c2c_skip_reason("12 month C2C contract", "C2C"))

    def test_contract_filter_rejects_missing_contract_terms(self):
        self.assertIsNotNone(c2c_skip_reason("Software Engineer", "CONTRACTS"))


class ApplicationAnswerTests(unittest.TestCase):
    def test_question_catalog_contains_patterns_but_no_default_answers(self):
        items = application_question_catalog_items()
        self.assertIn(("Work authorization", "work authorization"), items)
        self.assertTrue(all(isinstance(patterns, tuple) for patterns in APPLICATION_QUESTION_CATALOG.values()))

    def test_only_explicit_non_empty_answers_survive(self):
        self.assertEqual(
            normalize_application_answers({" ZIP Code ": " 12345 ", "visa": ""}),
            {"zip code": "12345"},
        )

    def test_ai_never_answers_sensitive_question(self):
        self.assertTrue(is_sensitive_question("Will you need visa sponsorship?"))
        self.assertFalse(may_generate_answer("Will you need visa sponsorship?", True))
        self.assertFalse(may_generate_answer("Describe your project", False))


class ApplicationOutcomeTests(unittest.TestCase):
    def test_already_applied_is_not_success(self):
        outcome = classify_application_outcome(False, "Already applied previously")
        self.assertEqual(outcome, ApplicationOutcome.ALREADY_APPLIED)

    def test_unconfirmed_is_not_success(self):
        outcome = classify_application_outcome(False, "Submission unconfirmed")
        self.assertEqual(outcome, ApplicationOutcome.UNCONFIRMED)


if __name__ == "__main__":
    unittest.main()
