"""Tab "Eventos": create, correct, search by id, archive a branch and the catalog.

Pattern of every button: read the entries -> call the Observatory ->
app.run(result) shows "Qué pasó" and redraws everything.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from .common import (EVENT_COLUMNS, ScrollFrame, event_row, fill_table, labeled_entry, make_table,
                     one_decimal, section, set_entry, show_date, sis, text_box, to_iso, write_text)

FILTERS = {"Activos": "ACTIVE", "Archivados": "ARCHIVED", "Eliminados": "DELETED", "Todos": "ALL"}


class EventsTab(ScrollFrame):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.preview = None     # last answer of "Ver rama elegible"
        page = self.inner

        # ---- create ----
        box = section(page, "Crear evento", "Se asigna la revisión 1, se calcula la zona y la prioridad, "
                      "y el evento entra al AVL como pendiente. Use punto decimal: 5.2")
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        self.new_id = labeled_entry(grid, 0, 0, "Identificador")
        self.new_magnitude = labeled_entry(grid, 0, 1, "Magnitud (-2 a 10)")
        self.new_depth = labeled_entry(grid, 0, 2, "Profundidad km (0-700)")
        self.new_x = labeled_entry(grid, 2, 0, "Epicentro x km")
        self.new_y = labeled_entry(grid, 2, 1, "Epicentro y km")
        self.new_time = labeled_entry(grid, 2, 2, "Ocurrencia UTC", width=20)
        ttk.Label(grid, text="Estación").grid(row=4, column=0, sticky="w", padx=4)
        self.new_station = ttk.Combobox(grid, state="readonly", width=14)
        self.new_station.grid(row=5, column=0, sticky="w", padx=4)
        ttk.Button(grid, text="Crear", command=self.create).grid(row=5, column=2, sticky="e", padx=4)

        # ---- correct ----
        box = section(page, "Corregir evento", "Crea la revisión r + 1. Si cambian P o M, el nodo se retira "
                      "con su clave anterior y se reinserta. Deje un campo vacío para conservar su valor.")
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        self.fix_id = labeled_entry(grid, 0, 0, "ID a corregir")
        self.fix_magnitude = labeled_entry(grid, 0, 1, "Magnitud")
        self.fix_depth = labeled_entry(grid, 0, 2, "Profundidad km")
        self.fix_x = labeled_entry(grid, 2, 0, "Epicentro x km")
        self.fix_y = labeled_entry(grid, 2, 1, "Epicentro y km")
        self.fix_time = labeled_entry(grid, 2, 2, "Ocurrencia UTC", width=20)
        ttk.Label(grid, text="Estación").grid(row=4, column=0, sticky="w", padx=4)
        self.fix_station = ttk.Combobox(grid, state="readonly", width=14)
        self.fix_station.grid(row=5, column=0, sticky="w", padx=4)
        ttk.Button(grid, text="Aplicar corrección", command=self.correct).grid(row=5, column=2, sticky="e", padx=4)

        # ---- search ----
        box = section(page, "Consultar por identificador")
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="ID").pack(side="left")
        self.search_id = ttk.Entry(row, width=14)
        self.search_id.pack(side="left", padx=4)
        self.search_id.bind("<Return>", lambda e: self.search())
        ttk.Button(row, text="Buscar", command=self.search).pack(side="left")
        self.search_result = ttk.Label(box, text="", wraplength=520, justify="left")
        self.search_result.pack(fill="x", anchor="w")

        # ---- archive ----
        box = section(page, "Archivar rama de eventos antiguos")
        self.archive_hint = ttk.Label(box, text="", foreground="#6b7180", wraplength=520, justify="left")
        self.archive_hint.pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Ver rama elegible", command=self.preview_archive).pack(side="left")
        self.archive_button = ttk.Button(row, text="Archivar…", command=self.apply_archive)
        self.archive_button.pack(side="left", padx=4)
        self.archive_button.state(["disabled"])
        self.archive_text = text_box(box, height=5)
        self.archive_text.frame.pack(fill="x")

        # ---- catalog ----
        box = section(page, "Catálogo", "Doble clic en una fila para seleccionar el evento.")
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Mostrar").pack(side="left")
        self.filter = tk.StringVar(value="Activos")
        combo = ttk.Combobox(row, textvariable=self.filter, values=list(FILTERS), width=11, state="readonly")
        combo.pack(side="left", padx=4)
        combo.bind("<<ComboboxSelected>>", lambda e: self.refresh(self.app.view))
        self.catalog_count = ttk.Label(row, text="")
        self.catalog_count.pack(side="left", padx=8)
        self.catalog = make_table(box, EVENT_COLUMNS + [("Prof. nodo", 70), ("Referencia", 70)], height=10)
        self.catalog.frame.pack(fill="both", expand=True)
        self.catalog.bind("<Double-1>", lambda e: self._select_row(self.catalog))

    # ---------------------------------------------------------------- helpers

    def _select_row(self, table):
        row = table.focus()
        if row.isdigit():
            self.app.select(int(row))

    def set_time_fields(self, clock):
        """Called when the clock changes: new events start at the current clock."""
        set_entry(self.new_time, show_date(clock))

    # ---------------------------------------------------------------- actions

    def create(self):
        form = {
            "id": self.new_id.get(),
            "magnitude": self.new_magnitude.get(),
            "depth": self.new_depth.get(),
            "x": self.new_x.get(),
            "y": self.new_y.get(),
            "time": to_iso(self.new_time.get()),
            "station": self.new_station.get(),
        }
        result = self.app.run(self.app.obs.create_event(form))
        if result["ok"]:
            self.new_id.delete(0, tk.END)
            self.app.select(result["details"]["event_id"])

    def correct(self):
        text = self.fix_id.get().strip()
        if not text:
            self.app.show_message({"ok": False, "message": "Escriba el identificador del evento a corregir",
                                   "details": None})
            return
        try:
            event_id = int(text.upper().replace("SIS-", ""))
        except ValueError:
            self.app.show_message({"ok": False, "message": "El identificador debe ser un número",
                                   "details": None})
            return
        form = {
            "magnitude": self.fix_magnitude.get(),
            "depth": self.fix_depth.get(),
            "x": self.fix_x.get(),
            "y": self.fix_y.get(),
            "time": to_iso(self.fix_time.get()),
            "station": self.fix_station.get(),
        }
        result = self.app.run(self.app.obs.correct_event(event_id, form))
        if result["ok"]:
            self.app.select(event_id)

    def fill_correction(self, event):
        """'Corregir…' in the node panel copies the event into the form."""
        self.app.show_tab(self)
        set_entry(self.fix_id, event["id"])
        set_entry(self.fix_magnitude, one_decimal(event["magnitude"]))
        set_entry(self.fix_depth, one_decimal(event["depth"]))
        set_entry(self.fix_x, one_decimal(event["x"]))
        set_entry(self.fix_y, one_decimal(event["y"]))
        set_entry(self.fix_time, show_date(event["time"]))
        self.fix_station.set(event["stations"][0])
        self.canvas.yview_moveto(0)
        self.fix_magnitude.focus_set()

    def search(self):
        text = self.search_id.get().strip().upper().replace("SIS-", "")
        if not text.isdigit():
            self.search_result.configure(text="Escriba un identificador numérico, por ejemplo 10 o SIS-000010",
                                         foreground="#b3261e")
            return
        answer = self.app.obs.get_event(int(text))
        if not answer["ok"]:
            self.search_result.configure(text=answer["message"], foreground="#b3261e")
            return
        e = answer["details"]
        line = answer["message"]
        if e["state"] == "ACTIVE":
            line += " · nodos AVL examinados: " + str(e["examined"]) + " (profundidad " + str(e["node_depth"]) + " + 1)"
        line += "\nClave " + e["key_text"] + " · revisión " + str(e["revision"]) + " · estaciones "
        line += ", ".join(e["stations"]) + " · " + ("zona poblada" if e["populated"] else "zona no poblada")
        self.search_result.configure(text=line, foreground="black")
        if e["state"] == "ACTIVE":
            self.app.select(e["id"])

    def preview_archive(self):
        self.preview = self.app.obs.archive_preview()
        details = self.preview["details"] or {}
        lines = [self.preview["message"]]
        if self.preview["ok"]:
            lines.append("Eventos: " + ", ".join(details["labels"]))
            lines += ["- " + line for line in details["justification"]]
        for item in details.get("blocked", []):
            lines.append("Raíz " + sis(item["root"]) + " " + item["reason"])
        write_text(self.archive_text, "\n".join(lines))
        self.archive_button.state(["!disabled"] if self.preview["ok"] else ["disabled"])

    def apply_archive(self):
        if not self.preview or not self.preview["ok"]:
            return
        d = self.preview["details"]
        question = ("¿Archivar la rama con raíz " + sis(d["root"]) + "?\n\n" + str(d["count"]) + " evento(s): "
                    + ", ".join(d["labels"]) + "\n\n" + "\n".join(d["justification"]))
        if not messagebox.askyesno("Archivar rama", question):
            return
        self.app.run(self.app.obs.archive_apply(d["ids"]))
        self.preview = None
        self.archive_button.state(["disabled"])
        write_text(self.archive_text, "")

    # ---------------------------------------------------------------- redraw

    def refresh(self, view):
        stations = view["stations"]
        for combo in (self.new_station, self.fix_station):
            combo.configure(values=stations)
            if combo.get() not in stations:
                combo.set(stations[0] if stations else "")
        self.archive_hint.configure(
            text="Elegible: todos sus eventos con prioridad baja y antigüedad mayor que T = "
                 + str(view["parameters"]["T"]) + " h. Se elige la rama más grande; empate -> raíz más "
                 "profunda; empate -> mayor ID de raíz.")
        wanted = FILTERS[self.filter.get()]
        shown = [e for e in view["events"] if wanted == "ALL" or e["state"] == wanted]
        rows = [event_row(e, ("node_depth",)) + [sis(e["reference"]) if e["reference"] else "—"] for e in shown]
        fill_table(self.catalog, rows, [e["id"] for e in shown])
        self.catalog_count.configure(text=str(len(shown)) + " evento(s)")
