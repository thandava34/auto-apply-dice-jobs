"""Distinguish questions worth matching from fields that prevent submission."""
from core.dice_forms import REVIEW_FIELDS_JS


def approve_submission_review(driver, job_title):
    """Optional read-only form review; any review failure fails closed."""
    callback = getattr(driver, '_review_before_submit', None)
    if not callable(callback):
        return True
    from core.dice_forms import SUBMIT_REVIEW_JS
    try:
        fields = driver.execute_script(SUBMIT_REVIEW_JS) or []
        return bool(callback(job_title, fields))
    except Exception:
        return False


def blocking_fields(fields):
    """The scanner returns only blank or invalid controls; optional blanks may pass."""
    return [field for field in fields if field.get('required') is True or field.get('invalid') is True]


def wait_for_submission_result(driver, wait):
    """Observe one submission attempt. Never click or replay the external action."""
    def observe(browser):
        for by, selector in (
            ('css selector', '[data-testid="job-application-success-card"]'),
            ('xpath', '//header[contains(@class, "post-apply-banner")]//h1[contains(text(), "Application submitted")]'),
        ):
            if any(element.is_displayed() for element in browser.find_elements(by, selector)):
                return 'confirmed', []
        fields = browser.execute_script(REVIEW_FIELDS_JS) or []
        rejected = [field for field in fields if field.get('invalid') is True]
        if rejected:
            return 'validation_failed', rejected
        return False
    return wait.until(observe)
