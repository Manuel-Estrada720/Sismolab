"""Tab "Cola y estrés": bursts of reports, processing, stress mode and recovery."""

import json
import tkinter as tk
from tkinter import filedialog, ttk

from .common import (DATA_DIR, ScrollFrame, fill_table, labeled_entry, make_table, one_decimal, section,
                     set_entry, show_date, to_iso)


class QueueTab(ScrollFrame):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.draft = []           # reports prepared but not sent yet
        self.continuous = False   # True while "Continuo" is running
        page = self.inner

        # ---- processing ----
        box = section(page, "Procesamiento de la cola (FIFO)", "El orden de la cola es el de llegada; la "
                      "prioridad solo decide la posición en el AVL. Cada paso resuelve un reporte y se puede "
                      "deshacer por separado.")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=4)
        self.step_button = ttk.Button(row, text="Procesar un paso", command=self.step)
        self.step_button.pack(side="left")
        self.continuous_button = ttk.Button(row, text="Continuo", command=self.start_continuous)
        self.continuous_button.pack(side="left", padx=4)
        self.pause_button = ttk.Button(row, text="Pausar", command=self.pause_continuous)
        self.pause_button.pack(side="left")
        ttk.Label(row, text="Pausa (ms)").pack(side="left", padx=(8, 2))
        self.delay = ttk.Entry(row, width=6)
        self.delay.insert(0, "800")
        self.delay.pack(side="left")
        self.all_button = ttk.Button(row, text="Procesar toda la cola", command=self.process_all)
        self.all_button.pack(side="left", padx=4)
        self.queue_table = make_table(box, [("#", 35), ("Estación", 95), ("Evento", 95), ("Rev.", 40),
                                            ("M", 45), ("H km", 50), ("Ocurrencia", 150)], height=6)
        self.queue_table.frame.pack(fill="x")

        # ---- stress ----
        box = section(page, "Modo estrés y recuperación", "En estrés se insertan, corrigen y eliminan nodos "
                      "conservando el orden BST, pero sin rotaciones. La recuperación global pausa la cola, "
                      "aplica rotaciones hasta restablecer el AVL y solo vuelve al modo normal si la auditoría "
                      "lo confirma.")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=4)
        self.stress_button = ttk.Button(row, text="Activar modo estrés", command=self.enter_stress)
        self.stress_button.pack(side="left")
        self.recover_button = ttk.Button(row, text="Recuperación global", command=self.recover)
        self.recover_button.pack(side="left", padx=4)

        # ---- burst ----
        box = section(page, "Preparar una ráfaga", "Los reportes no se aplican hasta encolar y procesar. "
                      "Pueden venir de varias estaciones.")
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        self.rep_id = labeled_entry(grid, 0, 0, "ID")
        self.rep_revision = labeled_entry(grid, 0, 1, "Revisión", value="1")
        self.rep_magnitude = labeled_entry(grid, 0, 2, "Magnitud")
        self.rep_depth = labeled_entry(grid, 0, 3, "Prof. km")
        self.rep_x = labeled_entry(grid, 2, 0, "x km")
        self.rep_y = labeled_entry(grid, 2, 1, "y km")
        self.rep_time = labeled_entry(grid, 2, 2, "Ocurrencia UTC", width=20)
        ttk.Label(grid, text="Estación").grid(row=2, column=3, sticky="w", padx=4)
        self.rep_station = ttk.Combobox(grid, state="readonly", width=12)
        self.rep_station.grid(row=3, column=3, sticky="w", padx=4)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="Añadir a la ráfaga", command=self.add_report).pack(side="left")
        self.send_button = ttk.Button(row, text="Encolar ráfaga (0)", command=self.send_burst)
        self.send_button.pack(side="left", padx=4)
        ttk.Button(row, text="Vaciar borrador", command=self.clear_draft).pack(side="left")
        ttk.Button(row, text="Cargar ráfaga desde JSON…", command=self.load_burst_file).pack(side="left", padx=4)
        self.draft_table = make_table(box, [("Estación", 95), ("Evento", 95), ("Rev.", 40), ("M", 45)], height=4)
        self.draft_table.frame.pack(fill="x")

        # ---- log ----
        box = section(page, "Registro de procesamiento")
        self.log_table = make_table(box, [("Estación", 85), ("Evento", 90), ("Rev.", 35), ("Decisión", 100),
                                          ("Rotaciones", 120), ("Detalle", 260)], height=8)
        self.log_table.frame.pack(fill="both", expand=True)

    def set_time_fields(self, clock):
        set_entry(self.rep_time, show_date(clock))

    # ---------------------------------------------------------------- burst draft

    def add_report(self):
        if not self.rep_id.get().strip():
            self.app.show_message({"ok": False, "message": "Escriba el ID del reporte", "details": None})
            return
        self.draft.append({
            "id": self.rep_id.get(),
            "revision": self.rep_revision.get(),
            "magnitude": self.rep_magnitude.get(),
            "depth": self.rep_depth.get(),
            "x": self.rep_x.get(),
            "y": self.rep_y.get(),
            "time": to_iso(self.rep_time.get()),
            "station": self.rep_station.get(),
        })
        self.rep_id.delete(0, tk.END)
        self._show_draft()

    def clear_draft(self):
        self.draft = []
        self._show_draft()

    def _show_draft(self):
        rows = [[r["station"], r["id"], r["revision"], r["magnitude"]] for r in self.draft]
        fill_table(self.draft_table, rows)
        self.send_button.configure(text="Encolar ráfaga (" + str(len(self.draft)) + ")")
        self.send_button.state(["!disabled"] if self.draft else ["disabled"])

    def send_burst(self):
        result = self.app.run(self.app.obs.enqueue_reports(self.draft))
        if result["ok"]:
            self.clear_draft()

    def load_burst_file(self):
        """Read a JSON file with {"reports": [...]} (see data/reports/) and enqueue it."""
        path = filedialog.askopenfilename(title="Ráfaga de reportes", initialdir=str(DATA_DIR / "reports"),
                                          filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                content = json.load(stream)
            reports = content if isinstance(content, list) else content.get("reports")
            if not isinstance(reports, list):
                raise ValueError('el archivo debe tener una lista "reports"')
        except (OSError, ValueError, AttributeError) as error:
            self.app.show_message({"ok": False, "message": "No se pudo leer la ráfaga: " + str(error),
                                   "details": None})
            return
        self.app.run(self.app.obs.enqueue_reports(reports))

    # ---------------------------------------------------------------- processing

    def step(self):
        return self.app.run(self.app.obs.process_step())

    def process_all(self):
        self.app.run(self.app.obs.process_all())

    def start_continuous(self):
        """One step, a pause, the next step... until the queue is empty or the user pauses."""
        self.continuous = True
        self._update_buttons(self.app.view)
        self._continuous_step()

    def _continuous_step(self):
        if not self.continuous:
            return
        if not self.app.view["queue"]:
            self.pause_continuous()
            return
        result = self.step()
        if not result["ok"] or not self.app.view["queue"]:
            self.pause_continuous()     # error or queue finished
            return
        try:
            delay = max(100, int(self.delay.get()))
        except ValueError:
            delay = 800
        self.after(delay, self._continuous_step)

    def pause_continuous(self):
        self.continuous = False
        self._update_buttons(self.app.view)

    def enter_stress(self):
        self.app.run(self.app.obs.enter_stress())

    def recover(self):
        self.pause_continuous()     # the global recovery pauses the processing of reports
        self.app.run(self.app.obs.recover())

    # ---------------------------------------------------------------- redraw

    def _update_buttons(self, view):
        """Enable only the buttons that make sense right now."""
        empty = not view["queue"]
        stress = view["mode"] == "STRESS"

        def enable(button, on):
            button.state(["!disabled"] if on else ["disabled"])
        enable(self.step_button, not empty and not self.continuous)
        enable(self.all_button, not empty and not self.continuous)
        enable(self.continuous_button, not empty and not self.continuous)
        enable(self.pause_button, self.continuous)
        enable(self.stress_button, not stress)
        enable(self.recover_button, stress)

    def refresh(self, view):
        self._update_buttons(view)
        self.rep_station.configure(values=view["stations"])
        if self.rep_station.get() not in view["stations"]:
            self.rep_station.set(view["stations"][0] if view["stations"] else "")
        self._show_draft()
        rows = [[r["position"], r["station"], r["label"], r["revision"], one_decimal(r["magnitude"]),
                 one_decimal(r["depth"]), r["time"]] for r in view["queue"]]
        fill_table(self.queue_table, rows)
        rows = [[e["station"], e["label"], e["revision"], e["decision_name"], e.get("rotation_text", ""),
                 e["detail"]] for e in view["queue_log"]]
        fill_table(self.log_table, rows)
