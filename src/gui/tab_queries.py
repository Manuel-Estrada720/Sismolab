"""Tabs "Consultas" and "AVL vs BST".

Queries only read the scenario: they do not use app.run (nothing to undo).
Each answer says how many AVL nodes were examined.
"""

import tkinter as tk
from tkinter import ttk

from .common import (EVENT_COLUMNS, ScrollFrame, event_row, fill_table, labeled_entry, make_table,
                     section, set_entry, show_date, to_iso)
from .tree_view import lighter


class QueriesTab(ScrollFrame):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        page = self.inner

        box = section(page, "Primeros k pendientes (K descendente)")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.k = labeled_entry(row, 0, 0, "k", width=6, value="5")
        ttk.Button(row, text="Consultar", command=self.pending).grid(row=1, column=1, padx=4)
        self.pending_out = self._result_area(box, [("Prof. nodo", 70)])

        box = section(page, "Eventos en un intervalo de magnitud")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.m_min = labeled_entry(row, 0, 0, "M mínima", width=8, value="4.5")
        self.m_max = labeled_entry(row, 0, 1, "M máxima", width=8, value="6.0")
        ttk.Button(row, text="Consultar", command=self.magnitude).grid(row=1, column=2, padx=4)
        self.magnitude_out = self._result_area(box, [("Prof. nodo", 70)])

        box = section(page, "Profundidad del hipocentro <= límite, en un intervalo de fechas")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.max_depth = labeled_entry(row, 0, 0, "H máxima km", width=8, value="30")
        self.date_from = labeled_entry(row, 0, 1, "Desde (UTC)", width=19, value="2026-09-01 00:00:00")
        self.date_to = labeled_entry(row, 0, 2, "Hasta (UTC)", width=19)
        ttk.Button(row, text="Consultar", command=self.depth_dates).grid(row=1, column=3, padx=4)
        self.depth_out = self._result_area(box, [])

        box = section(page, "Eventos de prioridad alta con acceso costoso")
        ttk.Button(box, text="Consultar", command=self.costly).pack(anchor="w")
        self.costly_out = self._result_area(box, [("Prof. nodo", 70), ("L", 35), ("Visitados", 70)])

        box = section(page, "Asociaciones de un evento", "Candidatos ordenados por la política: mayor "
                      "magnitud, luego menor distancia, luego menor ID.")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.assoc_id = labeled_entry(row, 0, 0, "Identificador", width=12)
        ttk.Button(row, text="Consultar", command=self.associations).grid(row=1, column=1, padx=4)
        self.assoc_label = ttk.Label(box, text="", wraplength=520, justify="left")
        self.assoc_label.pack(fill="x", anchor="w")
        ttk.Label(box, text="Candidatos").pack(anchor="w")
        self.candidates = make_table(box, EVENT_COLUMNS + [("Distancia km", 80), ("Horas antes", 80)], height=4)
        self.candidates.frame.pack(fill="x")
        ttk.Label(box, text="Eventos que lo usan como referencia").pack(anchor="w")
        self.used_by = make_table(box, EVENT_COLUMNS, height=3)
        self.used_by.frame.pack(fill="x")

    def _result_area(self, box, extra_columns):
        label = ttk.Label(box, text="", wraplength=520, justify="left")
        label.pack(fill="x", anchor="w")
        table = make_table(box, EVENT_COLUMNS + extra_columns, height=4)
        table.frame.pack(fill="x")
        table.bind("<Double-1>", lambda e: self._select_row(table))
        return label, table

    def _select_row(self, table):
        row = table.focus()
        if row.isdigit():
            self.app.select(int(row))

    def set_time_fields(self, clock):
        set_entry(self.date_to, show_date(clock))

    def _show(self, output, name, params, extra=()):
        label, table = output
        answer = self.app.obs.query(name, params)
        if not answer["ok"]:
            label.configure(text=answer["message"], foreground="#b3261e")
            fill_table(table, [])
            return
        details = answer["details"]
        label.configure(text=answer["message"] + "\n" + details["explanation"], foreground="black")
        results = details["results"]
        fill_table(table, [event_row(e, extra) for e in results], [e["id"] for e in results])

    def pending(self):
        self._show(self.pending_out, "pending", {"k": self.k.get()}, ("node_depth",))

    def magnitude(self):
        self._show(self.magnitude_out, "magnitude", {"min": self.m_min.get(), "max": self.m_max.get()},
                   ("node_depth",))

    def depth_dates(self):
        params = {"max_depth": self.max_depth.get(), "from": to_iso(self.date_from.get()),
                  "to": to_iso(self.date_to.get())}
        self._show(self.depth_out, "depth-dates", params)

    def costly(self):
        self._show(self.costly_out, "costly", {}, ("node_depth", "limit", "search_cost"))

    def associations(self):
        answer = self.app.obs.query("associations", {"id": self.assoc_id.get()})
        if not answer["ok"]:
            self.assoc_label.configure(text=answer["message"], foreground="#b3261e")
            fill_table(self.candidates, [])
            fill_table(self.used_by, [])
            return
        d = answer["details"]
        reference = "sin asociación"
        if d["reference"]:
            reference = d["reference"]["label"]
        self.assoc_label.configure(
            text=d["event"]["label"] + " · nodos AVL examinados " + str(d["examined"]) + " · registros revisados "
            + str(d["registry_scanned"]) + "\nReferencia elegida: " + reference + "\n" + d["explanation"],
            foreground="black")
        fill_table(self.candidates, [event_row(e, ("distance_km", "hours_before")) for e in d["candidates"]])
        fill_table(self.used_by, [event_row(e) for e in d["used_by"]])


class ComparisonTab(ScrollFrame):
    """Same events, same comparator, four insertion orders: AVL vs BST."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        box = section(self.inner, "Comparación AVL vs BST", "Se insertan los mismos eventos activos, con el "
                      "mismo comparador, en cuatro órdenes. Luego se busca cada clave una vez y se suman las "
                      "comparaciones (nodos visitados).")
        ttk.Button(box, text="Comparar", command=self.compare).pack(anchor="w", pady=4)
        self.table = make_table(box, [("Orden", 230), ("Árbol", 45), ("Altura", 55), ("Hojas", 55),
                                      ("Comparaciones", 100), ("Promedio", 70), ("Máximo", 60)], height=9)
        self.table.frame.pack(fill="x")
        ttk.Label(box, text="Barras: altura (arriba) y comparaciones totales (abajo) de cada orden.",
                  foreground="#6b7180").pack(anchor="w", pady=(6, 0))
        self.bars = tk.Canvas(box, height=470, background="white", highlightthickness=0)
        self.bars.pack(fill="x")
        self.seed = ttk.Label(box, text="", foreground="#6b7180")
        self.seed.pack(anchor="w")

    def compare(self):
        answer = self.app.obs.compare()
        rows = answer["details"]["rows"]
        table_rows = []
        for row in rows:
            for kind in ("avl", "bst"):
                m = row[kind]
                table_rows.append([row["title"] + " (" + str(row["size"]) + ")", kind.upper(), m["height"],
                                   m["leaves"], m["total_comparisons"], m["average_comparisons"],
                                   m["max_comparisons"]])
        fill_table(self.table, table_rows)
        self._draw_bars(rows)
        self.seed.configure(text="Orden aleatorio con semilla fija " + str(answer["details"]["seed"])
                            + " (reproducible).")

    def _draw_bars(self, rows):
        canvas = self.bars
        canvas.delete("all")
        colors = {"avl": "#0f6e6e", "bst": lighter("#6b7180")}
        max_height = max([1] + [row[k]["height"] for row in rows for k in ("avl", "bst")])
        max_comp = max([1] + [row[k]["total_comparisons"] for row in rows for k in ("avl", "bst")])
        y = 10
        for title, field, maximum in (("Altura", "height", max_height),
                                      ("Comparaciones", "total_comparisons", max_comp)):
            canvas.create_text(10, y, text=title, anchor="nw", font=("TkDefaultFont", 9, "bold"))
            y += 20
            for row in rows:
                canvas.create_text(20, y, text=row["title"], anchor="nw")
                y += 16
                for kind in ("avl", "bst"):
                    value = row[kind][field]
                    length = max(2, 380 * value / maximum)
                    canvas.create_text(20, y + 4, text=kind.upper(), anchor="w", font=("TkDefaultFont", 8))
                    canvas.create_rectangle(55, y, 55 + length, y + 8, fill=colors[kind], outline="")
                    canvas.create_text(61 + length, y + 4, text=str(value), anchor="w",
                                       font=("TkDefaultFont", 8))
                    y += 12
                y += 6
            y += 6

