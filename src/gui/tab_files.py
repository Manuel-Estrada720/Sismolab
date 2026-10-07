"""Tab "Archivos JSON": load (two modes), save and start a new scenario."""

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .common import DATA_DIR, ScrollFrame, fill_table, make_table, section


class FilesTab(ScrollFrame):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        page = self.inner

        box = section(page, "Cargar escenario", "Si el archivo es inválido se muestran los problemas y el "
                      "escenario actual no cambia. Una carga se puede deshacer.")
        self.mode = tk.StringVar(value="topology")
        ttk.Radiobutton(box, text="Por topología: recupera la raíz y los enlaces guardados (escenario completo)",
                        variable=self.mode, value="topology").pack(anchor="w")
        ttk.Radiobutton(box, text="Por inserciones: inserta los eventos en el mismo orden en el AVL y en el BST",
                        variable=self.mode, value="insertions").pack(anchor="w")
        ttk.Button(box, text="Elegir archivo y cargar…", command=self.load).pack(anchor="w", pady=4)
        self.load_table = make_table(box, [("Árbol", 60), ("Raíz", 100), ("Altura", 60),
                                           ("Profundidad máxima", 120), ("Hojas", 60)], height=2)
        self.load_table.frame.pack(fill="x")

        box = section(page, "Guardar escenario", "Guarda la topología del AVL, histórico, estaciones, "
                      "asociaciones, cola, reloj, zonas, parámetros, modo y métricas.")
        ttk.Button(box, text="Guardar como JSON…", command=self.save).pack(anchor="w", pady=4)

        box = section(page, "Nuevo escenario")
        ttk.Button(box, text="Escenario vacío", command=self.new).pack(anchor="w", pady=4)

    def load(self):
        path = filedialog.askopenfilename(title="Cargar escenario", initialdir=str(DATA_DIR / "scenarios"),
                                          filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                content = stream.read()
        except (OSError, UnicodeDecodeError) as error:
            self.app.show_message({"ok": False, "message": "No se pudo leer el archivo: " + str(error),
                                   "details": None})
            return
        # The Observatory validates everything and loads all or nothing
        result = self.app.run(self.app.obs.load_scenario(content, self.mode.get()))
        details = result["details"] or {}
        if result["ok"] and "avl" in details:
            # After a load by insertions, show the AVL and the BST side by side
            rows = []
            for kind in ("avl", "bst"):
                t = details[kind]
                rows.append([kind.upper(), t["root_label"], t["height"], t["max_depth"], t["leaves"]])
            fill_table(self.load_table, rows)
        else:
            fill_table(self.load_table, [])

    def save(self):
        clock = self.app.view["clock"].replace(":", "-")
        path = filedialog.asksaveasfilename(title="Guardar escenario", defaultextension=".json",
                                            initialfile="sismolab_" + clock + ".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(self.app.obs.export(), stream, ensure_ascii=False, indent=2)
        except (OSError, ValueError) as error:
            self.app.show_message({"ok": False, "message": "No se pudo guardar: " + str(error), "details": None})
            return
        self.app.show_message({"ok": True, "message": "Escenario guardado en " + path, "details": None})

    def new(self):
        if messagebox.askyesno("Nuevo escenario", "¿Empezar un escenario vacío? Se puede deshacer."):
            self.app.run(self.app.obs.new_scenario())

    def refresh(self, _view):
        pass
