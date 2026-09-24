"""OS-backed, process and thread safe locks. Lock files are never age-deleted."""
import hashlib
import os
from pathlib import Path
import threading
import time

_registry = {}
_guard = threading.Lock()


class ProcessLock:
    def __init__(self, resource, timeout=0):
        self.resource = os.path.normcase(str(Path(resource).resolve()))
        self.timeout = timeout
        with _guard:
            self.shared = _registry.setdefault(self.resource, [threading.RLock(), None, 0])

    def __enter__(self):
        local = self.shared[0]
        if not local.acquire(timeout=self.timeout):
            raise TimeoutError('Resource is in use: ' + self.resource)
        if self.shared[2]:
            self.shared[2] += 1
            return self
        stream = None
        try:
            path = Path(self.resource + '.lock')
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = open(path, 'a+b')
            # Windows permits locking a byte beyond EOF. Do not initialize
            # the file before locking: another process may already own byte 0.
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    stream.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Resource is in use: ' + self.resource)
                    time.sleep(.05)
            self.shared[1:] = [stream, 1]
            return self
        except BaseException:
            if stream:
                stream.close()
            local.release()
            raise

    def __exit__(self, *_):
        self.shared[2] -= 1
        if not self.shared[2]:
            self.shared[1].close()
            self.shared[1] = None
        self.shared[0].release()


def instance_lock(bot, directory):
    return ProcessLock(Path(directory).resolve() / (bot + '.instance'), timeout=0)
