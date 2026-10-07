"""Tab "Auditoría": verify the structure, indicators, counters and traversals."""

from tkinter import ttk

from .common import ScrollFrame, fill_table, make_table, section, text_box, write_text

COUNTER_NAMES = [
    ("corrections", "Correcciones aceptadas"),
    ("discarded", "Reportes descartados"),
    ("conflicts", "Conflictos"),
    ("archive_operations", "Archivos masivos"),
    ("archived_events", "Eventos archivados"),
    ("count_ll", "Casos LL"),
    ("count_rr", "Casos RR"),
    ("count_lr", "Casos LR"),
    ("count_rl", "Casos RL"),
    ("count_left_rotations", "Giros simples a la izquierda"),
    ("count_right_rotations", "Giros simples a la derecha"),
]

TRAVERSALS = [("inorder", "Inorden"), ("preorder", "Preorden"), ("postorder", "Postorden"),
              ("levels", "Por niveles")]


class AuditTab(ScrollFrame):

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        page = self.inner

        box = section(page, "Verificar estructura", "Comprueba el orden global por K, unicidad, enlaces, "
                      "claves, alturas, factores de balance y referencias. En modo estrés el desbalance se "
                      "informa como esperado.")
        ttk.Button(box, text="Verificar estructura", command=self.audit).pack(anchor="w", pady=4)
        self.audit_label = ttk.Label(box, text="", wraplength=520, justify="left")
        self.audit_label.pack(fill="x", anchor="w")
        self.issues = make_table(box, [("Evento", 95), ("Tipo", 110), ("Detalle", 330)], height=6)
        self.issues.frame.pack(fill="x")

        box = section(page, "Indicadores")
        self.indicators = make_table(box, [("Indicador", 260), ("Valor", 120)], height=8)
        self.indicators.frame.pack(fill="x")

        box = section(page, "Contadores (se restauran al deshacer)",
                      "Un caso doble (LR o RL) cuenta como un caso y dos giros elementales.")
        self.counters = make_table(box, [("Contador", 260), ("Valor", 120)], height=11)
        self.counters.frame.pack(fill="x")

        box = section(page, "Recorridos del AVL (IDs)")
        self.traversals = text_box(box, height=10)
        self.traversals.frame.pack(fill="x")

    def audit(self):
        answer = self.app.obs.audit()
        report = answer["details"]
        self.audit_label.configure(text=answer["message"] + " · " + str(report["checked_nodes"])
                                   + " nodo(s) revisados", foreground="#2f7d32" if answer["ok"] else "#b3261e")
        rows = [[i["label"], i["type"], i["detail"]] for i in report["errors"]]
        rows += [[i["label"], "esperado (estrés)", i["detail"]] for i in report["expected"]]
        fill_table(self.issues, rows)

    def refresh(self, view):
        ind = view["indicators"]
        p = ind["by_priority"]
        fill_table(self.indicators, [
            ["Eventos activos", ind["active"]],
            ["Archivados (histórico)", ind["archived"]],
            ["Eliminados", ind["deleted"]],
            ["Altura del AVL", ind["height"]],
            ["Hojas", ind["leaves"]],
            ["Pendientes de atención", ind["pending"]],
            ["Acceso costoso", ind["costly"]],
            ["Prioridad baja / media / alta", str(p["1"]) + " / " + str(p["2"]) + " / " + str(p["3"])],
        ])
        fill_table(self.counters, [[title, view["metrics"].get(key, 0)] for key, title in COUNTER_NAMES])
        lines = []
        for key, title in TRAVERSALS:
            ids = ind["traversals"][key]
            lines.append(title + " (" + str(len(ids)) + "): " + (" · ".join(str(i) for i in ids) or "—"))
        write_text(self.traversals, "\n\n".join(lines))
