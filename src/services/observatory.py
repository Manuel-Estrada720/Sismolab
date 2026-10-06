"""Observatory: the facade that the API (and the tests) use.

Every action that changes the scenario goes through `_run`:
1. a complete snapshot is taken with scenario_to_dict;
2. the action runs;
3. if it fails, the snapshot is restored, so an invalid action never leaves
   the scenario half-changed;
4. if it succeeds, the snapshot is pushed on the undo stack.

Every public method returns {"ok": bool, "message": str, "details": ...}.
"""

import json
import sys

from ..models.event_data import EventData
from ..models.event_record import ACTIVE, ARCHIVED, DELETED, PENDING
from ..models.report import Report
from ..models.scenario_state import ScenarioState
from ..models.units import format_utc, from_tenths, parse_utc, to_tenths
from ..models.zone import default_zones
from ..persistence.exporter import (
    ScenarioLoadError,
    build_bst,
    load_by_insertions_from_dict,
    load_by_topology_from_dict,
    scenario_to_dict,
)
from .archive_service import ArchiveService
from .audit_service import AuditService
from .comparison_service import ComparisonService
from .event_service import EventService
from .priority import HIGH, LOW, MEDIUM
from .query_service import QueryService
from .queue_service import QueueService
from .report_processor import (
    CONFIRMED,
    CONFLICT,
    CREATED,
    INVALID,
    OLD,
    REACTIVATED,
    REJECTED,
    UPDATED,
    ReportProcessor,
)
from .tree_info import is_costly, key_text, moved_events, node_positions, sis, subtree_heights
from .undo_service import UndoService
from .version_service import VersionService

# Stress mode can build very deep trees; some helpers are recursive
sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))

DEFAULT_CLOCK = "2026-09-07T12:00:00Z"

DECISION_NAMES = {
    CREATED: "Alta",
    UPDATED: "Corrección",
    REACTIVATED: "Reactivación",
    CONFIRMED: "Confirmación",
    CONFLICT: "Conflicto",
    OLD: "Reporte antiguo",
    REJECTED: "Rechazado (eliminado)",
    INVALID: "Inválido",
}

STATE_NAMES = {ACTIVE: "activo", ARCHIVED: "archivado", DELETED: "eliminado"}


def new_default_state():
    """Empty scenario with the default zones, stations and parameters."""
    return ScenarioState(zones=default_zones(), clock_epoch=parse_utc(DEFAULT_CLOCK))


def response(ok, message, details=None):
    return {"ok": ok, "message": message, "details": details}


# ---------------------------------------------------------------- form parsing

def parse_id(value):
    """Accept 10, "10" or "SIS-000010"."""
    text = str(value).strip().upper()
    if text.startswith("SIS-"):
        text = text[4:]
    if not text.isdigit() or not 1 <= int(text) <= 999999:
        raise ValueError("El identificador debe ser un entero entre 1 y 999999")
    return int(text)


def _is_blank(form, field):
    return field not in form or form[field] is None or str(form[field]).strip() == ""


def _tenths(form, field, label):
    if _is_blank(form, field):
        raise ValueError("Falta el campo " + label)
    try:
        return to_tenths(form[field])
    except ValueError as error:
        raise ValueError(label + ": " + str(error))


def _positive_int(form, field, label):
    text = str(form.get(field, "")).strip()
    if not text.isdigit() or int(text) < 1:
        raise ValueError(label + " debe ser un entero positivo")
    return int(text)


def parse_event_data(form, base=None):
    """Build EventData from user text. Missing fields come from `base` (corrections)."""
    values = {}
    names = {"magnitude": "magnitud", "depth": "profundidad", "x": "x", "y": "y"}
    for field, label in names.items():
        if base is not None and _is_blank(form, field):
            values[field] = {
                "magnitude": base.magnitude10,
                "depth": base.depth10,
                "x": base.x10,
                "y": base.y10,
            }[field]
        else:
            values[field] = _tenths(form, field, label)
    if base is not None and _is_blank(form, "time"):
        time_epoch = base.time_epoch
    else:
        if _is_blank(form, "time"):
            raise ValueError("Falta la fecha y hora de ocurrencia")
        time_epoch = parse_utc(str(form["time"]))
    event_id = base.event_id if base is not None else parse_id(form.get("id", ""))
    return EventData(
        event_id, values["magnitude"], values["depth"], values["x"], values["y"], time_epoch
    )


def report_view(report, position=None):
    data = report.data
    view = {
        "id": data.event_id,
        "label": sis(data.event_id),
        "magnitude": from_tenths(data.magnitude10),
        "depth": from_tenths(data.depth10),
        "x": from_tenths(data.x10),
        "y": from_tenths(data.y10),
        "time": format_utc(data.time_epoch),
        "revision": report.revision,
        "station": report.station,
    }
    if position is not None:
        view["position"] = position
    return view


class Observatory:

    def __init__(self, state=None, versions_dir=None):
        self.state = state if state is not None else new_default_state()
        self.undo_service = UndoService()
        self.versions = VersionService(versions_dir)
        self.history = []        # every action, newest last
        self.queue_log = []      # one entry per processed report
        self.last_action = {
            "label": "Inicio",
            "message": "Escenario vacío listo. Cree eventos, cargue un archivo o encole reportes.",
            "ok": True,
            "moved": [],
        }
        self._wire()

    def _wire(self):
        """(Re)create the services so they point to the current state."""
        self.processor = ReportProcessor(self.state)
        self.events = EventService(self.state, self.processor)
        self.queue = QueueService(self.state, self.processor)
        self.archive = ArchiveService(self.state)
        self.queries = QueryService(self.state)
        self.auditor = AuditService(self.state)
        self.comparison = ComparisonService(self.state)

    def _restore(self, snapshot):
        self.state = load_by_topology_from_dict(snapshot)
        self._wire()

    def _remember(self, label, result, moved=None):
        entry = {
            "label": label,
            "message": result["message"],
            "ok": result["ok"],
            "moved": moved or [],
        }
        self.last_action = entry
        self.history.append({"label": label, "message": result["message"], "ok": result["ok"]})
        if len(self.history) > 300:
            self.history.pop(0)

    def _run(self, label, action, replaces=False):
        """Run one undoable action. `action` returns (ok, message, details).

        replaces=True means the action swaps the whole scenario (load, restore,
        new): then counter differences are not rotations of this action."""
        snapshot = scenario_to_dict(self.state)
        positions_before = node_positions(self.state.tree)
        counters_before = self.state.rotation_counters()
        try:
            ok, message, details = action()
        except ScenarioLoadError as error:
            count = len(error.problems)
            message = str(count) + " problema(s) detectado(s). " + str(error.problems[0])
            ok, details = False, {"problems": error.problems}
        except (ValueError, TypeError, KeyError) as error:
            ok, message, details = False, str(error).strip("'\""), None
        except Exception as error:      # unexpected bug: still never leave a partial state
            ok, message, details = False, "Error inesperado (" + type(error).__name__ + "): " + str(error), None

        if not ok:
            # Guarantee: a failed action leaves the scenario exactly as before
            self._restore(snapshot)
            result = response(False, message, details)
            self._remember(label, result)
            return result

        self.undo_service.push(label, snapshot)
        details = details if details is not None else {}
        moved = moved_events(positions_before, node_positions(self.state.tree))
        counters_after = self.state.rotation_counters()
        rotations = {}
        for name, value in counters_after.items():
            if value != counters_before[name]:
                rotations[name] = value - counters_before[name]
        if replaces:
            moved, rotations = [], {}
        details["moved"] = moved
        details["rotations"] = rotations
        details["rotation_text"] = (
            "No aplica: se reemplazó el escenario completo" if replaces else self._rotation_text(rotations)
        )
        result = response(True, message, details)
        self._remember(label, result, moved)
        return result

    @staticmethod
    def _rotation_text(rotations):
        if not rotations:
            return "Sin rotaciones"
        names = {
            "count_ll": "LL", "count_rr": "RR", "count_lr": "LR", "count_rl": "RL",
            "count_left_rotations": "giros a la izquierda",
            "count_right_rotations": "giros a la derecha",
        }
        return ", ".join(names[name] + ": " + str(value) for name, value in rotations.items())

    # ---------------------------------------------------------------- events

    def _station(self, form):
        station = str(form.get("station", "")).strip()
        if not station:
            raise ValueError("Seleccione la estación que origina el registro")
        if not self.state.has_station(station):
            raise ValueError("La estación " + station + " no existe en el escenario")
        return station

    def create_event(self, form):
        def action():
            data = parse_event_data(form)
            station = self._station(form)
            ok, message = self.events.create_event(data, station)
            return ok, sis(data.event_id) + ": " + message, {"event_id": data.event_id}
        return self._run("Crear evento", action)

    def correct_event(self, event_id, form):
        def action():
            record = self.state.registry.get(event_id)
            if record is None:
                return False, "El evento " + sis(event_id) + " no existe", None
            old_key = record.key()
            data = parse_event_data(form, base=record.data)
            station = self._station(form)
            ok, message = self.events.correct_event(event_id, data, station)
            details = {
                "event_id": event_id,
                "old_key": key_text(old_key),
                "new_key": key_text(record.key()),
                "key_changed": old_key != record.key(),
            }
            return ok, sis(event_id) + ": " + message, details
        return self._run("Corregir " + sis(event_id), action)

    def mark_reviewed(self, event_id):
        def action():
            ok, message = self.events.mark_reviewed(event_id)
            return ok, sis(event_id) + ": " + message, {"event_id": event_id}
        return self._run("Revisar " + sis(event_id), action)

    def delete_event(self, event_id):
        def action():
            ok, message = self.events.delete_event(event_id)
            return ok, sis(event_id) + ": " + message, {"event_id": event_id}
        return self._run("Eliminar " + sis(event_id), action)

    def get_event(self, event_id):
        info = self.events.get_event_info(event_id)
        if info is None:
            return response(False, "No existe ningún evento con identificador " + sis(event_id))
        located = self.queries.find_by_id(event_id)
        record = self.state.registry.get(event_id)
        details = self._event_view(record, located.get("node_depth"))
        details["examined"] = located["examined"]
        if record.state == ACTIVE:
            details["node_height"] = info["node_height"]
            details["balance_factor"] = info["balance_factor"]
            details["search_cost"] = info["visited"]
        if record.state != DELETED:
            details["associations"] = self.queries.associations_of(event_id)
        message = sis(event_id) + " está " + STATE_NAMES[record.state]
        return response(True, message, details)

    # ---------------------------------------------------------------- queue

    def enqueue_reports(self, items):
        def action():
            if not isinstance(items, list) or not items:
                return False, "La ráfaga debe tener al menos un reporte", None
            reports = []
            for index, form in enumerate(items):
                try:
                    data = parse_event_data(form)
                    revision = _positive_int(form, "revision", "La revisión")
                    reports.append(Report(data, revision, self._station(form)))
                except ValueError as error:
                    raise ValueError("Reporte " + str(index + 1) + ": " + str(error))
            count = self.queue.enqueue_burst(reports)
            stations = sorted({report.station for report in reports})
            message = (str(count) + " reporte(s) encolado(s) de " + str(len(stations))
                       + " estación(es); se aplicarán al procesar la cola")
            return True, message, {"count": count, "stations": stations}
        return self._run("Encolar ráfaga", action)

    def process_step(self):
        entry = {}

        def action():
            position = self.state.pending_reports.size()
            report, result, message = self.queue.step()
            entry.update({
                "station": report.station,
                "event_id": report.data.event_id,
                "label": sis(report.data.event_id),
                "revision": report.revision,
                "decision": result,
                "decision_name": DECISION_NAMES[result],
                "detail": message,
                "remaining": position - 1,
            })
            text = (report.station + " → " + sis(report.data.event_id) + " rev. "
                    + str(report.revision) + ": " + DECISION_NAMES[result] + ". " + message)
            return True, text, dict(entry)

        label = "Procesar reporte de la cola"
        if not self.state.pending_reports.is_empty():
            first = self.state.pending_reports.peek()
            label = "Paso de cola: " + sis(first.data.event_id) + " (" + first.station + ")"
        result = self._run(label, action)
        if result["ok"]:
            log = dict(result["details"])
            self.queue_log.append(log)
            if len(self.queue_log) > 300:
                self.queue_log.pop(0)
        return result

    def process_all(self):
        steps = []
        while not self.state.pending_reports.is_empty():
            result = self.process_step()
            if not result["ok"]:
                return response(False, result["message"], {"steps": steps})
            steps.append(result["details"])
        if not steps:
            return response(False, "La cola de reportes está vacía")
        return response(True, "Se procesaron " + str(len(steps)) + " reporte(s); cada paso se puede deshacer por separado", {"steps": steps})

    # ---------------------------------------------------------------- stress

    def enter_stress(self):
        def action():
            if self.state.tree.stress_mode:
                return False, "El árbol ya está en modo estrés", None
            self.state.mode = "STRESS"
            return True, "Modo estrés activo: se conserva el orden BST pero se aplazan las rotaciones", {}
        return self._run("Activar modo estrés", action)

    def recover(self):
        def action():
            tree = self.state.tree
            if not tree.stress_mode:
                return False, "El árbol ya está en modo normal; no hay nada que recuperar", None
            height_before = tree.height
            unbalanced_before = len(tree.audit_balance())
            try:
                total = tree.restore_avl_balance()
            except RuntimeError:
                return False, "La recuperación no convergió; se mantiene el modo estrés", None
            report = AuditService(self.state).audit()
            if not report["ok"] or not report["balanced"] or tree.stress_mode:
                return False, "La auditoría no confirmó el equilibrio; se mantiene el modo estrés", report
            message = ("Recuperación global: " + str(unbalanced_before) + " nodo(s) desbalanceado(s) "
                       "reparados con " + str(total) + " giros; altura " + str(height_before)
                       + " → " + str(tree.height) + ". La auditoría confirma el AVL: modo normal")
            return True, message, {
                "height_before": height_before,
                "height_after": tree.height,
                "unbalanced_before": unbalanced_before,
                "rotations_total": total,
            }
        return self._run("Recuperación global del AVL", action)

    # ---------------------------------------------------------------- archive

    def archive_preview(self):
        preview = self.archive.select()
        if preview is None:
            _, blocked = self.archive.evaluate()
            return response(False, "No existe una rama elegible: no se archiva nada",
                            {"blocked": blocked[:10]})
        preview["labels"] = [sis(event_id) for event_id in preview["ids"]]
        return response(True, "Rama elegible con raíz " + sis(preview["root"]) + " ("
                        + str(preview["count"]) + " evento(s))", preview)

    def archive_apply(self, expected_ids=None):
        def action():
            preview = self.archive.select()
            if preview is None:
                return False, "No existe una rama elegible: el estado se conserva", None
            if expected_ids is not None and sorted(expected_ids) != preview["ids"]:
                return False, "La selección cambió desde la vista previa; vuelva a revisarla", None
            ids = self.archive.apply(preview["ids"])
            message = ("Rama con raíz " + sis(preview["root"]) + " archivada: "
                       + str(len(ids)) + " evento(s) pasan al histórico")
            return True, message, {"ids": ids, "root": preview["root"],
                                   "justification": preview["justification"]}
        return self._run("Archivar rama de eventos antiguos", action)

    # ---------------------------------------------------------------- clock and parameters

    def advance_clock(self, hours=None, to=None):
        def action():
            if to not in (None, ""):
                new_clock = parse_utc(str(to))
            else:
                tenths = _tenths({"hours": hours}, "hours", "Horas a avanzar")
                if tenths <= 0:
                    return False, "Las horas a avanzar deben ser positivas", None
                new_clock = self.state.clock_epoch + tenths * 360
            if new_clock <= self.state.clock_epoch:
                return False, "El reloj solo puede avanzar hacia el futuro", None
            old = self.state.clock_epoch
            self.state.clock_epoch = new_clock
            return True, ("Reloj: " + format_utc(old) + " → " + format_utc(new_clock)), {
                "clock": format_utc(new_clock)}
        return self._run("Avanzar reloj", action)

    def set_parameters(self, form):
        def action():
            changes = []
            parameters = dict(self.state.parameters)
            for name in ("W", "R", "T"):
                if not _is_blank(form, name):
                    tenths = _tenths(form, name, name)
                    if tenths <= 0:
                        return False, "El parámetro " + name + " debe ser positivo", None
                    parameters[name] = from_tenths(tenths)
            if not _is_blank(form, "L"):
                text = str(form["L"]).strip()
                if not text.isdigit():
                    return False, "L debe ser un entero no negativo", None
                parameters["L"] = int(text)
            for name in ("W", "R", "L", "T"):
                if parameters[name] != self.state.parameters[name]:
                    changes.append(name + ": " + str(self.state.parameters[name]) + " → " + str(parameters[name]))
            if not changes:
                return False, "No hay cambios en los parámetros", None
            old_references = dict(self.state.associations.references)
            self.state.parameters = parameters
            self.state._validate_parameters()
            self.state.associations.set_parameters(self.state.w10, self.state.r10)
            changed = sorted(
                event_id for event_id in set(old_references) | set(self.state.associations.references)
                if old_references.get(event_id) != self.state.associations.references.get(event_id)
            )
            message = "Parámetros actualizados (" + "; ".join(changes) + ")"
            if changed:
                message += ". Asociaciones recalculadas: cambiaron " + str(len(changed))
            return True, message, {"parameters": parameters, "associations_changed": changed}
        return self._run("Cambiar parámetros", action)

    # ---------------------------------------------------------------- undo and versions

    def undo(self):
        entry = self.undo_service.pop()
        if entry is None:
            result = response(False, "No hay acciones para deshacer")
            self._remember("Deshacer", result)
            return result
        before = node_positions(self.state.tree)
        self._restore(entry["snapshot"])
        moved = moved_events(before, node_positions(self.state.tree))
        result = response(True, "Se deshizo: " + entry["label"], {"moved": moved, "undone": entry["label"]})
        self._remember("Deshacer", result, moved)
        return result

    def save_version(self, name):
        try:
            file_name = self.versions.save(name, scenario_to_dict(self.state))
        except (ValueError, OSError) as error:
            return response(False, "No se guardó la versión: " + str(error))
        result = response(True, "Versión '" + str(name).strip() + "' guardada en data/versions/" + file_name)
        self._remember("Guardar versión", result)
        return result

    def list_versions(self):
        return response(True, "Versiones guardadas", {"versions": self.versions.list()})

    def restore_version(self, name):
        def action():
            document = self.versions.load(name)
            new_state = load_by_topology_from_dict(document)
            self.state = new_state
            self._wire()
            return True, "Versión '" + str(name).strip() + "' restaurada (se puede deshacer)", {}
        return self._run("Restaurar versión " + str(name), action, replaces=True)

    # ---------------------------------------------------------------- files

    def load_scenario(self, content, mode):
        def action():
            document = content
            if isinstance(content, str):
                try:
                    document = json.loads(content)
                except json.JSONDecodeError as error:
                    raise ScenarioLoadError(["El archivo no es JSON válido: " + str(error)])
            if mode == "topology":
                new_state = load_by_topology_from_dict(document)
                self.state = new_state
                self._wire()
                text = ("Escenario cargado conservando la topología (" + str(new_state.tree.size)
                        + " nodos activos, modo " + ("estrés" if new_state.tree.stress_mode else "normal") + ")")
                return True, text, {"mode": new_state.mode}
            if mode == "insertions":
                new_state, bst = load_by_insertions_from_dict(document)
                self.state = new_state
                self._wire()
                details = {
                    "avl": self._tree_stats(new_state.tree, new_state.tree.height, new_state.tree.count_leaves()),
                    "bst": self._tree_stats(bst, bst.height(), bst.count_leaves()),
                }
                text = ("Carga por inserciones: " + str(new_state.tree.size) + " eventos insertados en el mismo "
                        "orden en el AVL (altura " + str(details["avl"]["height"]) + ") y en el BST (altura "
                        + str(details["bst"]["height"]) + ")")
                return True, text, details
            return False, "Modo de carga desconocido: use 'topology' o 'insertions'", None

        result = self._run("Cargar archivo JSON", action, replaces=True)
        if not result["ok"]:
            result["message"] = "No se cargó el archivo; el escenario actual se conserva. " + result["message"]
        return result

    @staticmethod
    def _tree_stats(tree, height, leaves):
        root = tree.root.getEvent().data.event_id if tree.root is not None else None
        return {"root": root, "root_label": sis(root) if root else None,
                "height": height, "max_depth": height, "leaves": leaves}

    def new_scenario(self):
        def action():
            self.state = new_default_state()
            self._wire()
            return True, "Nuevo escenario vacío con las zonas y estaciones por defecto", {}
        return self._run("Nuevo escenario", action, replaces=True)

    def export(self):
        return scenario_to_dict(self.state)

    # ---------------------------------------------------------------- queries

    def query(self, name, params):
        try:
            if name == "pending":
                data = self.queries.pending_top(_positive_int(params, "k", "k"))
            elif name == "magnitude":
                data = self.queries.magnitude_range(
                    _tenths(params, "min", "magnitud mínima"), _tenths(params, "max", "magnitud máxima"))
            elif name == "depth-dates":
                data = self.queries.depth_and_dates(
                    _tenths(params, "max_depth", "profundidad máxima"),
                    parse_utc(str(params.get("from", ""))), parse_utc(str(params.get("to", ""))))
            elif name == "costly":
                data = self.queries.costly_events()
            elif name == "associations":
                data = self.queries.associations_of(parse_id(params.get("id", "")))
            else:
                return response(False, "Consulta desconocida: " + str(name))
        except ValueError as error:
            return response(False, str(error))
        count = len(data["results"]) if "results" in data else len(data.get("candidates", []))
        return response(True, str(count) + " resultado(s); nodos AVL examinados: " + str(data["examined"]), data)

    def audit(self):
        report = self.auditor.audit()
        if report["ok"] and report["expected"]:
            message = ("Sin errores de orden ni de metadatos. Desbalance esperado por modo estrés en "
                       + str(len(report["expected"])) + " nodo(s)")
        elif report["ok"]:
            message = "Estructura correcta: orden global, claves, enlaces, alturas y balance verificados"
        else:
            message = "Se encontraron " + str(len(report["errors"])) + " inconsistencia(s)"
        return response(report["ok"], message, report)

    def compare(self):
        return response(True, "Comparación AVL/BST con los mismos eventos", self.comparison.compare())

    # ---------------------------------------------------------------- state for the GUI

    def _event_view(self, record, node_depth=None):
        data = record.data
        event_id = data.event_id
        view = {
            "id": event_id,
            "label": sis(event_id),
            "state": record.state,
            "state_name": STATE_NAMES[record.state],
            "magnitude": from_tenths(data.magnitude10),
            "depth": from_tenths(data.depth10),
            "x": from_tenths(data.x10),
            "y": from_tenths(data.y10),
            "time": format_utc(data.time_epoch),
            "revision": record.revision,
            "stations": list(record.stations),
            "priority": record.priority,
            "key": [record.priority, from_tenths(data.magnitude10), event_id],
            "key_text": key_text(record.key()),
            "attention": record.attention,
            "populated": self.state.zones.is_populated(data.x10, data.y10),
            "reference": self.state.associations.reference_of(event_id),
            "used_by": self.state.associations.used_by(event_id),
        }
        if node_depth is not None:
            view["node_depth"] = node_depth
            view["costly"] = is_costly(record, node_depth, self.state.parameters["L"])
        return view

    def _tree_view(self, tree, moved, mark_costly=True):
        heights = subtree_heights(tree)
        positions = node_positions(tree)
        limit = self.state.parameters["L"]
        nodes = []
        for index, node in enumerate(tree.inorder()):
            record = node.getEvent()
            event_id = record.data.event_id
            left, right = node.getLeft(), node.getRight()
            left_h = heights[left.getEvent().data.event_id] if left is not None else -1
            right_h = heights[right.getEvent().data.event_id] if right is not None else -1
            depth = positions[event_id][2]
            nodes.append({
                "id": event_id,
                "label": sis(event_id),
                "key": [record.priority, from_tenths(record.data.magnitude10), event_id],
                "key_text": key_text(record.key()),
                "priority": record.priority,
                "attention": record.attention,
                "left": left.getEvent().data.event_id if left is not None else None,
                "right": right.getEvent().data.event_id if right is not None else None,
                "depth": depth,
                "height": heights[event_id],
                "balance": left_h - right_h,
                "unbalanced": abs(left_h - right_h) > 1,
                # The "costly access" mark is a rule of the active AVL only
                "costly": mark_costly and is_costly(record, depth, limit),
                "moved": event_id in moved,
                "inorder": index,
            })
        height = max(heights.values()) if heights else -1
        leaves = sum(1 for n in nodes if n["left"] is None and n["right"] is None)
        return {
            "root": tree.root.getEvent().data.event_id if tree.root is not None else None,
            "nodes": nodes,
            "size": len(nodes),
            "height": height,
            "max_depth": height,
            "leaves": leaves,
        }

    def state_view(self):
        state = self.state
        tree = state.tree
        positions = node_positions(tree)
        moved = set(self.last_action.get("moved", []))
        events = []
        by_priority = {LOW: 0, MEDIUM: 0, HIGH: 0}
        pending = 0
        costly = 0
        for record in state.registry.records.values():
            depth = positions[record.data.event_id][2] if record.state == ACTIVE else None
            view = self._event_view(record, depth)
            events.append(view)
            if record.state == ACTIVE:
                by_priority[record.priority] += 1
                pending += 1 if record.attention == PENDING else 0
                costly += 1 if view["costly"] else 0
        events.sort(key=lambda item: item["id"])

        def ids(nodes):
            return [node.getEvent().data.event_id for node in nodes]

        indicators = {
            "active": state.registry.count_by_state(ACTIVE),
            "archived": state.registry.count_by_state(ARCHIVED),
            "deleted": state.registry.count_by_state(DELETED),
            "height": tree.height,
            "leaves": tree.count_leaves(),
            "by_priority": {str(p): n for p, n in by_priority.items()},
            "pending": pending,
            "costly": costly,
            "traversals": {
                "inorder": ids(tree.inorder()),
                "preorder": ids(tree.preorder()),
                "postorder": ids(tree.postorder()),
                "levels": ids(tree.level_order()),
            },
            "unbalanced": len(tree.audit_balance()),
        }
        return {
            "mode": state.mode,
            "clock": format_utc(state.clock_epoch),
            "parameters": dict(state.parameters),
            "stations": list(state.stations),
            "zones": [
                {"zone_id": z.zone_id, "populated": z.populated, "x1": from_tenths(z.x1),
                 "y1": from_tenths(z.y1), "x2": from_tenths(z.x2), "y2": from_tenths(z.y2)}
                for z in state.zones.zones
            ],
            "metrics": state.all_metrics(),
            "queue": [report_view(r, i + 1) for i, r in enumerate(state.pending_reports.to_list())],
            "undo": {
                "available": self.undo_service.can_undo(),
                "size": self.undo_service.size(),
                "labels": self.undo_service.labels()[:15],
            },
            "events": events,
            "avl": self._tree_view(tree, moved),
            "bst": self._tree_view(build_bst(state), set(), mark_costly=False),
            "indicators": indicators,
            "last_action": self.last_action,
            "history": list(reversed(self.history[-60:])),
            "queue_log": list(reversed(self.queue_log[-80:])),
        }
