"""Main window of SismoLab AVL (Tkinter).

How every action works:
1. a button calls a method of a tab (create, step, ...);
2. that method calls the Observatory (the business facade);
3. app.run(result) shows the answer in "Qué pasó" and calls refresh();
4. refresh() asks obs.state_view() and redraws the trees, the map and every tab.

The window never touches the trees: it only reads state_view() and calls
Observatory methods. That is the separation between GUI and business.
"""

import tkinter as tk
from tkinter import ttk

from ..services.observatory import Observatory
from .common import ERROR_COLOR, OK_COLOR, PAPER
from .node_panel import NodePanel
from .tab_audit import AuditTab
from .tab_events import EventsTab
from .tab_files import FilesTab
from .tab_history import HistoryTab
from .tab_map import MapTab
from .tab_queries import ComparisonTab, QueriesTab
from .tab_queue import QueueTab
from .tree_view import TreeView


class SismoLabApp(tk.Tk):

    def __init__(self, observatory=None):
        super().__init__()
        self.obs = observatory if observatory is not None else Observatory()
        self.view = None          # last obs.state_view()
        self.selected = None      # id of the selected event
        self.last_clock = None

        self.title("SismoLab AVL — observatorio sísmico simulado")
        self.geometry("1440x880")
        self.minsize(1100, 700)
        self.configure(background=PAPER)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self._build_top_bar()
        self._build_body()
        self.bind("<Control-z>", lambda e: self.undo())
        self.refresh()
        self.show_message({"ok": True, "message": self.obs.last_action["message"], "details": None})

    # ---------------------------------------------------------------- layout

    def _build_top_bar(self):
        bar = tk.Frame(self, background="#0f6e6e", padx=10, pady=6)
        bar.pack(fill="x")
        tk.Label(bar, text="SismoLab AVL", font=("TkDefaultFont", 14, "bold"),
                 background="#0f6e6e", foreground="white").pack(side="left")
        self.mode_label = tk.Label(bar, text="", font=("TkDefaultFont", 10, "bold"), padx=8)
        self.mode_label.pack(side="left", padx=12)
        self.status_label = tk.Label(bar, text="", background="#0f6e6e", foreground="white")
        self.status_label.pack(side="left")
        self.undo_button = ttk.Button(bar, text="Deshacer (Ctrl+Z)", command=self.undo)
        self.undo_button.pack(side="right")

        # "Qué pasó": result of the last action
        self.message = tk.Label(self, text="", anchor="w", justify="left", padx=10, pady=6,
                                wraplength=1380, font=("TkDefaultFont", 10))
        self.message.pack(fill="x")

    def _build_body(self):
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(body)
        self.tree_view = TreeView(left, self.select)
        self.tree_view.pack(fill="both", expand=True)
        self.node_panel = NodePanel(left, self)
        self.node_panel.pack(fill="x", pady=(6, 0))
        body.add(left, weight=3)

        self.notebook = ttk.Notebook(body)
        self.events_tab = EventsTab(self.notebook, self)
        self.queue_tab = QueueTab(self.notebook, self)
        self.queries_tab = QueriesTab(self.notebook, self)
        self.comparison_tab = ComparisonTab(self.notebook, self)
        self.map_tab = MapTab(self.notebook, self)
        self.history_tab = HistoryTab(self.notebook, self)
        self.audit_tab = AuditTab(self.notebook, self)
        self.files_tab = FilesTab(self.notebook, self)
        for tab, name in ((self.events_tab, "Eventos"), (self.queue_tab, "Cola y estrés"),
                          (self.queries_tab, "Consultas"), (self.comparison_tab, "AVL vs BST"),
                          (self.map_tab, "Mapa"), (self.history_tab, "Historial"),
                          (self.audit_tab, "Auditoría"), (self.files_tab, "Archivos")):
            self.notebook.add(tab, text=name)
        body.add(self.notebook, weight=2)

    def show_tab(self, tab):
        self.notebook.select(tab)

    # ---------------------------------------------------------------- actions

    def run(self, result):
        """Show the result of an action and redraw everything. Returns the result."""
        self.show_message(result)
        self.refresh()
        return result

    def undo(self):
        self.run(self.obs.undo())

    def select(self, event_id):
        """Select an event (click in the tree, the map or a table)."""
        self.selected = event_id
        self.tree_view.show(self.view, self.selected)
        self.map_tab.draw()
        self.node_panel.show(event_id)

    def show_message(self, result):
        """Box "Qué pasó": green when it worked, red when it was rejected."""
        details = result.get("details") or {}
        lines = [("Qué pasó: " if result["ok"] else "No se aplicó: ") + result["message"]]
        if result["ok"] and details.get("rotation_text"):
            line = "Rotaciones: " + details["rotation_text"]
            moved = details.get("moved") or []
            if moved:
                line += " · Nodos movidos: " + ", ".join(str(i) for i in moved[:25])
                line += "…" if len(moved) > 25 else ""
            lines.append(line)
        if details.get("old_key"):
            lines.append("Clave anterior " + details["old_key"] + " -> nueva " + details["new_key"]
                         + (" (se retiró y reinsertó el nodo)" if details["key_changed"] else " (el nodo no se movió)"))
        problems = details.get("problems") or []
        for problem in problems[:8]:
            lines.append("- " + str(problem))
        if len(problems) > 8:
            lines.append("… y " + str(len(problems) - 8) + " problema(s) más")
        self.message.configure(text="\n".join(lines), background=OK_COLOR if result["ok"] else ERROR_COLOR)

    # ---------------------------------------------------------------- redraw

    def refresh(self):
        view = self.obs.state_view()
        self.view = view

        # Top bar
        stress = view["mode"] == "STRESS"
        self.mode_label.configure(text="Modo estrés" if stress else "Modo normal",
                                  background="#ef6c00" if stress else "#d8eeec",
                                  foreground="white" if stress else "#0f6e6e")
        p = view["parameters"]
        ind = view["indicators"]
        self.status_label.configure(
            text="Reloj: " + view["clock"].replace("T", " ").replace("Z", " UTC")
            + "   ·   Activos " + str(ind["active"]) + " · Archivados " + str(ind["archived"])
            + " · Cola " + str(len(view["queue"]))
            + "   ·   W=" + str(p["W"]) + " h · R=" + str(p["R"]) + " km · L=" + str(p["L"]) + " · T=" + str(p["T"]) + " h")
        self.undo_button.state(["!disabled"] if view["undo"]["available"] else ["disabled"])

        # When the clock changes (advance, load, undo...), the date fields start at the new clock
        if view["clock"] != self.last_clock:
            self.last_clock = view["clock"]
            for tab in (self.events_tab, self.queue_tab, self.queries_tab, self.history_tab):
                tab.set_time_fields(view["clock"])

        # If the selected event disappeared (new scenario, undo...), forget it
        if self.selected is not None and not any(e["id"] == self.selected for e in view["events"]):
            self.selected = None

        self.tree_view.show(view, self.selected)
        self.node_panel.show(self.selected)
        for tab in (self.events_tab, self.queue_tab, self.history_tab, self.audit_tab, self.map_tab,
                    self.files_tab):
            tab.refresh(view)


def start():
    app = SismoLabApp()
    app.mainloop()
