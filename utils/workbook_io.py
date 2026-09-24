"""Atomic workbook replacement shared by both desktop applications."""
import os
from pathlib import Path
import tempfile
from utils.process_lock import ProcessLock


def write_frame(frame, filename):
    path = Path(filename).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with ProcessLock(path, timeout=10):
        fd, temporary = tempfile.mkstemp(suffix='.xlsx', dir=path.parent)
        os.close(fd)
        try:
            frame.to_excel(temporary, index=False)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

