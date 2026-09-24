"""Application outcome categories used by UI, persistence, and reporting."""

from enum import Enum


class ApplicationOutcome(str, Enum):
    APPLIED = "applied"
    ALREADY_APPLIED = "already_applied"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    UNCONFIRMED = "unconfirmed"
    FAILED = "failed"


def classify_application_outcome(applied: bool, reason: str | None) -> ApplicationOutcome:
    if applied:
        return ApplicationOutcome.APPLIED
    lowered = (reason or "").strip().lower()
    if "already applied" in lowered:
        return ApplicationOutcome.ALREADY_APPLIED
    if "unconfirmed" in lowered or "no success confirmation" in lowered:
        return ApplicationOutcome.UNCONFIRMED
    if any(token in lowered for token in ("required application questions", "resume upload failed")):
        return ApplicationOutcome.BLOCKED
    if any(token in lowered for token in ("skip", "external apply", "employment", "excluded keyword")):
        return ApplicationOutcome.SKIPPED
    return ApplicationOutcome.FAILED
