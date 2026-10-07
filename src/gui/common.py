"""Small helpers shared by every part of the Tkinter interface.

Nothing here knows about trees: the windows only show what
Observatory.state_view() returns and call Observatory methods.
"""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

# data/ folder of the project, used as the first folder of the file dialogs
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Colour rule: priority = blue / amber / violet. RED is only for "acceso costoso".
PRIORITY_COLORS = {1: "#6f93b8", 2: "#e0a526", 3: "#8a3fb5"}
PRIORITY_NAMES = {1: "Baja", 2: "Media", 3: "Alta"}
STATE_NAMES = {"ACTIVE": "Activo", "ARCHIVED": "Archivado", "DELETED": "Eliminado"}
COSTLY_COLOR = "#d62828"
MOVED_COLOR = "#16b3c9"
UNBALANCED_COLOR = "#ef6c00"
OK_COLOR = "#e3f1e3"
ERROR_COLOR = "#f8dedc"
PAPER = "#f6f3ec"


def sis(event_id):
    """10 -> 'SIS-000010'."""
    return "SIS-" + str(event_id).zfill(6)


def one_decimal(number):
    return "{:.1f}".format(float(number))


def to_iso(text):
    """Accept '2026-09-07 10:00', '2026-09-07T10:00:00' or the full ISO text with Z."""
    clean = str(text).strip().replace(" ", "T")
    if clean == "":
        return ""
    if clean.endswith("Z") or clean.endswith("z"):
        clean = clean[:-1]
    if len(clean) == 16:          # without seconds
        clean += ":00"
    return clean + "Z"


def show_date(iso_text):
    """'2026-09-07T10:00:00Z' -> '2026-09-07 10:00:00' (easier to type)."""
    return iso_text.replace("T", " ").replace("Z", "")


def labeled_entry(parent, row, column, text, width=12, value=""):
    """A label with an entry below it, placed in a grid. Returns the entry."""
    ttk.Label(parent, text=text).grid(row=row, column=column, sticky="w", padx=4, pady=(4, 0))
    entry = ttk.Entry(parent, width=width)
    entry.grid(row=row + 1, column=column, sticky="we", padx=4, pady=(0, 4))
    if value != "":
        entry.insert(0, value)
    return entry


def set_entry(entry, value):
    entry.delete(0, tk.END)
    entry.insert(0, str(value))


def make_table(parent, columns, height=8):
    """A ttk.Treeview used as a simple table. columns = [(title, width), ...]."""
    frame = ttk.Frame(parent)
    names = ["c" + str(i) for i in range(len(columns))]
    table = ttk.Treeview(frame, columns=names, show="headings", height=height)
    for name, (title, width) in zip(names, columns):
        table.heading(name, text=title)
        table.column(name, width=width, anchor="w", stretch=True)
    scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    table.frame = frame
    return table


def fill_table(table, rows, ids=None):
    """Replace every row. ids (optional) are kept as row names, e.g. the event id."""
    table.delete(*table.get_children())
    for index, row in enumerate(rows):
        name = str(ids[index]) if ids is not None else ""
        if name and not table.exists(name):
            table.insert("", "end", iid=name, values=row)
        else:
            table.insert("", "end", values=row)


EVENT_COLUMNS = [("ID", 95), ("Clave K", 110), ("Prioridad", 70), ("M", 45),
                 ("H km", 55), ("Estado", 75), ("Atención", 75)]


def event_row(event, extra=()):
    """One table row for an event; extra = names of more fields to show."""
    key = event["key"]
    row = [
        sis(event["id"]),
        "(" + str(key[0]) + ", " + one_decimal(key[1]) + ", " + str(key[2]) + ")",
        PRIORITY_NAMES[event["priority"]],
        one_decimal(event["magnitude"]),
        one_decimal(event["depth"]),
        STATE_NAMES.get(event.get("state", "ACTIVE"), ""),
        "Pendiente" if event.get("attention") == "PENDING" else "Revisado",
    ]
    for name in extra:
        value = event.get(name)
        row.append("—" if value is None else value)
    return row


class ScrollFrame(ttk.Frame):
    """A frame with a vertical scrollbar. Put the widgets inside self.inner."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=PAPER)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, padding=6)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        # The inner frame always uses the full width
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        # Mouse wheel scrolls only while the pointer is over this frame
        self.inner.bind("<Enter>", lambda e: self._wheel(True))
        self.inner.bind("<Leave>", lambda e: self._wheel(False))

    def _wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
            self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
            self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        else:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120) or (-1 if event.delta > 0 else 1), "units")


def section(parent, title, hint=None):
    """A titled box (LabelFrame) with an optional grey explanation."""
    box = ttk.LabelFrame(parent, text=title, padding=6)
    box.pack(fill="x", pady=5)
    if hint:
        ttk.Label(box, text=hint, foreground="#6b7180", wraplength=520, justify="left").pack(anchor="w")
    return box


def text_box(parent, height=6):
    """Read-only multi-line text with a scrollbar, for long results."""
    frame = ttk.Frame(parent)
    text = tk.Text(frame, height=height, wrap="word", relief="flat", background="#fffdf8",
                   font=("TkDefaultFont", 9))
    scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set, state="disabled")
    text.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    text.frame = frame
    return text


def write_text(text, content):
    text.configure(state="normal")
    text.delete("1.0", tk.END)
    text.insert("1.0", content)
    text.configure(state="disabled")
