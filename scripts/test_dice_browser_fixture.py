"""Offline Chrome test. Run as a module with explicit --browser and --driver paths."""
import argparse
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from core.dice_forms import ANSWER_MATCHER_JS, WIZARD_SCAN_JS, REVIEW_FIELDS_JS
from core.dice_consent import accept_dice_cookies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', required=True)
    parser.add_argument('--driver', required=True)
    args = parser.parse_args()
    options = webdriver.ChromeOptions()
    options.binary_location = args.browser
    options.add_argument('--headless=new')
    options.add_argument('--disable-background-networking')
    driver = webdriver.Chrome(service=Service(args.driver), options=options)
    try:
        driver.get('data:text/html;charset=utf-8,' + quote('''
        <html><body>
        <div id="onetrust-banner-sdk">Cookies <button id="onetrust-accept-btn-handler"
          onclick="this.parentElement.remove()">Accept all cookies</button></div>
        <button id="unrelated" onclick="this.dataset.clicked='yes'">Accept</button>
        <form>
        <label for="python">Years of Python experience</label><input id="python" type="number" required>
        <label for="kube">Years of Kubernetes experience</label><input id="kube" type="number" required>
        <label for="work">Work setting?</label><select id="work" required>
        <option value="">Select</option><option>Remote</option><option>Hybrid</option></select>
        <fieldset><legend>Do you require sponsorship?</legend>
        <input id="no" name="sponsor" type="radio" value="No" required><label for="no">No</label>
        <input id="na" name="sponsor" type="radio" value="Not applicable"><label for="na">Not applicable</label>
        </fieldset></form></body></html>'''))
        class FixtureDomain:
            # Only the URL guard is simulated; actual clicks run in the offline browser.
            current_url = 'https://www.dice.com/dashboard/login'
            find_elements = driver.find_elements
        assert accept_dice_cookies(FixtureDomain(), timeout=1)
        assert not driver.find_elements(By.ID, 'onetrust-accept-btn-handler')
        assert driver.find_element(By.ID, 'unrelated').get_attribute('data-clicked') is None
        driver.execute_script(ANSWER_MATCHER_JS)
        answers = {'years of experience': '8', 'years of python experience': '3',
                   'work setting?': 'Remote', 'do you require sponsorship?': 'No'}
        missed = driver.execute_script(WIZARD_SCAN_JS, answers)
        assert any('Kubernetes' in x for x in missed), missed
        assert driver.find_element(By.ID, 'python').get_attribute('data-dice-fill') == '3'
        assert driver.find_element(By.ID, 'kube').get_attribute('data-dice-fill') is None
        driver.find_element(By.ID, 'python').send_keys('3')
        Select(driver.find_element(By.ID, 'work')).select_by_visible_text('Remote')
        for el in driver.find_elements(By.CSS_SELECTOR, '[data-dice-click]'):
            el.click()
        assert driver.find_element(By.ID, 'no').is_selected()
        assert not driver.find_element(By.ID, 'na').is_selected()
        review = driver.execute_script(REVIEW_FIELDS_JS)
        assert any(r['question'] == 'Years of Kubernetes experience' for r in review), review
        assert not any(r['question'] == 'Work setting?' for r in review), review
        driver.find_element(By.ID, 'kube').send_keys('2')
        assert driver.execute_script(REVIEW_FIELDS_JS) == []
        print('PASS: cookie targeting, saved-answer handoff, specific matching, exact radio choice, post-fill validation')
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
