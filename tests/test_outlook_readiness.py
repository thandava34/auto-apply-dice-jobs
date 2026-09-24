from unittest.mock import MagicMock, patch
from core.outreach.email_engine import EmailEngine


def test_ready_skips_hidden_first_match():
    driver, hidden, visible = MagicMock(), MagicMock(), MagicMock()
    hidden.is_displayed.return_value = False
    visible.is_displayed.return_value = True
    visible.is_enabled.return_value = True
    driver.find_elements.return_value = [hidden, visible]
    assert EmailEngine._outlook_ready_button(driver, '//button', .1) is visible


def test_outlook_startup_eager_and_timeout_continues_to_readiness():
    from selenium.common.exceptions import TimeoutException
    driver = MagicMock()
    driver.get.side_effect = TimeoutException()
    original = EmailEngine._web_driver, EmailEngine._web_driver_provider
    EmailEngine._web_driver = None
    try:
        with patch('selenium.webdriver.Chrome', return_value=driver) as chrome, \
             patch('webdriver_manager.chrome.ChromeDriverManager') as manager:
            manager.return_value.install.return_value = 'test-driver'
            assert EmailEngine._get_web_driver('outlook_web', 'https://outlook.office.com/mail/', log_fn=lambda _: None) is driver
            assert chrome.call_args.kwargs['options'].page_load_strategy == 'eager'
            driver.set_page_load_timeout.assert_called_once_with(30)
            assert EmailEngine._get_web_driver('outlook_web', 'unused', log_fn=lambda _: None) is driver
            chrome.assert_called_once()
    finally:
        EmailEngine._web_driver, EmailEngine._web_driver_provider = original
