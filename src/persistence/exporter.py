"""JSON serialization and reconstruction for SismoLab scenarios."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models import (
    ACTIVE,
    EventData,
    EventRecord,
    EventRegistry,
    Report,
    ScenarioState,
    Zone,
    ZoneMap,
)
from ..services.association_service import AssociationService
from ..services.priority import calculate_priority
from ..structures import AVLTree, BSTTree, KeyType, Node, Queue


SCHEMA_VERSION = 1

# Allowed execution modes for the scenario.
EXECUTION_MODES = {"NORMAL", "STRESS"}

# Possible attention states for events.
ATTENTION_STATES = {"PENDING", "REVIEWED"}

# Possible lifecycle states for events.
LIFECYCLE_STATES = {"ACTIVE", "ARCHIVED", "DELETED"}

# Default monitoring stations.
DEFAULT_STATIONS = ["STA-01", "STA-02", "STA-03"]


def _is_int(value: Any) -> bool:
    """Check whether a value is a valid integer and not a boolean."""
    return isinstance(value, int) and not isinstance(value, bool)


def _require_dict(value: Any, label: str) -> Dict[str, Any]:
    """Ensure that the given value is a dictionary."""
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _data_to_dict(data: EventData) -> Dict[str, int]:
    """Convert event data into a JSON-compatible dictionary."""
    return {
        "event_id": data.event_id,
        "magnitude10": data.magnitude10,
        "depth10": data.depth10,
        "x10": data.x10,
        "y10": data.y10,
        "time_epoch": data.time_epoch,
    }


def _dict_to_data(raw: Any, label: str) -> EventData:
    """Convert a dictionary into an EventData object after validation."""
    raw = _require_dict(raw, label)

    fields = (
        "event_id",
        "magnitude10",
        "depth10",
        "x10",
        "y10",
        "time_epoch",
    )

    values = [raw.get(field) for field in fields]

    # All event data fields must be integers.
    if any(not _is_int(value) for value in values):
        raise ValueError(f"{label} fields must be integers")

    return EventData(*values)


def _record_to_dict(record: EventRecord) -> Dict[str, Any]:
    """Convert an event record into a JSON-compatible dictionary."""
    return {
        "data": _data_to_dict(record.data),
        "revision": record.revision,
        "priority": record.priority,
        "stations": list(record.stations),
        "attention": record.attention,
        "state": record.state,
    }


def _dict_to_record(
    raw: Any, zones: ZoneMap, clock_epoch: int, label: str
) -> EventRecord:
    """Validate event data and create an EventRecord object."""
    raw = _require_dict(raw, label)

    data = _dict_to_data(raw.get("data"), f"{label}.data")

    # Events cannot occur after the scenario clock.
    if data.time_epoch > clock_epoch:
        raise ValueError(f"{label} occurs after the scenario clock")

    revision = raw.get("revision")

    if not _is_int(revision) or revision < 1:
        raise ValueError(f"{label}.revision must be a positive integer")

    stations = raw.get("stations")

    # Stations must be unique and contain valid names.
    if (
        not isinstance(stations, list)
        or not stations
        or any(
            not isinstance(station, str) or not station
            for station in stations
        )
        or len(stations) != len(set(stations))
    ):
        raise ValueError(
            f"{label}.stations must be unique non-empty strings"
        )

    attention = raw.get("attention")
    state = raw.get("state")

    # Validate event status values.
    if not isinstance(attention, str) or attention not in ATTENTION_STATES:
        raise ValueError(f"{label}.attention is invalid")

    if not isinstance(state, str) or state not in LIFECYCLE_STATES:
        raise ValueError(f"{label}.state is invalid")

    # Recalculate priority to verify the stored value.
    expected_priority = calculate_priority(data, zones)

    if raw.get("priority") != expected_priority:
        raise ValueError(f"{label}.priority does not match its event data")

    record = EventRecord(
        data,
        revision,
        expected_priority,
        stations[0]
    )

    record.stations = list(stations)
    record.attention = attention
    record.state = state

    return record


def _zone_to_dict(zone: Zone) -> Dict[str, Any]:
    """Convert a geographic zone into a JSON-compatible dictionary."""
    return {
        "zone_id": zone.zone_id,
        "populated": zone.populated,
        "x1": zone.x1,
        "y1": zone.y1,
        "x2": zone.x2,
        "y2": zone.y2,
    }


def _dict_to_zones(raw_zones: Any) -> ZoneMap:
    """Validate zone data and create a ZoneMap."""
    if not isinstance(raw_zones, list):
        raise ValueError("zones must be a list")

    zones = []
    seen_ids = set()

    for index, raw in enumerate(raw_zones):
        label = f"zones[{index}]"
        raw = _require_dict(raw, label)

        zone_id = raw.get("zone_id")
        populated = raw.get("populated")

        bounds = [
            raw.get(name)
            for name in ("x1", "y1", "x2", "y2")
        ]

        # Zone IDs must be unique and non-empty.
        if (
            not isinstance(zone_id, str)
            or not zone_id
            or zone_id in seen_ids
        ):
            raise ValueError(
                f"{label}.zone_id must be unique and non-empty"
            )

        if not isinstance(populated, bool):
            raise ValueError(f"{label}.populated must be a boolean")

        # Coordinates must be integers inside the allowed range.
        if any(
            not _is_int(value) or not 0 <= value <= 10000
            for value in bounds
        ):
            raise ValueError(
                f"{label} bounds must be integers in [0, 10000]"
            )

        x1, y1, x2, y2 = bounds

        # Validate the zone rectangle.
        if x1 > x2 or y1 > y2:
            raise ValueError(f"{label} has reversed bounds")

        seen_ids.add(zone_id)
        zones.append(
            Zone(
                zone_id,
                populated,
                x1,
                y1,
                x2,
                y2
            )
        )

    return ZoneMap(zones)


def _report_to_dict(report: Report) -> Dict[str, Any]:
    """Convert a report into a JSON-compatible dictionary."""
    return {
        "data": _data_to_dict(report.data),
        "revision": report.revision,
        "station": report.station,
    }


def _dict_to_report(
    raw: Any,
    clock_epoch: int,
    label: str
) -> Report:
    """Validate report data and create a Report object."""
    raw = _require_dict(raw, label)

    data = _dict_to_data(
        raw.get("data"),
        f"{label}.data"
    )

    # Reports cannot belong to the future.
    if data.time_epoch > clock_epoch:
        raise ValueError(
            f"{label} occurs after the scenario clock"
        )

    revision = raw.get("revision")
    station = raw.get("station")

    if not _is_int(revision) or revision < 1:
        raise ValueError(
            f"{label}.revision must be a positive integer"
        )

    if not isinstance(station, str) or not station:
        raise ValueError(
            f"{label}.station must be a non-empty string"
        )

    return Report(data, revision, station)


def _tree_to_dict(
    tree: AVLTree,
    registry: EventRegistry
) -> Dict[str, Any]:
    """Serialize the AVL tree while preserving its exact topology."""

    nodes = []
    seen_node_ids = set()
    seen_event_ids = set()

    # Start traversal from the AVL root.
    stack = [tree.root] if tree.root is not None else []

    while stack:
        node = stack.pop()

        node_identity = id(node)

        # Detect repeated references or cycles.
        if node_identity in seen_node_ids:
            raise ValueError(
                "AVL contains a cycle or a repeated node reference"
            )

        seen_node_ids.add(node_identity)

        record = node.getEvent()
        event_id = record.data.event_id

        # Every event must appear only once.
        if event_id in seen_event_ids:
            raise ValueError(
                f"AVL contains duplicate event ID {event_id}"
            )

        # The node must correspond to the active registry record.
        if (
            registry.get(event_id) is not record
            or record.state != ACTIVE
        ):
            raise ValueError(
                f"AVL event {event_id} is not the active registry record"
            )

        # Verify that the node key matches the event key.
        if tuple(node.getKey()) != tuple(record.key()):
            raise ValueError(
                f"AVL key does not match event {event_id}"
            )

        nodes.append(
            {
                "event_id": event_id,
                "key": list(node.getKey()),
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

    # Compare tree events with active registry events.
    active_ids = {
        event_id
        for event_id, record in registry.records.items()
        if record.state == ACTIVE
    }

    if seen_event_ids != active_ids:
        raise ValueError(
            "AVL nodes and active registry records do not match"
        )

    return {
        "root": (
            tree.root.getEvent().data.event_id
            if tree.root is not None
            else None
        ),
        "nodes": nodes,
    }


def _association_references(
    associations: Any,
    registry: EventRegistry,
    parameters: Dict[str, Any]
) -> Dict[int, int]:
    """Validate and return event association references."""
    if not isinstance(
        associations,
        AssociationService
    ):
        raise TypeError(
            "Scenario associations must be an AssociationService"
        )

    if associations.registry is not registry:
        raise ValueError(
            "AssociationService must use the scenario event registry"
        )

    # Validate association distance parameters.
    if associations.w10 != parameters["W"] * 10:
        raise ValueError(
            "AssociationService W does not match scenario parameters"
        )

    if associations.r10 != parameters["R"] * 10:
        raise ValueError(
            "AssociationService R does not match scenario parameters"
        )

    references = associations.references

    if not isinstance(references, dict):
        raise ValueError(
            "AssociationService references must be a dictionary"
        )

    # Check that all association IDs are valid.
    for event_id, reference_id in references.items():
        if not _is_int(event_id) or not _is_int(reference_id):
            raise ValueError(
                "Association IDs must be integers"
            )

        if (
            registry.get(event_id) is None
            or registry.get(reference_id) is None
        ):
            raise ValueError(
                "Association references an unknown event"
            )

    # Recalculate associations to detect stale data.
    expected = AssociationService(
        registry,
        parameters["W"] * 10,
        parameters["R"] * 10
    )

    for record in registry.records.values():
        expected.recompute(record)

    if references != expected.references:
        raise ValueError(
            "AssociationService references are stale or invalid"
        )

    return dict(references)


def scenario_to_dict(
    state: ScenarioState
) -> Dict[str, Any]:
    """Convert a ScenarioState into JSON-compatible data."""

    if not isinstance(state, ScenarioState):
        raise TypeError(
            "state must be a ScenarioState"
        )

    state._validate_parameters()

    if state.mode not in EXECUTION_MODES:
        raise ValueError(
            f"Invalid execution mode: {state.mode}"
        )

    # Validate the AVL structure before saving.
    structure_issues = state.tree.audit_structure()

    if structure_issues:
        raise ValueError(
            "Cannot save an inconsistent AVL: "
            + "; ".join(structure_issues)
        )

    associations = _association_references(
        state.associations,
        state.registry,
        state.parameters
    )

    records = list(
        state.registry.records.items()
    )

    # Verify registry consistency.
    for event_id, record in records:
        if event_id != record.data.event_id:
            raise ValueError(
                "Registry key does not match its event ID"
            )

    if len(state.registry.records) != len(records):
        raise ValueError(
            "Registry contains duplicate event IDs"
        )

    pending_reports = state.pending_reports.to_list()

    # Store scenario and AVL statistics.
    metrics = {
        "scenario": dict(state.metrics),
        "avl": {
            "count_ll": state.tree.count_ll,
            "count_rr": state.tree.count_rr,
            "count_lr": state.tree.count_lr,
            "count_rl": state.tree.count_rl,
            "count_left_rotations": (
                state.tree.count_left_rotations
            ),
            "count_right_rotations": (
                state.tree.count_right_rotations
            ),
        },
    }

    document = {
        "schema_version": SCHEMA_VERSION,
        "mode": state.mode,
        "clock_epoch": state.clock_epoch,
        "parameters": dict(state.parameters),
        "stations": list(state.stations),
        "metrics": metrics,
        "associations": associations,
        "zones": [
            _zone_to_dict(zone)
            for zone in state.zones.zones
        ],
        "events": [
            _record_to_dict(record)
            for _, record in records
        ],
        "tree": _tree_to_dict(
            state.tree,
            state.registry
        ),
        "insertion_order": [
            event_id
            for event_id, record in records
            if record.state == ACTIVE
        ],
        "pending_reports": [
            _report_to_dict(report)
            for report in pending_reports
        ],
    }

    # Make sure the document can be represented as JSON.
    try:
        json.dumps(
            document,
            allow_nan=False
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Scenario contains values that cannot be represented in JSON"
        ) from error

    return document


def save_scenario(
    state: ScenarioState
) -> Dict[str, Any]:
    """Create a JSON-compatible representation of a scenario."""
    return scenario_to_dict(state)


def export_to_file(
    filepath: str | os.PathLike[str],
    scenario: Any
) -> None:
    """Save a scenario dictionary or ScenarioState to a JSON file."""

    if isinstance(scenario, ScenarioState):
        document = scenario_to_dict(scenario)

    elif isinstance(scenario, dict):
        document = scenario

        try:
            json.dumps(
                document,
                allow_nan=False
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "scenario_dict must contain only JSON values"
            ) from error

    else:
        raise TypeError(
            "scenario must be a ScenarioState or a dictionary"
        )

    destination = Path(filepath)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_path = None

    try:
        # Write to a temporary file before replacing the destination.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=destination.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:

            temporary_path = Path(stream.name)

            json.dump(
                document,
                stream,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            stream.write("\n")

        # Replace the old file safely.
        os.replace(
            temporary_path,
            destination
        )

    finally:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()


def load_raw(
    filepath: str | os.PathLike[str]
) -> Dict[str, Any]:
    """Read a JSON scenario file and return its raw data."""

    with open(
        filepath,
        "r",
        encoding="utf-8"
    ) as stream:
        document = json.load(stream)

    return _require_dict(
        document,
        "scenario"
    )


def _load_records(
    document: Dict[str, Any],
    zones: ZoneMap
) -> EventRegistry:
    """Load and validate event records into the registry."""

    clock_epoch = document.get("clock_epoch")

    if not _is_int(clock_epoch) or clock_epoch < 0:
        raise ValueError(
            "clock_epoch must be a non-negative integer"
        )

    raw_events = document.get("events")

    if not isinstance(raw_events, list):
        raise ValueError(
            "events must be a list"
        )

    registry = EventRegistry()

    for index, raw in enumerate(raw_events):
        record = _dict_to_record(
            raw,
            zones,
            clock_epoch,
            f"events[{index}]"
        )

        event_id = record.data.event_id

        if registry.get(event_id) is not None:
            raise ValueError(
                f"Duplicate event ID {event_id}"
            )

        registry.add(record)

    return registry


def _load_parameters(
    document: Dict[str, Any]
) -> Dict[str, Any]:
    """Load and validate the scenario parameters."""

    parameters = _require_dict(
        document.get("parameters"),
        "parameters"
    )

    required = {"W", "R", "L"}

    if not required.issubset(parameters):
        raise ValueError(
            "parameters must include W, R, and L"
        )

    result = dict(parameters)

    # Use 72 as the default T parameter.
    result.setdefault("T", 72)

    return result


def _load_metrics(
    document: Dict[str, Any]
) -> Tuple[
    Dict[str, int],
    Dict[str, int]
]:
    """Load and validate scenario and AVL metrics."""

    raw = _require_dict(
        document.get("metrics"),
        "metrics"
    )

    scenario_metrics = raw.get(
        "scenario",
        {}
    )

    avl_metrics = raw.get(
        "avl",
        {}
    )

    scenario_metrics = _require_dict(
        scenario_metrics,
        "metrics.scenario"
    )

    avl_metrics = _require_dict(
        avl_metrics,
        "metrics.avl"
    )

    # Scenario metrics must be non-negative integers.
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in scenario_metrics.values()
    ):
        raise ValueError(
            "Scenario metric values must be non-negative integers"
        )

    names = (
        "count_ll",
        "count_rr",
        "count_lr",
        "count_rl",
        "count_left_rotations",
        "count_right_rotations",
    )

    counters = {}

    for name in names:
        value = avl_metrics.get(
            name,
            0
        )

        if not _is_int(value) or value < 0:
            raise ValueError(
                f"metrics.avl.{name} must be a non-negative integer"
            )

        counters[name] = value

        if (
            name in scenario_metrics
            and scenario_metrics[name] != value
        ):
            raise ValueError(
                f"metrics.{name} counters do not match "
                f"the AVL counters"
            )

        scenario_metrics[name] = value

    return (
        dict(scenario_metrics),
        counters
    )


def _load_associations(
    document: Dict[str, Any],
    registry: EventRegistry,
    parameters: Dict[str, Any]
) -> AssociationService:
    """Load and validate event associations."""

    raw = _require_dict(
        document.get("associations", {}),
        "associations"
    )

    references = {}

    for key, value in raw.items():

        try:
            event_id = int(key)

        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid association event ID: {key!r}"
            ) from error

        if event_id in references:
            raise ValueError(
                f"Duplicate association event ID: {event_id}"
            )

        if not _is_int(value):
            raise ValueError(
                f"Invalid reference event ID for {event_id}"
            )

        references[event_id] = value

    associations = AssociationService(
        registry,
        parameters["W"] * 10,
        parameters["R"] * 10
    )

    # Recalculate the expected associations.
    for record in registry.records.values():
        associations.recompute(record)

    if references != associations.references:
        raise ValueError(
            "Saved associations do not match the event data"
        )

    return associations


def _load_pending_reports(
    document: Dict[str, Any],
    clock_epoch: int,
    stations=None
) -> Queue:
    """Load pending reports into a FIFO queue."""

    raw_reports = document.get(
        "pending_reports"
    )

    if not isinstance(raw_reports, list):
        raise ValueError(
            "pending_reports must be a list"
        )

    queue = Queue()

    for index, raw in enumerate(raw_reports):
        report = _dict_to_report(
            raw,
            clock_epoch,
            f"pending_reports[{index}]"
        )

        if (
            stations is not None
            and report.station not in stations
        ):
            raise ValueError(
                f"pending_reports[{index}].station is unknown"
            )

        # Add the report to the FIFO queue.
        queue.enqueue(report)

    return queue


def _new_state(
    document: Dict[str, Any]
) -> ScenarioState:
    """Create a ScenarioState from validated scenario data."""

    # Validate the file schema version.
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            "Unsupported schema version: "
            f"{document.get('schema_version')!r}"
        )

    mode = document.get("mode")

    if (
        not isinstance(mode, str)
        or mode not in EXECUTION_MODES
    ):
        raise ValueError(
            f"Invalid execution mode: {mode!r}"
        )

    clock_epoch = document.get(
        "clock_epoch"
    )

    if not _is_int(clock_epoch) or clock_epoch < 0:
        raise ValueError(
            "clock_epoch must be a non-negative integer"
        )

    zones = _dict_to_zones(
        document.get("zones")
    )

    registry = _load_records(
        document,
        zones
    )

    parameters = _load_parameters(
        document
    )

    stations = document.get(
        "stations",
        DEFAULT_STATIONS
    )

    if (
        not isinstance(stations, list)
        or not stations
        or any(
            not isinstance(name, str)
            or not name
            for name in stations
        )
        or len(stations) != len(set(stations))
    ):
        raise ValueError(
            "stations must be unique non-empty names"
        )

    scenario_metrics, avl_metrics = _load_metrics(
        document
    )

    queue = _load_pending_reports(
        document,
        clock_epoch,
        stations
    )

    # Create the complete scenario state.
    state = ScenarioState(
        registry=registry,
        zones=zones,
        pending_reports=queue,
        clock_epoch=clock_epoch,
        parameters=parameters,
        metrics=scenario_metrics,
        stations=list(stations),
        associations=_load_associations(
            document,
            registry,
            parameters
        ),
    )

    state.mode = mode

    # Restore AVL counters.
    for name, value in avl_metrics.items():
        setattr(
            state.tree,
            name,
            value
        )

    return state


def _tree_from_topology(
    raw_tree: Any,
    registry: EventRegistry,
    stress_mode: bool
) -> AVLTree:
    """Rebuild an AVL tree using the stored tree topology."""

    raw_tree = _require_dict(
        raw_tree,
        "tree"
    )

    raw_nodes = raw_tree.get(
        "nodes"
    )

    if not isinstance(raw_nodes, list):
        raise ValueError(
            "tree.nodes must be a list"
        )

    descriptors = {}

    # Read and validate every stored node.
    for index, raw in enumerate(raw_nodes):

        label = f"tree.nodes[{index}]"

        raw = _require_dict(
            raw,
            label
        )

        event_id = raw.get(
            "event_id"
        )

        if (
            not _is_int(event_id)
            or event_id in descriptors
        ):
            raise ValueError(
                f"{label}.event_id is invalid or duplicated"
            )

        record = registry.get(
            event_id
        )

        if (
            record is None
            or record.state != ACTIVE
        ):
            raise ValueError(
                f"{label} does not reference an active event"
            )

        key = raw.get("key")

        if (
            not isinstance(key, list)
            or len(key) != 3
            or any(
                not _is_int(value)
                for value in key
            )
            or tuple(key) != record.key()
        ):
            raise ValueError(
                f"{label}.key does not match the registered event"
            )

        height = raw.get(
            "height"
        )

        balance = raw.get(
            "balance_factor"
        )

        if (
            not _is_int(height)
            or height < 0
            or not _is_int(balance)
        ):
            raise ValueError(
                f"{label} has invalid height or balance metadata"
            )

        descriptors[event_id] = raw

    # The tree must contain all active events.
    active_ids = {
        event_id
        for event_id, record in registry.records.items()
        if record.state == ACTIVE
    }

    if set(descriptors) != active_ids:
        raise ValueError(
            "Tree must contain every active event exactly once"
        )

    root_id = raw_tree.get(
        "root"
    )

    if not descriptors:
        if root_id is not None:
            raise ValueError(
                "An empty tree must have a null root"
            )

        return AVLTree(
            stress_mode=stress_mode
        )

    if (
        not _is_int(root_id)
        or root_id not in descriptors
    ):
        raise ValueError(
            "tree.root must identify an existing node"
        )

    parent_by_id = {}

    # Validate parent-child relationships.
    for event_id, raw in descriptors.items():

        for side in ("left", "right"):

            child_id = raw.get(side)

            if child_id is None:
                continue

            if (
                not _is_int(child_id)
                or child_id not in descriptors
            ):
                raise ValueError(
                    f"Tree node {event_id} has an invalid "
                    f"{side} reference"
                )

            if child_id in parent_by_id:
                raise ValueError(
                    f"Tree node {child_id} has multiple parents"
                )

            parent_by_id[child_id] = event_id

    if root_id in parent_by_id:
        raise ValueError(
            "Tree root cannot have a parent"
        )

    if set(parent_by_id) != (
        set(descriptors) - {root_id}
    ):
        raise ValueError(
            "Every non-root node must have exactly one parent"
        )

    # Create the AVL nodes.
    nodes = {
        event_id: Node(
            registry.get(event_id).key(),
            registry.get(event_id)
        )
        for event_id in descriptors
    }

    # Connect the nodes using the saved topology.
    for event_id, raw in descriptors.items():

        node = nodes[event_id]

        left_id = raw.get("left")
        right_id = raw.get("right")

        if left_id is not None:
            node.setLeft(
                nodes[left_id]
            )

        if right_id is not None:
            node.setRight(
                nodes[right_id]
            )

    root = nodes[root_id]

    visited: Set[int] = set()
    calculated_heights = {}

    # Stack is used to validate the tree iteratively.
    stack = [
        (root_id, False, None, None)
    ]

    while stack:

        event_id, exiting, lower, upper = stack.pop()

        node = nodes[event_id]
        key = node.getKey()

        if not exiting:

            # Detect cycles or repeated nodes.
            if event_id in visited:
                raise ValueError(
                    "Tree topology contains a cycle or repeated node"
                )

            visited.add(event_id)

            # Validate BST ordering.
            if (
                lower is not None
                and key <= lower
            ):
                raise ValueError(
                    f"BST ordering violation at event {event_id}"
                )

            if (
                upper is not None
                and key >= upper
            ):
                raise ValueError(
                    f"BST ordering violation at event {event_id}"
                )

            stack.append(
                (
                    event_id,
                    True,
                    lower,
                    upper
                )
            )

            right_id = descriptors[event_id].get(
                "right"
            )

            left_id = descriptors[event_id].get(
                "left"
            )

            if right_id is not None:
                stack.append(
                    (
                        right_id,
                        False,
                        key,
                        upper
                    )
                )

            if left_id is not None:
                stack.append(
                    (
                        left_id,
                        False,
                        lower,
                        key
                    )
                )

            continue

        left_id = descriptors[event_id].get(
            "left"
        )

        right_id = descriptors[event_id].get(
            "right"
        )

        left_height = calculated_heights.get(
            left_id,
            -1
        )

        right_height = calculated_heights.get(
            right_id,
            -1
        )

        calculated_height = (
            1 + max(
                left_height,
                right_height
            )
        )

        calculated_balance = (
            left_height - right_height
        )

        raw = descriptors[event_id]

        # Verify stored AVL metadata.
        if raw["height"] != calculated_height:
            raise ValueError(
                f"Stored height is incorrect at event {event_id}"
            )

        if raw["balance_factor"] != calculated_balance:
            raise ValueError(
                f"Stored balance factor is incorrect at event {event_id}"
            )

        # Normal mode requires a balanced AVL tree.
        if (
            not stress_mode
            and abs(calculated_balance) > 1
        ):
            raise ValueError(
                f"Unbalanced topology at event {event_id} "
                "requires STRESS mode"
            )

        node.setHeight(
            calculated_height
        )

        calculated_heights[event_id] = (
            calculated_height
        )

    if visited != set(descriptors):
        raise ValueError(
            "Tree contains nodes unreachable from its root"
        )

    tree = AVLTree(
        stress_mode=stress_mode
    )

    tree.root = root
    tree._size = len(nodes)

    return tree


def load_by_topology(
    filepath: str | os.PathLike[str]
) -> ScenarioState:
    """Load a scenario while preserving its exact AVL topology."""
    return scenario_from_dict(
        load_raw(filepath)
    )


def scenario_from_dict(
    document: Dict[str, Any]
) -> ScenarioState:
    """Validate and restore a complete scenario from JSON data."""

    document = _require_dict(
        document,
        "scenario"
    )

    state = _new_state(
        document
    )

    # Restore the exact AVL structure from the saved topology.
    state.tree = _tree_from_topology(
        document.get("tree"),
        state.registry,
        state.mode == "STRESS"
    )

    state.tree.bind_metrics(
        state.metrics
    )

    scenario_metrics, avl_metrics = _load_metrics(
        document
    )

    state.metrics.update(
        scenario_metrics
    )

    for name, value in avl_metrics.items():
        setattr(
            state.tree,
            name,
            value
        )

    return state


def load_by_insertions(
    filepath: str | os.PathLike[str],
) -> Tuple[ScenarioState, BSTTree]:
    """Load a scenario and rebuild AVL and BST using insertion order."""

    return load_by_insertions_from_dict(
        load_raw(filepath)
    )


def load_by_insertions_from_dict(
    document: Dict[str, Any],
) -> Tuple[ScenarioState, BSTTree]:
    """Rebuild AVL and BST trees from the stored insertion sequence."""

    document = _require_dict(
        document,
        "scenario"
    )

    state = _new_state(
        document
    )

    raw_order = document.get(
        "insertion_order"
    )

    if (
        not isinstance(raw_order, list)
        or any(
            not _is_int(value)
            for value in raw_order
        )
    ):
        raise ValueError(
            "insertion_order must be a list of event IDs"
        )

    # Get all active event IDs.
    active_ids = {
        event_id
        for event_id, record in state.registry.records.items()
        if record.state == ACTIVE
    }

    if (
        len(raw_order) != len(set(raw_order))
        or set(raw_order) != active_ids
    ):
        raise ValueError(
            "insertion_order must list every active event exactly once"
        )

    # Reset AVL rotation counters before rebuilding.
    for name in (
        "count_ll",
        "count_rr",
        "count_lr",
        "count_rl",
        "count_left_rotations",
        "count_right_rotations"
    ):
        state.metrics[name] = 0

    tree = AVLTree(
        stress_mode=False
    )

    tree.bind_metrics(
        state.metrics
    )

    bst = BSTTree()

    # Insert every event into both trees.
    for event_id in raw_order:

        record = state.registry.get(
            event_id
        )

        tree.insert(
            record.key(),
            record
        )

        bst.insert(
            record.key(),
            record
        )

    state.tree = tree

    return state, bst