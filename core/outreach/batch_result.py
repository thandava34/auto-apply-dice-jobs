"""Lightweight structured results; UI must not infer outcomes from log text."""
from dataclasses import dataclass


@dataclass
class BatchResult:
    selected: int = 0
    drafted: int = 0
    sent: int = 0
    failed: int = 0
    unconfirmed: int = 0
    skipped: int = 0
    deferred: int = 0
    stop_reason: str = 'Complete'

    def finish(self):
        self.deferred = max(0, self.selected - self.drafted - self.sent - self.failed - self.skipped - self.unconfirmed)
        return self

    def summary(self):
        return (f'Selected: {self.selected} | Drafted: {self.drafted} | Sent: {self.sent}\n'
                f'Failed: {self.failed} | Needs review: {self.unconfirmed} | Skipped: {self.skipped} | Deferred: {self.deferred}\n'
                f'Stop reason: {self.stop_reason}')
