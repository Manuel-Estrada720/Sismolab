"""JSON serialization and reconstruction for SismoLab scenarios.

Schema version 2 (written by this module):
- Dates use ISO 8601 UTC text ("2026-09-07T10:00:00Z").
- Magnitude, depth and coordinates use a decimal point (5.2), but inside the
  program they are integers in tenths (52) to keep comparisons exact.
- The AVL is saved by topology: root id plus left/right ids of every node.

Files with schema version 1 (epoch seconds and tenths) are still accepted:
they are converted to version 2 before validation.

Every loader builds a brand new ScenarioState. The caller replaces its
current scenario only when loading succeeds, so a bad file never leaves a
half-loaded scenario.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models.event_data import EventData
from ..models.event_record import ACTIVE, EventRecord
from ..models.event_registry import EventRegistry
from ..models.report import Report
from ..models.scenario_state import DEFAULT_STATIONS, METRIC_NAMES, ROTATION_NAMES, ScenarioState
from ..models.units import format_utc, from_tenths, parse_utc, to_tenths
from ..models.zone import Zone, ZoneMap, default_zones
from ..services.association_service import AssociationService
from ..services.priority import calculate_priority
from ..services.tree_info import key_text
from ..structures.Avl import AVLTree
from ..structures.Bst import BSTTree
from ..structures.Node import Node
from ..structures.Queue import Queue
from ..structures.comparator import compare_keys


SCHEMA_VERSION = 2
EXECUTION_MODES = {"NORMAL", "STRESS"}
ATTENTION_STATES = {"PENDING", "REVIEWED"}
LIFECYCLE_STATES = {"ACTIVE", "ARCHIVED", "DELETED"}


class ScenarioLoadError(ValueError):
    """A file that cannot be loaded. `problems` lists every problem found."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_dict(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} debe ser un objeto JSON")
    return value


def _decimal(raw: Any, label: str) -> int:
    """Read a decimal number from JSON and return it in tenths."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValueError(f"{label} debe ser un número")
    try:
        return to_tenths(raw)
    except ValueError as error:
        raise ValueError(f"{label}: {error}")


# ---------------------------------------------------------------- events

def _data_to_dict(data: EventData) -> Dict[str, Any]:
    return {
        "id": data.event_id,
        "magnitude": from_tenths(data.magnitude10),
        "depth": from_tenths(data.depth10),
        "x": from_tenths(data.x10),
        "y": from_tenths(data.y10),
        "time": format_utc(data.time_epoch),
    }


def _dict_to_data(raw: Any, label: str) -> EventData:
    raw = _require_dict(raw, label)
    event_id = raw.get("id")
    if not _is_int(event_id):
        raise ValueError(f"{label}.id debe ser un entero")
    try:
        return EventData(
            event_id,
            _decimal(raw.get("magnitude"), f"{label}.magnitude"),
            _decimal(raw.get("depth"), f"{label}.depth"),
            _decimal(raw.get("x"), f"{label}.x"),
            _decimal(raw.get("y"), f"{label}.y"),
            parse_utc(raw.get("time")),
        )
    except ValueError as error:
        message = str(error)
        if message.startswith(label):
            raise
        raise ValueError(f"{label} (evento {event_id}): {message}")


def _record_to_dict(record: EventRecord) -> Dict[str, Any]:
    result = _data_to_dict(record.data)
    result.update(
        {
            "revision": record.revision,
            "priority": record.priority,
            "stations": list(record.stations),
            "attention": record.attention,
            "state": record.state,
        }
    )
    return result


def _dict_to_record(
    raw: Any, zones: ZoneMap, clock_epoch: int, stations: List[str], label: str
) -> EventRecord:
    data = _dict_to_data(raw, label)
    if data.time_epoch > clock_epoch:
        raise ValueError(f"{label} (evento {data.event_id}) ocurre después del reloj")

    revision = raw.get("revision")
    if not _is_int(revision) or revision < 1:
        raise ValueError(f"{label}.revision debe ser un entero positivo")

    record_stations = raw.get("stations")
    if (
        not isinstance(record_stations, list)
        or not record_stations
        or any(not isinstance(station, str) or not station for station in record_stations)
        or len(record_stations) != len(set(record_stations))
    ):
        raise ValueError(f"{label}.stations debe ser una lista de textos sin repetir")
    for station in record_stations:
        if station not in stations:
            raise ValueError(f"{label} usa la estación desconocida {station!r}")

    attention = raw.get("attention")
    state = raw.get("state")
    if not isinstance(attention, str) or attention not in ATTENTION_STATES:
        raise ValueError(f"{label}.attention debe ser PENDING o REVIEWED")
    if not isinstance(state, str) or state not in LIFECYCLE_STATES:
        raise ValueError(f"{label}.state debe ser ACTIVE, ARCHIVED o DELETED")

    expected_priority = calculate_priority(data, zones)
    if raw.get("priority") != expected_priority:
        raise ValueError(
            f"{label}: la prioridad guardada {raw.get('priority')!r} no coincide "
            f"con la calculada ({expected_priority}) para el evento {data.event_id}"
        )

    record = EventRecord(data, revision, expected_priority, record_stations[0])
    record.stations = list(record_stations)
    record.attention = attention
    record.state = state
    return record


# ---------------------------------------------------------------- zones

def _zone_to_dict(zone: Zone) -> Dict[str, Any]:
    return {
        "zone_id": zone.zone_id,
        "populated": zone.populated,
        "x1": from_tenths(zone.x1),
        "y1": from_tenths(zone.y1),
        "x2": from_tenths(zone.x2),
        "y2": from_tenths(zone.y2),
    }


def _dict_to_zones(raw_zones: Any) -> ZoneMap:
    if not isinstance(raw_zones, list):
        raise ValueError("zones debe ser una lista")

    zones = []
    seen_ids = set()
    for index, raw in enumerate(raw_zones):
        label = f"zones[{index}]"
        raw = _require_dict(raw, label)
        zone_id = raw.get("zone_id")
        populated = raw.get("populated")
        if not isinstance(zone_id, str) or not zone_id or zone_id in seen_ids:
            raise ValueError(f"{label}.zone_id debe ser un texto único")
        if not isinstance(populated, bool):
            raise ValueError(f"{label}.populated debe ser true o false")
        bounds = [_decimal(raw.get(name), f"{label}.{name}") for name in ("x1", "y1", "x2", "y2")]
        if any(not 0 <= value <= 10000 for value in bounds):
            raise ValueError(f"{label}: los límites deben estar entre 0.0 y 1000.0 km")
        x1, y1, x2, y2 = bounds
        if x1 > x2 or y1 > y2:
            raise ValueError(f"{label}: los límites están invertidos")
        seen_ids.add(zone_id)
        zones.append(Zone(zone_id, populated, x1, y1, x2, y2))

    return ZoneMap(zones)


# ---------------------------------------------------------------- reports

def _report_to_dict(report: Report) -> Dict[str, Any]:
    result = _data_to_dict(report.data)
    result["revision"] = report.revision
    result["station"] = report.station
    return result


def _dict_to_report(raw: Any, stations: List[str], label: str) -> Report:
    data = _dict_to_data(raw, label)
    revision = raw.get("revision")
    station = raw.get("station")
    if not _is_int(revision) or revision < 1:
        raise ValueError(f"{label}.revision debe ser un entero positivo")
    if not isinstance(station, str) or station not in stations:
        raise ValueError(f"{label}: la estación {station!r} no existe en el escenario")
    return Report(data, revision, station)


# ---------------------------------------------------------------- tree

def _tree_to_dict(tree: AVLTree, registry: EventRegistry) -> Dict[str, Any]:
    """Serialize AVL links by event identity, retaining the exact topology."""
    nodes = []
    seen_node_ids = set()
    seen_event_ids = set()
    stack = [tree.root] if tree.root is not None else []

    while stack:
        node = stack.pop()
        node_identity = id(node)
        if node_identity in seen_node_ids:
            raise ValueError("El AVL contiene un ciclo o un nodo repetido")
        seen_node_ids.add(node_identity)

        record = node.getEvent()
        event_id = record.data.event_id
        if event_id in seen_event_ids:
            raise ValueError(f"El AVL contiene dos veces el evento {event_id}")
        if registry.get(event_id) is not record or record.state != ACTIVE:
            raise ValueError(f"El evento {event_id} del AVL no es el registro activo")
        if tuple(node.getKey()) != tuple(record.key()):
            raise ValueError(f"La clave del nodo no coincide con el evento {event_id}")

        priority, magnitude10, _ = node.getKey()
        nodes.append(
            {
                "id": event_id,
                "key": [priority, from_tenths(magnitude10), event_id],
                "height": node.getHeight(),
                "balance_factor": node.balance_factor(),
                "left": (
                    node.getLeft().getEvent().data.event_id
                    if node.getLeft() is not None
                    else None
                ),
                "right": (
                    node.getRight().getEvent().data.event_id
                    if node.getRight() is not None
                    else None
                ),
            }
        )
        seen_event_ids.add(event_id)
        if node.getRight() is not None:
            stack.append(node.getRight())
        if node.getLeft() is not None:
            stack.append(node.getLeft())

    active_ids = {
        event_id
        for event_id, record in registry.records.items()
        if record.state == ACTIVE
    }
    if seen_event_ids != active_ids:
        raise ValueError("Los nodos del AVL no coinciden con los eventos activos")

    return {
        "root": (
            tree.root.getEvent().data.event_id if tree.root is not None else None
        ),
        "nodes": nodes,
    }


def _association_references(state: ScenarioState) -> Dict[int, int]:
    associations = state.associations
    registry = state.registry
    if not isinstance(associations, AssociationService):
        raise TypeError("Scenario associations must be an AssociationService")
    if associations.registry is not registry:
        raise ValueError("AssociationService must use the scenario event registry")
    if associations.w10 != state.w10 or associations.r10 != state.r10:
        raise ValueError("AssociationService W/R do not match scenario parameters")

    references = associations.references
    for event_id, reference_id in references.items():
        if not _is_int(event_id) or not _is_int(reference_id):
            raise ValueError("Association IDs must be integers")
        if registry.get(event_id) is None or registry.get(reference_id) is None:
            raise ValueError("Association references an unknown event")

    expected = AssociationService(registry, state.w10, state.r10)
    for record in registry.records.values():
        expected.recompute(record)
    if references != expected.references:
        raise ValueError("AssociationService references are stale or invalid")
    return dict(references)


def scenario_to_dict(state: ScenarioState) -> Dict[str, Any]:
    """Convert a ScenarioState into JSON-compatible data (schema version 2).

    The result shares nothing with the state, so it is also used as an
    independent snapshot for the undo stack.
    """
    if not isinstance(state, ScenarioState):
        raise TypeError("state must be a ScenarioState")
    state._validate_parameters()
    structure_issues = state.tree.audit_structure()
    if structure_issues:
        raise ValueError(
            "No se puede guardar un AVL inconsistente: " + "; ".join(structure_issues)
        )
    associations = _association_references(state)

    records = list(state.registry.records.items())
    for event_id, record in records:
        if event_id != record.data.event_id:
            raise ValueError("Registry key does not match its event ID")

    active_ids = [event_id for event_id, record in records if record.state == ACTIVE]
    order = [event_id for event_id in state.insertion_order if event_id in active_ids]
    for event_id in active_ids:          # defensive: every active id appears once
        if event_id not in order:
            order.append(event_id)

    document = {
        "schema_version": SCHEMA_VERSION,
        "mode": state.mode,
        "clock": format_utc(state.clock_epoch),
        "parameters": dict(state.parameters),
        "stations": list(state.stations),
        "metrics": {
            "scenario": dict(state.metrics),
            "avl": state.rotation_counters(),
        },
        "zones": [_zone_to_dict(zone) for zone in state.zones.zones],
        "events": [_record_to_dict(record) for _, record in records],
        "tree": _tree_to_dict(state.tree, state.registry),
        "insertion_order": order,
        "associations": {str(key): value for key, value in sorted(associations.items())},
        "pending_reports": [
            _report_to_dict(report) for report in state.pending_reports.to_list()
        ],
    }
    try:
        json.dumps(document, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Scenario contains values that cannot be represented in JSON") from error
    return document


def save_scenario(state: ScenarioState) -> Dict[str, Any]:
    """Build and return a JSON-compatible representation of a scenario."""
    return scenario_to_dict(state)


def export_to_file(filepath: str | os.PathLike[str], scenario: Any) -> None:
    """Write a ScenarioState or its serialized dictionary to a JSON file."""
    if isinstance(scenario, ScenarioState):
        document = scenario_to_dict(scenario)
    elif isinstance(scenario, dict):
        document = scenario
        try:
            json.dumps(document, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("scenario_dict must contain only JSON values") from error
    else:
        raise TypeError("scenario must be a ScenarioState or a dictionary")

    destination = Path(filepath)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=destination.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_raw(filepath: str | os.PathLike[str]) -> Dict[str, Any]:
    """Read a JSON scenario file."""
    try:
        with open(filepath, "r", encoding="utf-8") as stream:
            document = json.load(stream)
    except json.JSONDecodeError as error:
        raise ScenarioLoadError([f"El archivo no es JSON válido: {error}"])
    return _require_dict(document, "El archivo")


# ---------------------------------------------------------------- version 1

def _upgrade_v1(document: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a schema version 1 document (epoch seconds, tenths) to version 2."""

    def tenths_to_number(value):
        if not _is_int(value):
            raise ValueError("Los valores numéricos de la versión 1 deben ser enteros")
        return from_tenths(value)

    def data_v1(raw, label):
        raw = _require_dict(raw, label)
        time_epoch = raw.get("time_epoch")
        if not _is_int(time_epoch) or time_epoch < 0:
            raise ValueError(f"{label}.time_epoch debe ser un entero no negativo")
        return {
            "id": raw.get("event_id"),
            "magnitude": tenths_to_number(raw.get("magnitude10")),
            "depth": tenths_to_number(raw.get("depth10")),
            "x": tenths_to_number(raw.get("x10")),
            "y": tenths_to_number(raw.get("y10")),
            "time": format_utc(time_epoch),
        }

    clock_epoch = document.get("clock_epoch")
    if not _is_int(clock_epoch) or clock_epoch < 0:
        raise ValueError("clock_epoch debe ser un entero no negativo")

    upgraded = dict(document)
    upgraded["schema_version"] = SCHEMA_VERSION
    upgraded["clock"] = format_utc(clock_epoch)
    upgraded.pop("clock_epoch", None)

    events = []
    for index, raw in enumerate(_list(document.get("events"), "events")):
        raw = _require_dict(raw, f"events[{index}]")
        event = data_v1(raw.get("data"), f"events[{index}].data")
        for name in ("revision", "priority", "stations", "attention", "state"):
            event[name] = raw.get(name)
        events.append(event)
    upgraded["events"] = events

    reports = []
    for index, raw in enumerate(_list(document.get("pending_reports", []), "pending_reports")):
        raw = _require_dict(raw, f"pending_reports[{index}]")
        report = data_v1(raw.get("data"), f"pending_reports[{index}].data")
        report["revision"] = raw.get("revision")
        report["station"] = raw.get("station")
        reports.append(report)
    upgraded["pending_reports"] = reports

    zones = []
    for index, raw in enumerate(_list(document.get("zones", []), "zones")):
        raw = dict(_require_dict(raw, f"zones[{index}]"))
        for name in ("x1", "y1", "x2", "y2"):
            raw[name] = tenths_to_number(raw.get(name))
        zones.append(raw)
    upgraded["zones"] = zones

    tree = _require_dict(document.get("tree", {}), "tree")
    nodes = []
    for index, raw in enumerate(_list(tree.get("nodes", []), "tree.nodes")):
        raw = dict(_require_dict(raw, f"tree.nodes[{index}]"))
        raw["id"] = raw.pop("event_id", None)
        key = raw.get("key")
        if isinstance(key, list) and len(key) == 3:
            raw["key"] = [key[0], tenths_to_number(key[1]), key[2]]
        nodes.append(raw)
    upgraded["tree"] = {"root": tree.get("root"), "nodes": nodes}
    return upgraded


def _list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} debe ser una lista")
    return value


def _normalize(document: Any) -> Dict[str, Any]:
    document = _require_dict(document, "El archivo")
    version = document.get("schema_version")
    if version == 1:
        return _upgrade_v1(document)
    if version != SCHEMA_VERSION:
        raise ValueError(f"Versión de esquema no soportada: {version!r}")
    return document


# ---------------------------------------------------------------- full loaders

def _load_parameters(document: Dict[str, Any]) -> Dict[str, Any]:
    parameters = _require_dict(document.get("parameters"), "parameters")
    required = {"W", "R", "L"}
    if not required.issubset(parameters):
        raise ValueError("parameters debe incluir W, R y L")
    parameters = dict(parameters)
    parameters.setdefault("T", 72)      # old files do not have T
    return parameters


def _load_stations(document: Dict[str, Any]) -> List[str]:
    raw = document.get("stations")
    if raw is None:
        # Old files: default catalog plus every station already used in the file
        stations = list(DEFAULT_STATIONS)
        used = []
        for event in document.get("events", []):
            if isinstance(event, dict) and isinstance(event.get("stations"), list):
                used += event["stations"]
        for report in document.get("pending_reports", []):
            if isinstance(report, dict):
                used.append(report.get("station"))
        for station in used:
            if isinstance(station, str) and station and station not in stations:
                stations.append(station)
        return stations
    if not isinstance(raw, list):
        raise ValueError("stations debe ser una lista")
    return list(raw)


def _load_metrics(document: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int]]:
    raw = _require_dict(document.get("metrics", {}), "metrics")
    scenario_metrics = _require_dict(raw.get("scenario", {}), "metrics.scenario")
    avl_metrics = _require_dict(raw.get("avl", {}), "metrics.avl")
    for name, value in scenario_metrics.items():
        if not _is_int(value) or value < 0:
            raise ValueError(f"metrics.scenario.{name} debe ser un entero no negativo")

    counters = {}
    for name in ROTATION_NAMES:
        value = avl_metrics.get(name, 0)
        if not _is_int(value) or value < 0:
            raise ValueError(f"metrics.avl.{name} debe ser un entero no negativo")
        counters[name] = value
    return dict(scenario_metrics), counters


def _load_records(
    document: Dict[str, Any], zones: ZoneMap, clock_epoch: int, stations: List[str]
) -> Tuple[EventRegistry, List[str]]:
    """Read every event. Returns the registry and the list of problems found."""
    registry = EventRegistry()
    problems = []
    for index, raw in enumerate(_list(document.get("events"), "events")):
        try:
            record = _dict_to_record(raw, zones, clock_epoch, stations, f"events[{index}]")
        except ValueError as error:
            problems.append(str(error))
            continue
        event_id = record.data.event_id
        if registry.get(event_id) is not None:
            problems.append(f"El identificador {event_id} está repetido")
            continue
        registry.add(record)
    return registry, problems


def _load_associations(
    document: Dict[str, Any], registry: EventRegistry, w10: int, r10: int
) -> AssociationService:
    raw = _require_dict(document.get("associations", {}), "associations")
    references = {}
    for key, value in raw.items():
        try:
            event_id = int(key)
        except (TypeError, ValueError):
            raise ValueError(f"Identificador de asociación inválido: {key!r}")
        if not _is_int(value):
            raise ValueError(f"Referencia inválida para el evento {event_id}")
        references[event_id] = value

    associations = AssociationService(registry, w10, r10)
    for record in registry.records.values():
        associations.recompute(record)
    if references != associations.references:
        raise ValueError(
            "Las asociaciones guardadas no coinciden con las calculadas con W y R"
        )
    return associations


def _load_pending_reports(document: Dict[str, Any], stations: List[str]) -> Queue:
    queue = Queue()
    for index, raw in enumerate(_list(document.get("pending_reports", []), "pending_reports")):
        queue.enqueue(_dict_to_report(raw, stations, f"pending_reports[{index}]"))
    return queue


def _new_state(document: Dict[str, Any]) -> ScenarioState:
    mode = document.get("mode")
    if not isinstance(mode, str) or mode not in EXECUTION_MODES:
        raise ValueError(f"Modo de ejecución inválido: {mode!r}")

    clock_epoch = parse_utc(document.get("clock"))
    zones = _dict_to_zones(document.get("zones"))
    stations = _load_stations(document)
    parameters = _load_parameters(document)
    scenario_metrics, avl_metrics = _load_metrics(document)

    # A temporary state validates parameters and stations before the events
    check = ScenarioState(parameters=dict(parameters), stations=list(stations))
    registry, problems = _load_records(document, zones, clock_epoch, stations)
    if problems:
        raise ScenarioLoadError(problems)
    queue = _load_pending_reports(document, stations)

    state = ScenarioState(
        stations=stations,
        registry=registry,
        zones=zones,
        pending_reports=queue,
        clock_epoch=clock_epoch,
        parameters=parameters,
        metrics=scenario_metrics,
        associations=_load_associations(document, registry, check.w10, check.r10),
    )
    state.mode = mode
    for name, value in avl_metrics.items():
        setattr(state.tree, name, value)
    return state


def _tree_from_topology(
    raw_tree: Any, registry: EventRegistry, stress_mode: bool
) -> AVLTree:
    """Rebuild the AVL exactly as it was saved. Raises ScenarioLoadError."""
    raw_tree = _require_dict(raw_tree, "tree")
    raw_nodes = _list(raw_tree.get("nodes"), "tree.nodes")
    problems = []

    descriptors = {}
    for index, raw in enumerate(raw_nodes):
        label = f"tree.nodes[{index}]"
        raw = _require_dict(raw, label)
        event_id = raw.get("id")
        if not _is_int(event_id) or event_id in descriptors:
            problems.append(f"{label}: identificador inválido o repetido ({event_id!r})")
            continue
        record = registry.get(event_id)
        if record is None or record.state != ACTIVE:
            problems.append(f"El nodo {event_id} no corresponde a un evento activo")
            continue

        key = raw.get("key")
        try:
            key_ok = (
                isinstance(key, list)
                and len(key) == 3
                and _is_int(key[0])
                and _is_int(key[2])
                and (key[0], _decimal(key[1], "key"), key[2]) == record.key()
            )
        except ValueError:
            key_ok = False
        if not key_ok:
            problems.append(
                f"La clave guardada del nodo {event_id} no coincide con sus datos "
                f"(esperada {key_text(record.key())})"
            )
        height = raw.get("height")
        balance = raw.get("balance_factor")
        if not _is_int(height) or height < 0 or not _is_int(balance):
            problems.append(f"El nodo {event_id} tiene altura o factor de balance inválidos")
            continue
        descriptors[event_id] = raw

    active_ids = {
        event_id
        for event_id, record in registry.records.items()
        if record.state == ACTIVE
    }
    for missing in sorted(active_ids - set(descriptors)):
        if not any(str(missing) in problem for problem in problems):
            problems.append(f"El evento activo {missing} no aparece en el árbol")
    if problems:
        raise ScenarioLoadError(problems)

    root_id = raw_tree.get("root")
    if not descriptors:
        if root_id is not None:
            raise ScenarioLoadError(["Un árbol vacío debe tener raíz null"])
        return AVLTree(stress_mode=stress_mode)
    if not _is_int(root_id) or root_id not in descriptors:
        raise ScenarioLoadError([f"La raíz {root_id!r} no es un nodo del árbol"])

    parent_by_id = {}
    for event_id, raw in descriptors.items():
        for side in ("left", "right"):
            child_id = raw.get(side)
            if child_id is None:
                continue
            if not _is_int(child_id) or child_id not in descriptors:
                problems.append(f"El nodo {event_id} tiene un enlace {side} inválido ({child_id!r})")
            elif child_id in parent_by_id:
                problems.append(f"El nodo {child_id} aparece en más de una posición")
            else:
                parent_by_id[child_id] = event_id
    if root_id in parent_by_id:
        problems.append("La raíz no puede tener padre (hay un ciclo)")
    if problems:
        raise ScenarioLoadError(problems)

    nodes = {
        event_id: Node(registry.get(event_id).key(), registry.get(event_id))
        for event_id in descriptors
    }
    for event_id, raw in descriptors.items():
        if raw.get("left") is not None:
            nodes[event_id].setLeft(nodes[raw["left"]])
        if raw.get("right") is not None:
            nodes[event_id].setRight(nodes[raw["right"]])

    # Walk from the root checking global order, heights and balance factors
    visited: Set[int] = set()
    calculated_heights = {}
    stack = [(root_id, False, None, None)]
    while stack:
        event_id, exiting, lower, upper = stack.pop()
        node = nodes[event_id]
        key = node.getKey()
        if not exiting:
            if event_id in visited:
                raise ScenarioLoadError(["La topología contiene un ciclo"])
            visited.add(event_id)
            if lower is not None and compare_keys(key, lower) <= 0:
                problems.append(f"Orden incorrecto: el nodo {event_id} {key_text(key)} debe ser mayor que {key_text(lower)}")
            if upper is not None and compare_keys(key, upper) >= 0:
                problems.append(f"Orden incorrecto: el nodo {event_id} {key_text(key)} debe ser menor que {key_text(upper)}")
            stack.append((event_id, True, lower, upper))
            right_id = descriptors[event_id].get("right")
            left_id = descriptors[event_id].get("left")
            if right_id is not None:
                stack.append((right_id, False, key, upper))
            if left_id is not None:
                stack.append((left_id, False, lower, key))
            continue

        left_height = calculated_heights.get(descriptors[event_id].get("left"), -1)
        right_height = calculated_heights.get(descriptors[event_id].get("right"), -1)
        calculated_height = 1 + max(left_height, right_height)
        calculated_balance = left_height - right_height
        raw = descriptors[event_id]
        if raw["height"] != calculated_height:
            problems.append(
                f"Altura guardada incorrecta en {event_id}: {raw['height']} (calculada {calculated_height})"
            )
        if raw["balance_factor"] != calculated_balance:
            problems.append(
                f"Factor de balance incorrecto en {event_id}: {raw['balance_factor']} "
                f"(calculado {calculated_balance})"
            )
        if not stress_mode and abs(calculated_balance) > 1:
            problems.append(
                f"El nodo {event_id} está desbalanceado ({calculated_balance}): "
                "esta topología solo se puede cargar en modo estrés"
            )
        node.setHeight(calculated_height)
        calculated_heights[event_id] = calculated_height

    if visited != set(descriptors):
        unreachable = sorted(set(descriptors) - visited)
        problems.append(f"Nodos no alcanzables desde la raíz: {unreachable}")
    if problems:
        raise ScenarioLoadError(problems)

    tree = AVLTree(stress_mode=stress_mode)
    tree.root = nodes[root_id]
    tree._size = len(nodes)
    return tree


def _load_insertion_order(document: Dict[str, Any], state: ScenarioState) -> List[int]:
    active_ids = [
        event_id for event_id, record in state.registry.records.items() if record.state == ACTIVE
    ]
    raw = document.get("insertion_order")
    if raw is None:
        return [node.getEvent().data.event_id for node in state.tree.level_order()]
    if (
        not isinstance(raw, list)
        or any(not _is_int(value) for value in raw)
        or len(raw) != len(set(raw))
        or set(raw) != set(active_ids)
    ):
        raise ValueError("insertion_order debe listar cada evento activo exactamente una vez")
    return list(raw)


def _as_load_error(error: Exception) -> ScenarioLoadError:
    if isinstance(error, ScenarioLoadError):
        return error
    return ScenarioLoadError([str(error)])


def load_by_topology_from_dict(document: Any) -> ScenarioState:
    """Load a complete scenario (already parsed JSON) keeping its exact AVL topology."""
    try:
        document = _normalize(document)
        state = _new_state(document)
        counters = state.rotation_counters()
        state.tree = _tree_from_topology(
            document.get("tree"), state.registry, state.mode == "STRESS"
        )
        for name, value in counters.items():
            setattr(state.tree, name, value)
        state.insertion_order = _load_insertion_order(document, state)
        return state
    except (ValueError, TypeError) as error:
        raise _as_load_error(error)


def load_by_topology(filepath: str | os.PathLike[str]) -> ScenarioState:
    """Load a complete scenario while preserving its exact AVL topology."""
    return load_by_topology_from_dict(load_raw(filepath))


# ---------------------------------------------------------------- insertion loaders

def _is_simple_document(document: Dict[str, Any]) -> bool:
    return "tree" not in document and "schema_version" not in document


def _simple_events_state(document: Dict[str, Any]) -> Tuple[ScenarioState, List[int]]:
    """Validate a simple {"events": [...]} file. Returns a state with an empty
    tree plus the event ids in file order."""
    problems = []
    zones = default_zones()
    if "zones" in document:
        zones = _dict_to_zones(document.get("zones"))
    stations = _load_stations(document) if "stations" in document else list(DEFAULT_STATIONS)
    parameters = dict(_require_dict(document.get("parameters", {}), "parameters"))
    for name, value in {"W": 48, "R": 40, "L": 3, "T": 72}.items():
        parameters.setdefault(name, value)
    check = ScenarioState(parameters=dict(parameters), stations=list(stations))

    raw_events = _list(document.get("events"), "events")
    if not raw_events:
        problems.append("El archivo no contiene eventos")

    registry = EventRegistry()
    order = []
    for index, raw in enumerate(raw_events):
        label = f"events[{index}]"
        try:
            data = _dict_to_data(raw, label)
            revision = raw.get("revision", 1)
            station = raw.get("station", stations[0])
            if not _is_int(revision) or revision < 1:
                raise ValueError(f"{label}.revision debe ser un entero positivo")
            if station not in stations:
                raise ValueError(f"{label}: la estación {station!r} no existe")
        except ValueError as error:
            problems.append(str(error))
            continue
        if registry.get(data.event_id) is not None:
            problems.append(
                f"El identificador {data.event_id} está repetido (events[{index}]); "
                "las revisiones de un mismo evento se procesan con la cola"
            )
            continue
        record = EventRecord(data, revision, calculate_priority(data, zones), station)
        registry.add(record)
        order.append(data.event_id)

    latest = max((r.data.time_epoch for r in registry.records.values()), default=0)
    clock_epoch = latest
    if "clock" in document:
        try:
            clock_epoch = parse_utc(document.get("clock"))
        except ValueError as error:
            problems.append(str(error))
        if clock_epoch < latest:
            problems.append("Hay eventos posteriores al reloj del archivo")
    if problems:
        raise ScenarioLoadError(problems)

    state = ScenarioState(
        stations=stations,
        registry=registry,
        zones=zones,
        clock_epoch=clock_epoch,
        parameters=parameters,
        associations=AssociationService(registry, check.w10, check.r10),
    )
    for record in registry.records.values():
        state.associations.recompute(record)
    return state, order


def load_by_insertions_from_dict(document: Any) -> Tuple[ScenarioState, BSTTree]:
    """Build a new AVL (balancing on) and a comparison BST with the SAME comparator
    and the SAME insertion order.

    Two formats are accepted:
    - simple file {"events": [...]} (optional zones, stations, parameters, clock);
    - complete scenario file: its active events are reinserted in insertion_order.
    """
    try:
        document = _require_dict(document, "El archivo")
        if _is_simple_document(document):
            state, order = _simple_events_state(document)
        else:
            document = _normalize(document)
            state = _new_state(document)
            state.tree = AVLTree()
            order = _load_insertion_order(document, state)
    except (ValueError, TypeError) as error:
        raise _as_load_error(error)

    # Insertion loading always uses the normal (balanced) mode
    state.tree = AVLTree(stress_mode=False)
    state.insertion_order = []
    bst = BSTTree()
    for event_id in order:
        record = state.registry.get(event_id)
        state.add_to_tree(record)
        bst.insert(record.key(), record)
    return state, bst


def load_by_insertions(
    filepath: str | os.PathLike[str],
) -> Tuple[ScenarioState, BSTTree]:
    """Build a new AVL and comparison BST from the stored insertion sequence."""
    return load_by_insertions_from_dict(load_raw(filepath))


def build_bst(state: ScenarioState) -> BSTTree:
    """Comparison BST of the active events, inserted in the AVL insertion order."""
    bst = BSTTree()
    for event_id in state.insertion_order:
        record = state.registry.get(event_id)
        if record is not None and record.state == ACTIVE:
            bst.insert(record.key(), record)
    return bst
