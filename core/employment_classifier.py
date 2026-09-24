"""Employment-type classification with explicit negative-precedence rules."""

from dataclasses import dataclass
import re


_C2C_POSITIVE_RE = re.compile(
    r"\b(?:c2c|corp(?:oration)?[-\s]?(?:to|2)[-\s]?corp(?:oration)?|"
    r"corp2corp|1099|independent\s+contractor|subcontract(?:or)?)\b",
    re.IGNORECASE,
)
_CONTRACT_RE = re.compile(
    r"\b(?:contract(?:or|ing)?|c2h|contract[-\s]+to[-\s]+hire|freelance)\b",
    re.IGNORECASE,
)
_C2C_DENIAL_RE = re.compile(
    r"\b(?:no|not|without|cannot|can't|won't|do\s+not|does\s+not)\s+"
    r"(?:accept\s+|allow\s+|consider\s+|work\s+with\s+)?"
    r"(?:c2c|corp(?:oration)?[-\s]?(?:to|2)[-\s]?corp(?:oration)?|"
    r"third[-\s]?part(?:y|ies)|1099|subcontract(?:or)?s?)\b|"
    r"\b(?:c2c|1099|third[-\s]?part(?:y|ies))\s+(?:is\s+)?not\s+(?:accepted|allowed|available)\b",
    re.IGNORECASE,
)
_W2_ONLY_RE = re.compile(
    r"\b(?:w[-\s]?2\s*(?:only|exclusive)|only\s+(?:on\s+)?w[-\s]?2|"
    r"strictly\s+w[-\s]?2|must\s+be\s+(?:on\s+)?(?:our\s+)?w[-\s]?2|"
    r"(?:our|client)\s+w[-\s]?2\s+(?:only|required))\b",
    re.IGNORECASE,
)
_FULL_TIME_RE = re.compile(
    r"\b(?:full[-\s]?time|direct[-\s]?hire|permanent)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class EmploymentClassification:
    has_explicit_c2c: bool
    has_contract_language: bool
    denies_c2c: bool
    w2_only: bool
    full_time: bool

    @property
    def c2c_compatible(self) -> bool:
        if self.denies_c2c or self.w2_only:
            return False
        return self.has_explicit_c2c or self.has_contract_language


def classify_employment_text(text: str | None) -> EmploymentClassification:
    normalized = text or ""
    return EmploymentClassification(
        has_explicit_c2c=bool(_C2C_POSITIVE_RE.search(normalized)),
        has_contract_language=bool(_CONTRACT_RE.search(normalized)),
        denies_c2c=bool(_C2C_DENIAL_RE.search(normalized)),
        w2_only=bool(_W2_ONLY_RE.search(normalized)),
        full_time=bool(_FULL_TIME_RE.search(normalized)),
    )


def c2c_skip_reason(text: str | None, filter_employment_type: str = "ALL") -> str | None:
    result = classify_employment_text(text)
    requested = (filter_employment_type or "ALL").strip().upper()
    if result.denies_c2c:
        return "Job explicitly rejects C2C/third-party/1099 candidates"
    if result.w2_only:
        return "Job explicitly requires W2-only employment"
    if result.full_time and not result.c2c_compatible:
        return "Job is Full-Time/Direct-Hire without a compatible contract option"
    if requested in {"THIRD_PARTY", "CONTRACTS", "C2C"} and not result.c2c_compatible:
        return "Third-Party/Contract filter is active but no compatible contract option was found"
    return None
