"""Narrow, repeatable cookie-banner handling for Dice pages."""
from urllib.parse import urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException


def is_dice_url(url):
    host = (urlparse(url).hostname or '').lower()
    return host == 'dice.com' or host.endswith('.dice.com')


def accept_dice_cookies(driver, timeout=2, log=print):
    if not is_dice_url(driver.current_url):
        return False

    def accept(d):
        if not is_dice_url(d.current_url):
            return False
        # Known consent platforms; no page-wide generic 'Accept' click.
        selectors = (
            '#onetrust-accept-btn-handler',
            '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
            '[data-testid="cookie-accept-all"]',
        )
        for selector in selectors:
            for button in d.find_elements(By.CSS_SELECTOR, selector):
                if button.is_displayed() and button.is_enabled():
                    button.click()
                    return True
        for container in d.find_elements(By.CSS_SELECTOR,
                '[role="dialog"], [id*="cookie"], [id*="consent"], [class*="cookie-banner"]'):
            if not container.is_displayed() or 'cookie' not in container.text.lower():
                continue
            for button in container.find_elements(By.CSS_SELECTOR, 'button, [role="button"]'):
                if ' '.join(button.text.lower().split()) in {'accept', 'i accept', 'accept all', 'accept cookies', 'accept all cookies', 'allow all'}:
                    if button.is_displayed() and button.is_enabled():
                        button.click()
                        return True
        return False

    try:
        accepted = WebDriverWait(driver, timeout, poll_frequency=0.25,
                                  ignored_exceptions=(WebDriverException,)).until(accept)
        if accepted:
            log('[Dice] Cookie consent accepted.')
        return bool(accepted)
    except TimeoutException:
        return False


def dice_login_confirmed(driver):
    """Require account UI evidence; public search pages are not login evidence."""
    if not is_dice_url(driver.current_url):
        return False
    path = urlparse(driver.current_url).path.lower()
    if any(part in path for part in ('login', 'sign-in', 'signin', 'register')):
        return False
    return any(el.is_displayed() for el in driver.find_elements(By.CSS_SELECTOR,
        '[data-testid="nav-profile-link"], [data-testid="sign-out-button"], '
        'a[href*="/dashboard/profile"], a[href*="/logout"], button[aria-label="Sign out"]'))
