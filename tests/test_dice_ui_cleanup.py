"""Offline regressions for the Dice cleanup and login consent polling."""
import unittest
from unittest.mock import Mock, patch
from selenium.webdriver.common.by import By


class DiceCleanupTests(unittest.TestCase):
    def test_analytics_removed_and_skips_unique_per_run(self):
        from app_tkinter import DiceAutoBotApp
        self.assertFalse(hasattr(DiceAutoBotApp, 'setup_analytics_tab'))
        self.assertFalse(hasattr(DiceAutoBotApp, '_compute_live_analytics'))
        app = object.__new__(DiceAutoBotApp)
        app.root = Mock()
        app.root.after.side_effect = lambda delay, callback: callback()
        app.jobs_skipped_label = Mock()
        app._record_skipped_job({'Job URL': 'https://dice.com/job/1/'})
        app._record_skipped_job({'Job URL': 'https://dice.com/job/1'})
        app._record_skipped_job({'Job URL': 'https://dice.com/job/2'})
        self.assertEqual(len(app._skipped_job_keys), 2)
        self.assertEqual(app.jobs_skipped_label.config.call_count, 2)
        app.jobs_skipped_label.config.assert_called_with(text='2')
        app._skipped_job_keys = set()
        app._record_skipped_job({'Job URL': 'https://dice.com/job/1'})
        app.jobs_skipped_label.config.assert_called_with(text='1')

    def test_login_control_checks_consent_on_each_readiness_poll(self):
        from core.dice_login import _login_control
        driver, wait, button = Mock(), Mock(), Mock()
        driver.find_element.return_value = button
        button.is_displayed.side_effect = [False, True]
        button.is_enabled.return_value = True
        def polling(predicate):
            self.assertFalse(predicate(driver))
            return predicate(driver)
        wait.until.side_effect = polling
        with patch('core.dice_login.accept_dice_cookies') as accept:
            self.assertIs(_login_control(driver, wait, (By.NAME, 'email')), button)
        self.assertEqual(accept.call_count, 2)
        accept.assert_called_with(driver, timeout=0)

    def test_accept_label_requires_cookie_container(self):
        from core.dice_consent import accept_dice_cookies
        driver = Mock(current_url='https://www.dice.com/dashboard/login')
        container, button = Mock(), Mock()
        container.is_displayed.return_value = True
        container.text = 'We use cookies on this site'
        button.text = ' I ACCEPT '
        button.is_displayed.return_value = button.is_enabled.return_value = True
        container.find_elements.return_value = [button]
        driver.find_elements.side_effect = lambda by, query: [container] if '[role="dialog"]' in query else []
        self.assertTrue(accept_dice_cookies(driver, timeout=0, log=lambda *_: None))
        button.click.assert_called_once()
        container.text = 'Accept job offer'
        self.assertFalse(accept_dice_cookies(driver, timeout=0))
        button.click.assert_called_once()
