"""One Tcl/Tk interpreter per test process; independent class windows."""
import atexit
import tkinter as tk

_root = None


def create_test_host():
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()
        atexit.register(_root.destroy)
    host = tk.Toplevel(_root)
    host.withdraw()
    return host
