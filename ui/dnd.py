try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    TkinterDnD = None
    DND_FILES = None
    _DND_AVAILABLE = False


def parse_drop_data(root, data: str) -> list:
    try:
        return list(root.tk.splitlist(data))
    except Exception:
        return []


def bind_drop(widget, root, on_drop, highlight_widget=None):
    if not _DND_AVAILABLE:
        return False
    hw = highlight_widget or widget
    widget.drop_target_register(DND_FILES)
    widget.dnd_bind("<<Drop>>", on_drop)
    widget.dnd_bind("<<DragEnter>>", lambda e: hw.config(background="#1e2a3a"))
    widget.dnd_bind("<<DragLeave>>", lambda e: hw.config(background=widget.cget("background") if widget is not None else ""))
    return True
