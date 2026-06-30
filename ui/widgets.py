import tkinter as tk
from tkinter import ttk

from .theme import (ACCENT, BG, BORDER, BTN_BG, BTN_HOV, ENTRY_BG, GREEN_HOV, GREEN_BTN,
                    PANEL, SUBTEXT, TEXT)


def apply_style(root):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
    style.configure("Sub.TLabel", background=PANEL, foreground=SUBTEXT, font=("Segoe UI", 9))
    style.configure("Head.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 13, "bold"))
    style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 10), indicatorcolor=ACCENT)
    style.map("TCheckbutton", background=[("active", PANEL)])
    style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=TEXT, insertcolor=TEXT,
                    bordercolor=BORDER, relief="flat", font=("Segoe UI", 10))
    style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG, arrowcolor=SUBTEXT, bordercolor=BG)
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=BTN_BG, foreground=SUBTEXT,
                    borderwidth=0, padding=(16, 7), font=("Segoe UI", 9))
    style.map("TNotebook.Tab",
              background=[("selected", ENTRY_BG), ("active", BTN_HOV)],
              foreground=[("selected", TEXT), ("active", TEXT)])
    style.layout("TNotebook.Tab", [
        ("Notebook.tab", {
            "sticky": "nswe",
            "children": [
                ("Notebook.padding", {
                    "side": "top",
                    "sticky": "nswe",
                    "children": [
                        ("Notebook.label", {"side": "top", "sticky": ""})
                    ],
                })
            ],
        })
    ])


def create_button(parent, text, cmd, row=None, color=BTN_BG, text_color=TEXT,
                  big=False, side=None, small=False):
    font_size = 11 if big else (9 if small else 10)
    weight = "bold" if big else "normal"
    pady_val = 10 if big else (4 if small else 7)
    btn = tk.Button(parent, text=text, command=cmd, bg=color, fg=text_color,
                    relief="flat", cursor="hand2", font=("Segoe UI", font_size, weight),
                    activebackground=BTN_HOV, activeforeground=text_color,
                    pady=pady_val, padx=12, bd=0)
    hover_bg = BTN_HOV if color == BTN_BG else color
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
    btn.bind("<Leave>", lambda e: btn.config(bg=color))
    if side:
        btn.pack(side=side, padx=(0, 8))
    else:
        btn.grid(row=row, column=0, sticky="ew", pady=(2, 0))
    return btn


def create_section(parent, title, row):
    ttk.Label(parent, text=title, style="Head.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 4))


def create_info_row(parent, label, default, row):
    f = tk.Frame(parent, bg=ENTRY_BG, padx=10, pady=6)
    f.grid(row=row, column=0, sticky="ew", pady=2)
    tk.Label(f, text=label, bg=ENTRY_BG, fg=SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w")
    lbl = tk.Label(f, text=default, bg=ENTRY_BG, fg=TEXT,
                   font=("Segoe UI", 9), wraplength=260, anchor="w", justify="left")
    lbl.pack(anchor="w")
    return lbl


def create_scrollable_frame(parent):
    wrapper = tk.Frame(parent, bg="#0f1117")
    wrapper.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    wrapper.columnconfigure(0, weight=1)
    wrapper.rowconfigure(0, weight=1)

    canvas = tk.Canvas(wrapper, bg="#0f1117", highlightthickness=0, bd=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    vsb = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
    vsb.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=vsb.set)

    inner = ttk.Frame(canvas, style="TFrame")
    inner.columnconfigure(0, weight=1)
    inner_win = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfig(inner_win, width=event.width)

    inner.bind("<Configure>", _on_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    return wrapper, canvas, inner
