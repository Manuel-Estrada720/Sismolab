"""Panel with the data of the selected event and the actions available for it."""

import tkinter as tk
from tkinter import messagebox, ttk

from .common import PRIORITY_COLORS, PRIORITY_NAMES, STATE_NAMES, one_decimal, sis


def labels(items, empty_text):
    if not items:
        return empty_text
    return ", ".join(item["label"] for item in items)


class NodePanel(ttk.LabelFrame):

    def __init__(self, parent, app):
        super().__init__(parent, text="Evento seleccionado", padding=6)
        self.app = app
        self.event = None
        self.title = tk.Label(self, text="Haga clic en un nodo del árbol o del mapa.",
                              anchor="w", font=("TkDefaultFont", 10, "bold"))
        self.title.pack(fill="x")
        self.body = ttk.Label(self, text="", justify="left", wraplength=640)
        self.body.pack(fill="x", anchor="w")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(4, 0))
        self.review_button = ttk.Button(buttons, text="Marcar revisado", command=self.review)
        self.review_button.pack(side="left")
        self.edit_button = ttk.Button(buttons, text="Corregir…", command=self.edit)
        self.edit_button.pack(side="left", padx=4)
        self.delete_button = ttk.Button(buttons, text="Eliminar…", command=self.delete)
        self.delete_button.pack(side="left")
        ttk.Button(buttons, text="Cerrar", command=self.close).pack(side="right")
        self._enable(False, False)

    def _enable(self, active, pending):
        self.review_button.state(["!disabled"] if active and pending else ["disabled"])
        for button in (self.edit_button, self.delete_button):
            button.state(["!disabled"] if active else ["disabled"])

    def show(self, event_id):
        """Ask the Observatory for the full data of the event and show it."""
        if event_id is None:
            self.close(redraw=False)
            return
        answer = self.app.obs.get_event(event_id)
        if not answer["ok"]:
            self.close(redraw=False)    # it no longer exists (new scenario, undo...)
            return
        e = answer["details"]
        self.event = e
        links = e.get("associations") or {}
        title = e["label"] + "  ·  prioridad " + PRIORITY_NAMES[e["priority"]] + "  ·  " + STATE_NAMES[e["state"]]
        if e.get("costly"):
            title += "  ·  ACCESO COSTOSO"
        self.title.configure(text=title, foreground=PRIORITY_COLORS[e["priority"]])
        lines = [
            "Clave K: " + e["key_text"],
            "M " + one_decimal(e["magnitude"]) + " · H " + one_decimal(e["depth"]) + " km · epicentro ("
            + one_decimal(e["x"]) + ", " + one_decimal(e["y"]) + ") km · "
            + ("zona poblada" if e["populated"] else "zona no poblada"),
            "Ocurrencia " + e["time"] + " · revisión r" + str(e["revision"]) + " · estaciones "
            + ", ".join(e["stations"]) + " · " + ("pendiente" if e["attention"] == "PENDING" else "revisado"),
        ]
        if e["state"] == "ACTIVE":
            lines.append("Nodo: profundidad " + str(e["node_depth"]) + " · altura " + str(e["node_height"])
                         + " · balance " + str(e["balance_factor"]) + " · costo de búsqueda "
                         + str(e["search_cost"]) + " nodos")
        reference = links.get("reference")
        lines.append("Referencia: " + (reference["label"] if reference else "sin asociación")
                     + " · candidatos: " + labels(links.get("candidates"), "ninguno")
                     + " · lo usan: " + labels(links.get("used_by"), "nadie"))
        self.body.configure(text="\n".join(lines))
        self._enable(e["state"] == "ACTIVE", e["attention"] == "PENDING")

    def close(self, redraw=True):
        self.event = None
        self.title.configure(text="Haga clic en un nodo del árbol o del mapa.", foreground="black")
        self.body.configure(text="")
        self._enable(False, False)
        if redraw:
            self.app.select(None)

    # ---------------------------------------------------------------- actions

    def review(self):
        if self.event:
            self.app.run(self.app.obs.mark_reviewed(self.event["id"]))

    def edit(self):
        if self.event:
            self.app.events_tab.fill_correction(self.event)

    def delete(self):
        if not self.event:
            return
        event_id = self.event["id"]
        question = ("¿Eliminar " + sis(event_id) + "?\n\nSolo se retira este evento; sus descendientes "
                    "siguen activos. Su identificador queda retirado y solo se recupera con Deshacer.")
        if messagebox.askyesno("Eliminar evento", question):
            self.app.run(self.app.obs.delete_event(event_id))
