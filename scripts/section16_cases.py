"""The six mandatory cases of section 16, run against the real code.

Every case builds its own reproducible data, declares the initial state and
compares the EXPECTED result with the OBTAINED one. The unit tests in
tests/test_section16_cases.py call these functions, and

    python -m scripts.section16_cases

writes the evidence report docs_entrega/evidencia_casos_seccion16.md.
"""

import json
import tempfile
from pathlib import Path

from src.persistence.exporter import ScenarioLoadError, load_by_topology_from_dict, scenario_to_dict
from src.services.observatory import Observatory
from src.services.tree_info import key_text, sis

STATION = "EST-NORTE"
OLD = "2026-09-01T00:00:00Z"          # older than 72 h at the default clock (2026-09-07 12:00)
RECENT = "2026-09-07T10:00:00Z"
POPULATED = ("500", "450")             # inside "Valle Central" (populated)
UNPOPULATED = ("950", "950")           # inside "Llanura Este" (not populated)


class Case:
    def __init__(self, number, title, initial):
        self.number = number
        self.title = title
        self.initial = initial
        self.checks = []

    def check(self, description, expected, obtained):
        self.checks.append({
            "description": description,
            "expected": str(expected),
            "obtained": str(obtained),
            "ok": expected == obtained,
        })

    @property
    def ok(self):
        return all(item["ok"] for item in self.checks)


def observatory():
    return Observatory(versions_dir=tempfile.mkdtemp())


def create(obs, event_id, magnitude, depth="10", where=UNPOPULATED, time=RECENT):
    result = obs.create_event({"id": event_id, "magnitude": magnitude, "depth": depth,
                               "x": where[0], "y": where[1], "time": time, "station": STATION})
    if not result["ok"]:
        raise AssertionError(result["message"])
    return obs.state.registry.get(event_id)


def root(obs):
    return obs.state.tree.root.getEvent().data.event_id if obs.state.tree.root else None


def inorder(obs):
    return [node.getEvent().data.event_id for node in obs.state.tree.inorder()]


def shape(state):
    return {
        node.getEvent().data.event_id: (
            node.getLeft().getEvent().data.event_id if node.getLeft() else None,
            node.getRight().getEvent().data.event_id if node.getRight() else None,
        )
        for node in state.tree.preorder()
    }


# ---------------------------------------------------------------- case 1

def case_1_limits_and_ties():
    case = Case(1, "Límites de prioridad y desempate por identificador",
                "Escenario vacío con las zonas por defecto (Valle Central poblada x 400-700, y 300-600; "
                "Sierra Alta no poblada x 0-400, y 0-600; Ciudad Norte poblada x 100-400, y 600-900). "
                "Reloj 2026-09-07T12:00:00Z.")
    obs = observatory()
    rows = [
        (1, "4.5", "30", POPULATED, 3, "M = 4.5 y H = 30.0 en zona poblada (límites inclusivos)"),
        (2, "4.5", "30", UNPOPULATED, 2, "El mismo evento fuera de zona poblada"),
        (3, "4.5", "30.1", POPULATED, 2, "H = 30.1 supera el límite de profundidad"),
        (4, "4.4", "10", POPULATED, 1, "M = 4.4 no llega a 4.5"),
        (5, "6.0", "300", UNPOPULATED, 3, "M = 6.0 es alta en cualquier lugar"),
        (6, "5.9", "300", UNPOPULATED, 2, "M = 5.9 fuera de zona poblada"),
        (7, "5.0", "20", ("400", "450"), 3, "Epicentro en el borde x = 400 entre Sierra Alta (no poblada) y Valle Central (poblada)"),
        (8, "5.0", "20", ("100", "900"), 3, "Epicentro en la esquina (100, 900) de Ciudad Norte"),
        (9, "5.0", "20", ("99.9", "900"), 2, "A 0.1 km fuera del borde de Ciudad Norte"),
    ]
    for event_id, magnitude, depth, where, expected, description in rows:
        record = create(obs, event_id, magnitude, depth, where)
        case.check("SIS-%06d: %s → prioridad" % (event_id, description), expected, record.priority)

    # Ties: same priority and magnitude, the id decides
    for event_id in (30, 10, 20):
        create(obs, event_id, "5.2", "10", POPULATED)
    ties = [i for i in inorder(obs) if i in (10, 20, 30)]
    case.check("Tres eventos con clave (3, 5.2, I): el inorden los ordena por ID", [10, 20, 30], ties)
    from src.structures.comparator import compare_keys
    table = [((2, 58, 20), -1), ((3, 61, 30), 1), ((3, 52, 5), -1), ((3, 52, 25), 1)]
    for key, expected in table:
        direction = "izquierda" if expected < 0 else "derecha"
        obtained = "izquierda" if compare_keys(key, (3, 52, 10)) < 0 else "derecha"
        case.check("Tabla del §5: " + key_text(key) + " frente a (3, 5.2, 10)", direction, obtained)
    case.check("La auditoría del AVL no encuentra errores", True, obs.audit()["ok"])
    return case


# ---------------------------------------------------------------- case 2

def case_2_correction_and_old_report():
    case = Case(2, "Corrección M4.8/H70.0 → M6.2/H15.0 y reporte antiguo posterior",
                "Escenario vacío; SIS-000200 se crea en zona poblada (500, 450) con M 4.8 y H 70.0.")
    obs = observatory()
    record = create(obs, 200, "4.8", "70", POPULATED)
    case.check("Prioridad inicial (H 70 > 30 → media)", 2, record.priority)
    case.check("Clave inicial", "(2, 4.8, 200)", key_text(record.key()))
    obs.mark_reviewed(200)
    result = obs.correct_event(200, {"magnitude": "6.2", "depth": "15", "station": "EST-SUR"})
    case.check("La corrección se acepta", True, result["ok"])
    case.check("La prioridad pasa de 2 a 3", 3, record.priority)
    case.check("Nueva clave", "(3, 6.2, 200)", key_text(record.key()))
    case.check("Revisión r + 1", 2, record.revision)
    case.check("La corrección devuelve el evento a pendiente", "PENDING", record.attention)
    case.check("Se reubicó el nodo (clave cambió)", True, result["details"]["key_changed"])
    case.check("Sigue habiendo un solo nodo", 1, obs.state.tree.size)

    obs.enqueue_reports([{"id": 200, "magnitude": "4.8", "depth": "70", "x": POPULATED[0], "y": POPULATED[1],
                          "time": RECENT, "station": "EST-ESTE", "revision": 1}])
    step = obs.process_step()["details"]
    case.check("Reporte con revisión 1 (menor que la vigente)", "OLD", step["decision"])
    case.check("No se crea otro nodo", 1, obs.state.tree.size)
    case.check("No se revierte la corrección (magnitud)", 62, record.data.magnitude10)
    case.check("Revisión vigente sin cambios", 2, record.revision)
    case.check("Contador de reportes descartados", 1, obs.state.metrics["discarded"])
    case.check("Contador de correcciones aceptadas", 1, obs.state.metrics["corrections"])
    return case


# ---------------------------------------------------------------- case 3

def case_3_late_report():
    case = Case(3, "Reporte tardío: M5.6 a las 10:00, M4.2 a las 10:20 y luego M6.1 ocurrido a las 09:55",
                "W = 48 h, R = 40 km. Eventos cercanos alrededor de (500, 450). Política: mayor magnitud, "
                "luego menor distancia, luego menor ID.")
    obs = observatory()
    create(obs, 301, "5.6", "10", ("500", "450"), "2026-09-07T10:00:00Z")
    create(obs, 302, "4.2", "10", ("510", "450"), "2026-09-07T10:20:00Z")
    service = obs.state.associations
    case.check("Antes: candidatos de SIS-000302", [301], [r.data.event_id for r in service.candidates_of(obs.state.registry.get(302))])
    case.check("Antes: referencia de SIS-000302", 301, service.reference_of(302))
    case.check("Antes: SIS-000301 no tiene candidatos", None, service.reference_of(301))

    obs.enqueue_reports([{"id": 303, "magnitude": "6.1", "depth": "10", "x": "505", "y": "455",
                          "time": "2026-09-07T09:55:00Z", "station": "EST-OESTE", "revision": 1}])
    decision = obs.process_step()["details"]["decision"]
    case.check("El reporte tardío crea el evento", "CREATED", decision)
    links_301 = obs.query("associations", {"id": "301"})["details"]
    links_302 = obs.query("associations", {"id": "302"})["details"]
    case.check("Nuevos candidatos de SIS-000301", [303], [c["id"] for c in links_301["candidates"]])
    case.check("Referencia elegida para SIS-000301", 303, links_301["reference"]["id"])
    case.check("Candidatos de SIS-000302 ordenados por la política", [303, 301], [c["id"] for c in links_302["candidates"]])
    case.check("Referencia de SIS-000302 cambia a la de mayor magnitud", 303, links_302["reference"]["id"])
    case.check("Eventos que usan SIS-000303 como referencia", [301, 302],
               sorted(item["id"] for item in obs.query("associations", {"id": "303"})["details"]["used_by"]))
    case.check("No hay ciclos ni referencias inválidas (auditoría)", True, obs.audit()["ok"])
    return case


# ---------------------------------------------------------------- case 4

def case_4_rotations_and_recovery():
    case = Case(4, "Rotaciones LL, RR, LR, RL; estructura degradada en estrés y recuperación",
                "Para cada caso de balanceo, un escenario vacío y tres eventos de prioridad baja (M 3.0) "
                "insertados en el orden indicado. Para estrés, 40 eventos cercanos en el tiempo y el espacio.")
    for name, order, counter, expected_root in (
        ("LL", (30, 20, 10), "count_ll", 20),
        ("RR", (10, 20, 30), "count_rr", 20),
        ("LR", (30, 10, 20), "count_lr", 20),
        ("RL", (10, 30, 20), "count_rl", 20),
    ):
        obs = observatory()
        for event_id in order:
            create(obs, event_id, "3.0")
        counters = obs.state.all_metrics()
        case.check("Caso " + name + " (orden " + str(list(order)) + "): contador " + name, 1, counters[counter])
        case.check("Caso " + name + ": nueva raíz y árbol balanceado", (expected_root, 1, True),
                   (root(obs), obs.state.tree.height, obs.audit()["ok"]))
        if name in ("LR", "RL"):
            case.check("Caso " + name + ": cuenta como dos giros elementales", 2,
                       counters["count_left_rotations"] + counters["count_right_rotations"])

    obs = observatory()
    obs.enter_stress()
    ids = list(range(1, 26)) + list(range(60, 45, -1))
    for index, event_id in enumerate(ids):
        magnitude = "%.1f" % (2.0 + (event_id % 40) / 20)
        create(obs, event_id, magnitude, "10", (str(500 + index), "450"),
                "2026-09-07T%02d:%02d:00Z" % (6 + index // 20, (index * 3) % 60))
    tree = obs.state.tree
    worst = max(abs(node.balance_factor()) for node in tree.preorder())
    case.check("En estrés hay desbalances mayores que 2", True, worst > 2)
    case.check("La auditoría en estrés no tiene errores (solo desbalance esperado)", (True, False),
               (obs.audit()["ok"], obs.audit()["details"]["balanced"]))
    objects = {i: obs.state.registry.get(i) for i in ids}
    keys = {i: objects[i].key() for i in ids}
    order = inorder(obs)
    references = dict(obs.state.associations.references)
    height_before = tree.height
    result = obs.recover()
    case.check("La recuperación termina y vuelve a modo normal", (True, "NORMAL"), (result["ok"], obs.state.mode))
    height_after = obs.state.tree.height
    case.check("Altura: antes %d, después %d (debe ser ≤ 7 para 40 nodos)" % (height_before, height_after),
               True, height_after <= 7)
    case.check("Se conservan las identidades (mismos objetos evento)", True,
               all(node.getEvent() is objects[node.getEvent().data.event_id] for node in obs.state.tree.inorder()))
    case.check("Se conservan las claves", keys, {i: obs.state.registry.get(i).key() for i in ids})
    case.check("Se conserva el orden (inorden idéntico)", order, inorder(obs))
    case.check("Se conservan las asociaciones", references, dict(obs.state.associations.references))
    case.check("La auditoría confirma el AVL", (True, True), (obs.audit()["ok"], obs.audit()["details"]["balanced"]))
    return case


# ---------------------------------------------------------------- case 5

def case_5_archive():
    case = Case(5, "Archivo masivo de ramas antiguas",
                "Eventos de prioridad baja (M 3.0). Antiguos: 2026-09-01 (más de T = 72 h). "
                "Recientes: 2026-09-07 10:00.")
    # Eligible branch with several events + tie by id
    obs = observatory()
    for event_id in range(1, 8):
        create(obs, event_id, "3.0", time=RECENT if event_id == 4 else OLD)
    preview = obs.archive_preview()["details"]
    case.check("Raíz 4 reciente: ramas elegibles de 3 nodos con raíz 2 y 6 a la misma profundidad; "
               "gana el mayor ID", (6, [5, 6, 7]), (preview["root"], preview["ids"]))
    before = scenario_to_dict(obs.state)
    result = obs.archive_apply(preview["ids"])
    case.check("Se archivan los 3 eventos y salen del AVL", (True, 4), (result["ok"], obs.state.tree.size))
    case.check("Los archivados conservan identidad y datos", ("ARCHIVED", 30),
               (obs.state.registry.get(6).state, obs.state.registry.get(6).data.magnitude10))
    case.check("El AVL sigue balanceado", True, obs.audit()["ok"])
    obs.undo()
    case.check("Deshacer el archivo completo restaura el estado exacto", True, scenario_to_dict(obs.state) == before)

    # Tie broken by depth
    obs = observatory()
    for event_id in (5, 4, 3, 2, 1):
        create(obs, event_id, "3.0", time=RECENT if event_id in (2, 3, 4) else OLD)
    preview = obs.archive_preview()["details"]
    case.check("Hojas elegibles 1 (profundidad 2) y 5 (profundidad 1): gana la más profunda", 1, preview["root"])

    # Low root with a high descendant
    obs = observatory()
    create(obs, 1, "3.0", time=OLD)
    create(obs, 2, "3.0", time=OLD)
    create(obs, 3, "6.5", time=OLD)
    preview = obs.archive_preview()["details"]
    case.check("La raíz SIS-000002 es baja pero contiene a SIS-000003 (alta): no es elegible",
               (2, 1), (root(obs), preview["root"]))
    case.check("La justificación explica el bloqueo", True,
               any(item["root"] == 2 and "SIS-000003" in item["reason"] for item in preview["blocked"]))

    # Whole tree eligible
    obs = observatory()
    for event_id in range(1, 8):
        create(obs, event_id, "3.0", time=OLD)
    preview = obs.archive_preview()["details"]
    case.check("Si todo el árbol es elegible se archiva completo", 7, preview["count"])

    # No eligible branch
    obs = observatory()
    for event_id in range(1, 4):
        create(obs, event_id, "3.0", time=RECENT)
    before = scenario_to_dict(obs.state)
    result = obs.archive_apply()
    case.check("Sin ramas elegibles: se informa y no cambia nada", (False, True),
               (result["ok"], scenario_to_dict(obs.state) == before))
    return case


# ---------------------------------------------------------------- case 6

def case_6_persistence():
    case = Case(6, "Persistencia, rechazo de archivo inválido, versión tras reinicio y deshacer",
                "Escenarios construidos con la fachada; los archivos se escriben como JSON y se vuelven a leer.")
    obs = observatory()
    for event_id in (50, 30, 70, 20, 40, 60, 80, 35):
        create(obs, event_id, "4.0")
    obs.delete_event(30)
    normal = json.loads(json.dumps(obs.export()))
    restored = load_by_topology_from_dict(normal)
    case.check("Topología normal: misma forma tras guardar y cargar", shape(obs.state), shape(restored))
    case.check("Topología normal: mismo escenario completo", True, scenario_to_dict(restored) == normal)

    stress = observatory()
    stress.enter_stress()
    for event_id in range(1, 10):
        create(stress, event_id, "3.0")
    document = json.loads(json.dumps(stress.export()))
    restored = load_by_topology_from_dict(document)
    case.check("Topología en estrés: se carga en modo estrés con la misma forma", ("STRESS", True, 8),
               (restored.mode, shape(restored) == shape(stress.state), restored.tree.height))
    document["mode"] = "NORMAL"
    try:
        load_by_topology_from_dict(document)
        rejected = False
    except ScenarioLoadError:
        rejected = True
    case.check("La misma topología desbalanceada se rechaza en modo normal", True, rejected)

    invalid = json.loads(json.dumps(normal))
    invalid["tree"]["nodes"][0]["height"] = 9
    invalid["events"][0]["priority"] = 3
    before = obs.export()
    result = obs.load_scenario(invalid, "topology")
    case.check("Archivo inconsistente rechazado sin alterar el estado", (False, True),
               (result["ok"], obs.export() == before))

    directory = tempfile.mkdtemp()
    first = Observatory(versions_dir=directory)
    create(first, 1, "5.0")
    create(first, 2, "6.1")
    saved = first.export()
    first.save_version("demo")
    second = Observatory(versions_dir=directory)       # like restarting the program
    second.restore_version("demo")
    case.check("Versión restaurada en una instancia nueva", True, second.export() == saved)

    record = second.state.registry.get(1)
    second.correct_event(1, {"magnitude": "6.6", "station": STATION})
    case.check("Corrección aplicada", "(3, 6.6, 1)", key_text(record.key()))
    second.undo()
    case.check("Deshacer la corrección recupera clave y revisión", ("(2, 5.0, 1)", 1),
               (key_text(second.state.registry.get(1).key()), second.state.registry.get(1).revision))
    second.enqueue_reports([{"id": 2, "magnitude": "6.1", "depth": "10", "x": "950", "y": "950",
                             "time": RECENT, "station": STATION, "revision": 0 + 1},
                            {"id": 9, "magnitude": "3.0", "depth": "10", "x": "1", "y": "1",
                             "time": RECENT, "station": STATION, "revision": 1}])
    before_step = second.export()
    second.process_step()
    case.check("Paso de cola procesado (confirmación de SIS-000002)", 1, len(second.state.pending_reports.to_list()))
    second.undo()
    queue = [r.data.event_id for r in second.state.pending_reports.to_list()]
    case.check("Deshacer el paso devuelve el reporte a su posición en la cola", [2, 9], queue)
    case.check("Deshacer el paso recupera el escenario exacto", True, second.export() == before_step)
    return case


ALL_CASES = [
    case_1_limits_and_ties,
    case_2_correction_and_old_report,
    case_3_late_report,
    case_4_rotations_and_recovery,
    case_5_archive,
    case_6_persistence,
]


def report_markdown(cases):
    lines = ["# Evidencia de los casos obligatorios (sección 16)", "",
             "Generado ejecutando `python -m scripts.section16_cases` sobre el código real. "
             "Cada fila compara el resultado esperado con el obtenido.", ""]
    for case in cases:
        lines.append("## Caso %d. %s — %s" % (case.number, case.title, "CORRECTO" if case.ok else "CON FALLOS"))
        lines.append("")
        lines.append("**Estado inicial:** " + case.initial)
        lines.append("")
        lines.append("| Verificación | Esperado | Obtenido | ¿Coincide? |")
        lines.append("|---|---|---|---|")
        for item in case.checks:
            def cell(text):
                return text.replace("|", "\\|").replace("\n", " ")
            lines.append("| %s | %s | %s | %s |" % (cell(item["description"]), cell(item["expected"]),
                                                     cell(item["obtained"]), "Sí" if item["ok"] else "**No**"))
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    cases = [function() for function in ALL_CASES]
    destination = Path(__file__).resolve().parents[1] / "docs_entrega" / "evidencia_casos_seccion16.md"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(report_markdown(cases), encoding="utf-8")
    for case in cases:
        passed = sum(item["ok"] for item in case.checks)
        print("Caso %d: %d/%d verificaciones correctas" % (case.number, passed, len(case.checks)))
    print("Evidencia escrita en", destination)


if __name__ == "__main__":
    main()
