"""Tab "Mapa": the plane of the territory (0 to 1000 km) drawn on a Canvas.

The Canvas "y" grows downwards, so the y of the plane is flipped:
(0, 0) is the bottom-left corner, like in a math graph.
"""

import tkinter as tk
from tkinter import ttk

from .common import COSTLY_COLOR, PRIORITY_COLORS, PRIORITY_NAMES, STATE_NAMES, one_decimal, sis

SIZE = 520          # pixels for 1000 km
LEFT, TOP = 48, 12  # space for the axis numbers


class MapTab(ttk.Frame):

    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        self.app = app
        ttk.Label(self, text="Zonas pobladas en verde, no pobladas rayadas. El tamaño del círculo crece con la "
                  "magnitud y el color indica la prioridad. Cada flecha va de un evento a su referencia. El "
                  "círculo punteado del seleccionado muestra el radio R. Clic en un evento = seleccionarlo.",
                  foreground="#6b7180", wraplength=560, justify="left").pack(anchor="w")
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        self.show_archived = tk.BooleanVar(value=True)
        self.show_deleted = tk.BooleanVar(value=False)
        self.show_links = tk.BooleanVar(value=True)
        self.show_radius = tk.BooleanVar(value=True)
        for text, variable in (("Archivados", self.show_archived), ("Eliminados", self.show_deleted),
                               ("Asociaciones", self.show_links), ("Radio R del seleccionado", self.show_radius)):
            ttk.Checkbutton(row, text=text, variable=variable, command=self.draw).pack(side="left", padx=4)
        self.canvas = tk.Canvas(self, width=SIZE + LEFT + 20, height=SIZE + TOP + 30, background="white",
                                highlightthickness=0)
        self.canvas.pack(anchor="w")
        self.canvas.tag_bind("quake", "<Button-1>", self._on_click)
        self.info = ttk.Label(self, text="Pase el ratón sobre un evento para ver sus datos.", foreground="#6b7180")
        self.info.pack(anchor="w")
        self.canvas.tag_bind("quake", "<Enter>", self._on_hover)

    @staticmethod
    def px(x, y):
        """Plane km -> canvas pixels."""
        return LEFT + x * SIZE / 1000, TOP + (1000 - y) * SIZE / 1000

    def refresh(self, _view):
        self.draw()

    def draw(self):
        view = self.app.view
        if view is None:
            return
        canvas = self.canvas
        canvas.delete("all")
        by_id = {e["id"]: e for e in view["events"]}
        visible = [e for e in view["events"] if e["state"] == "ACTIVE"
                   or (e["state"] == "ARCHIVED" and self.show_archived.get())
                   or (e["state"] == "DELETED" and self.show_deleted.get())]

        # Plane and grid every 250 km
        x0, y0 = self.px(0, 1000)
        x1, y1 = self.px(1000, 0)
        canvas.create_rectangle(x0, y0, x1, y1, fill="#fbfaf6", outline="#9b9488")
        for tick in (0, 250, 500, 750, 1000):
            gx, _ = self.px(tick, 0)
            _, gy = self.px(0, tick)
            canvas.create_line(gx, y0, gx, y1, fill="#ece7dc")
            canvas.create_line(x0, gy, x1, gy, fill="#ece7dc")
            canvas.create_text(gx, y1 + 12, text=str(tick), font=("TkDefaultFont", 8))
            canvas.create_text(x0 - 6, gy, text=str(tick), anchor="e", font=("TkDefaultFont", 8))

        # Zones: populated = green, not populated = hatched
        for zone in view["zones"]:
            a = self.px(zone["x1"], zone["y2"])
            b = self.px(zone["x2"], zone["y1"])
            if zone["populated"]:
                canvas.create_rectangle(a[0], a[1], b[0], b[1], fill="#cfe8cf", outline="#2f7d32")
            else:
                canvas.create_rectangle(a[0], a[1], b[0], b[1], fill="#e8e3d8", outline="#9b9488",
                                        stipple="gray25")
            canvas.create_text(a[0] + 4, a[1] + 4, anchor="nw", font=("TkDefaultFont", 8),
                               text=zone["zone_id"] + (" (poblada)" if zone["populated"] else " (no poblada)"))

        # Associations: arrow from each event to its reference
        if self.show_links.get():
            for event in visible:
                reference = by_id.get(event["reference"])
                if reference is not None:
                    a = self.px(event["x"], event["y"])
                    b = self.px(reference["x"], reference["y"])
                    canvas.create_line(a[0], a[1], b[0], b[1], arrow="last", fill="#0f6e6e")

        # Radius R around the selected event
        selected = by_id.get(self.app.selected)
        if self.show_radius.get() and selected is not None:
            cx, cy = self.px(selected["x"], selected["y"])
            r = view["parameters"]["R"] * SIZE / 1000
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#0f6e6e", dash=(4, 3))

        # Events: size grows with magnitude, colour = priority
        for event in visible:
            cx, cy = self.px(event["x"], event["y"])
            r = 3 + max(0, event["magnitude"]) * 1.3
            color = PRIORITY_COLORS[event["priority"]]
            tags = ("quake", "id:" + str(event["id"]))
            if event["state"] == "ACTIVE":
                outline = COSTLY_COLOR if event.get("costly") else "white"
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=outline,
                                   width=2 if event.get("costly") else 1, tags=tags)
            else:
                # Archived / deleted: only the outline
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2,
                                   dash=(2, 2) if event["state"] == "DELETED" else None, tags=tags)
            if event["id"] == self.app.selected:
                canvas.create_oval(cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4, outline="#1f2430", width=2)

    def _event_from_current(self):
        for tag in self.canvas.gettags("current"):
            if tag.startswith("id:"):
                return int(tag[3:])
        return None

    def _on_click(self, _event):
        event_id = self._event_from_current()
        if event_id is not None:
            self.app.select(event_id)

    def _on_hover(self, _event):
        event_id = self._event_from_current()
        event = next((e for e in self.app.view["events"] if e["id"] == event_id), None)
        if event is None:
            return
        text = (sis(event["id"]) + " · M " + one_decimal(event["magnitude"]) + " · H " + one_decimal(event["depth"])
                + " km · prioridad " + PRIORITY_NAMES[event["priority"]] + " · " + event["time"] + " · "
                + STATE_NAMES[event["state"]])
        if event["reference"]:
            text += " · referencia " + sis(event["reference"])
        self.info.configure(text=text, foreground="black")
