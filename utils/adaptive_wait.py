"""Bounded readiness waiting; throttling and final confirmations stay separate."""
import time
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException


def until_ready(check, timeout, *, cancelled=lambda: False, interval=.2, stage='readiness', log=lambda *_: None):
    start = time.monotonic()
    try:
        while True:
            if cancelled() is True:
                raise InterruptedError('Cancelled while waiting for ' + stage)
            try:
                value = check()
                if value:
                    return value
            except (NoSuchElementException, StaleElementReferenceException):
                pass
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise TimeoutError('Timed out waiting for ' + stage)
            time.sleep(min(interval, remaining))
    finally:
        log(f'[Timing] {stage}: {time.monotonic() - start:.2f}s')
