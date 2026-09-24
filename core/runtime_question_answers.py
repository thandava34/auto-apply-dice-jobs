"""Only explicitly approved answers may enter a live Dice application form."""
from core.question_memory import normalize


def resolve_fields(memory, fields, scorer=None, allow_groq=True, job_title='', job_url='', budget=None, log=print):
    """Return approved answers only; similarity lookups belong in the review UI.

    Keep the existing signature for callers, but never infer or apply an
    unapproved association while processing a live application.
    """
    answers, managed = memory.for_fields(fields)
    if answers:
        log(f'[QUESTION] Reusing {len(answers)} previously approved field answer(s).')
    pending = {normalize(field.get('question', '')) for field in fields} - set(answers)
    pending.discard('')
    if pending:
        log(f'[QUESTION] {len(pending)} unapproved question(s) require review; no AI match will be filled during this application.')
    return answers, managed
