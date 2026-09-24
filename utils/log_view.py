"""Bounded display helpers; full disk logs are not modified."""
from pathlib import Path

MAX_VISIBLE_LINES = 2000
MAX_LOG_BYTES = 256 * 1024


def trim_log_widget(widget, max_lines=MAX_VISIBLE_LINES):
    lines = int(widget.index('end-1c').split('.')[0])
    if lines > max_lines:
        widget.delete('1.0', f'{lines - max_lines + 1}.0')


def read_log_tail(filename, limit=MAX_LOG_BYTES):
    with Path(filename).open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        content = stream.read(limit).decode('utf-8', errors='replace')
    if size > limit:
        content = '[Showing the latest log section; open the log folder for the complete file.]\n' + content
    return content
