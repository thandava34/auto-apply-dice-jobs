"""Tk-owned event pump: publishing from a worker never calls Tcl."""
from dataclasses import dataclass
from queue import Queue, Empty
import threading
import time


@dataclass(frozen=True)
class UiEvent:
    kind: str
    callback: object
    args: tuple = ()
    due: float = 0


class UiEvents:
    def __init__(self, root):
        self.root = root
        self.owner = threading.get_ident()
        self.queue = Queue()
        self.closed = False
        self.after = root.after
        self.handle = self.after(40, self._drain)
        root.bind('<Destroy>', self._destroyed, add='+')

    def publish(self, callback, *args, delay=0, kind='callback'):
        if not self.closed:
            self.queue.put(UiEvent(kind, callback, args, time.monotonic() + delay / 1000))

    def _drain(self):
        if self.closed:
            return
        later = []
        deadline = time.monotonic() + .012
        for _ in range(200):
            if time.monotonic() >= deadline:
                break
            try:
                event = self.queue.get_nowait()
            except Empty:
                break
            if event.due > time.monotonic():
                later.append(event)
                continue
            try:
                event.callback(*event.args)
            except Exception:
                import sys
                self.root.report_callback_exception(*sys.exc_info())
            if self.closed:
                return
        for event in later:
            self.queue.put(event)
        self.handle = self.after(40, self._drain)

    def _destroyed(self, event):
        if event.widget is self.root:
            self.close()

    def close(self):
        self.closed = True
        try:
            self.root.after_cancel(self.handle)
        except Exception:
            pass
        while not self.queue.empty():
            self.queue.get_nowait()


def install_ui_events(root):
    pump = UiEvents(root)
    original = root.after
    def schedule(ms, func=None, *args):
        if threading.get_ident() == pump.owner:
            return original(ms, func, *args)
        if func is None:
            raise RuntimeError('Worker threads cannot sleep through Tk')
        pump.publish(func, *args, delay=ms)
        return None
    root.after = schedule
    root.ui_events = pump
    return pump
