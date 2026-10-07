"""Tab "Historial": undo stack, clock, parameters, named versions and action history."""

from tkinter import messagebox, ttk

from .common import ScrollFrame, fill_table, labeled_entry, make_table, section, set_entry, show_date, to_iso


class HistoryTab(ScrollFrame):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        page = self.inner

        box = section(page, "Deshacer", "Cada acción guarda antes una copia completa del escenario (pila). "
                      "Deshacer recupera el estado exacto, incluida la topología del árbol. Arriba = tope.")
        self.undo_button = ttk.Button(box, text="Deshacer", command=app.undo)
        self.undo_button.pack(anchor="w", pady=4)
        self.undo_table = make_table(box, [("Acción que se deshace", 420)], height=5)
        self.undo_table.frame.pack(fill="x")

        box = section(page, "Reloj de simulación")
        self.clock_hint = ttk.Label(box, text="", foreground="#6b7180")
        self.clock_hint.pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.hours = labeled_entry(row, 0, 0, "Avanzar (horas)", width=8, value="24")
        ttk.Button(row, text="Avanzar", command=self.advance).grid(row=1, column=1, padx=4)
        self.clock_to = labeled_entry(row, 0, 2, "o ir hasta (UTC)", width=20)
        ttk.Button(row, text="Ir", command=self.go_to).grid(row=1, column=3, padx=4)

        box = section(page, "Parámetros", "W y R recalculan las asociaciones; L cambia qué accesos son "
                      "costosos; T fija la antigüedad para archivar.")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.params = {
            "W": labeled_entry(row, 0, 0, "W: ventana (h)", width=8),
            "R": labeled_entry(row, 0, 1, "R: radio (km)", width=8),
            "L": labeled_entry(row, 0, 2, "L: prof. límite", width=8),
            "T": labeled_entry(row, 0, 3, "T: antigüedad (h)", width=8),
        }
        ttk.Button(row, text="Aplicar parámetros", command=self.apply_parameters).grid(row=1, column=4, padx=4)

        box = section(page, "Versiones con nombre", "Se guardan en data/versions/ y siguen ahí al cerrar el "
                      "programa. Seleccione una y pulse Restaurar (se puede deshacer).")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.version_name = labeled_entry(row, 0, 0, "Nombre", width=24)
        ttk.Button(row, text="Guardar versión", command=self.save_version).grid(row=1, column=1, padx=4)
        self.versions = make_table(box, [("Nombre", 180), ("Guardada", 160), ("Eventos", 60)], height=4)
        self.versions.frame.pack(fill="x", pady=4)
        ttk.Button(box, text="Restaurar seleccionada…", command=self.restore_version).pack(anchor="w")

        box = section(page, "Historial de acciones (más reciente arriba)")
        self.history = make_table(box, [("Acción", 170), ("Resultado", 60), ("Mensaje", 330)], height=10)
        self.history.frame.pack(fill="both", expand=True)

    def set_time_fields(self, clock):
        set_entry(self.clock_to, show_date(clock))

    # ---------------------------------------------------------------- actions

    def advance(self):
        self.app.run(self.app.obs.advance_clock(hours=self.hours.get()))

    def go_to(self):
        self.app.run(self.app.obs.advance_clock(to=to_iso(self.clock_to.get())))

    def apply_parameters(self):
        form = {name: entry.get() for name, entry in self.params.items()}
        self.app.run(self.app.obs.set_parameters(form))

    def save_version(self):
        result = self.app.run(self.app.obs.save_version(self.version_name.get()))
        if result["ok"]:
            self.version_name.delete(0, "end")

    def restore_version(self):
        name = self.versions.focus()
        if not name:
            self.app.show_message({"ok": False, "message": "Seleccione una versión de la lista", "details": None})
            return
        if messagebox.askyesno("Restaurar versión", "¿Restaurar la versión '" + name + "'? Se puede deshacer."):
            self.app.run(self.app.obs.restore_version(name))

    # ---------------------------------------------------------------- redraw

    def refresh(self, view):
        self.clock_hint.configure(text="Actual: " + view["clock"] + ". Solo avanza; determina la antigüedad "
                                  "de los eventos.")
        focused = self.focus_get()
        for name, entry in self.params.items():
            if entry is not focused:            # do not overwrite what the user is typing
                set_entry(entry, view["parameters"][name])
        self.undo_button.state(["!disabled"] if view["undo"]["available"] else ["disabled"])
        labels = list(view["undo"]["labels"])
        if view["undo"]["size"] > len(labels):
            labels.append("… y " + str(view["undo"]["size"] - len(labels)) + " acción(es) más")
        fill_table(self.undo_table, [[label] for label in labels])
        fill_table(self.history, [[h["label"], "aplicada" if h["ok"] else "rechazada", h["message"]]
                                  for h in view["history"]])
        versions = self.app.obs.list_versions()["details"]["versions"]
        fill_table(self.versions, [[v["name"], v["saved_at"], v["events"]] for v in versions],
                   [v["name"] for v in versions])
