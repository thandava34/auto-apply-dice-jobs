"""Safe handling for application-wizard answers.

Only answers explicitly supplied by the user are eligible for form filling.
This module intentionally contains no candidate identity or legal-status defaults.
"""

from collections.abc import Mapping


SENSITIVE_QUESTION_TOKENS = (
    "citizen", "citizenship", "green card", "permanent resident",
    "authorized", "authorization", "eligible", "visa", "sponsor",
    "clearance", "disability", "veteran", "gender", "race", "ethnicity",
    "felony", "convicted", "background check", "drug test",
)

# These are question-pattern suggestions only. They intentionally contain no
# candidate answers: selecting a pattern never makes a claim on the user's behalf.
APPLICATION_QUESTION_CATALOG = {
    "Work authorization": (
        "work authorization", "authorized to work", "legally authorized",
        "employment eligibility",
    ),
    "Visa and sponsorship": (
        "visa sponsorship", "require sponsorship", "sponsorship now or later",
    ),
    "Compensation": (
        "salary expectation", "expected salary", "desired salary", "rate expectation",
    ),
    "Experience": (
        "years of relevant experience", "years of experience", "how many years",
        "describe your experience",
    ),
    "Availability": (
        "preferred start date", "start date", "notice period", "currently employed",
    ),
    "Location and work setting": (
        "willing to relocate", "relocation", "remote", "work from home",
    ),
    "Employment preferences": (
        "employment type", "work type", "job type", "overtime",
    ),
    "Application narrative": (
        "tell us about yourself", "why are you a good fit", "suitable candidate",
        "cover letter",
    ),
    "Compliance and voluntary disclosure": (
        "background check", "drug test", "security clearance", "veteran status",
        "disability status",
    ),
}


def application_question_catalog_items() -> list[tuple[str, str]]:
    """Return sorted (category, pattern) suggestions without answers."""
    return [
        (category, pattern)
        for category, patterns in APPLICATION_QUESTION_CATALOG.items()
        for pattern in patterns
    ]


def normalize_application_answers(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    answers: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip().lower()
        answer = str(raw_value).strip() if raw_value is not None else ""
        if key and answer:
            answers[key] = answer
    return answers


def is_sensitive_question(label: str) -> bool:
    lowered = (label or "").lower()
    return any(token in lowered for token in SENSITIVE_QUESTION_TOKENS)


def may_generate_answer(label: str, allow_generated_answers: bool) -> bool:
    return bool(allow_generated_answers) and not is_sensitive_question(label)
