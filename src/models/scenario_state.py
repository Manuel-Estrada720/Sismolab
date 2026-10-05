"""In-memory state for one SismoLab simulation scenario."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

from ..structures.Avl import AVLTree
from ..structures.Queue import Queue
from .event_registry import EventRegistry
from .units import to_tenths
from .zone import ZoneMap

if TYPE_CHECKING:
    from ..services.association_service import AssociationService


# Stations used when a scenario (or an old file) does not define its own
DEFAULT_STATIONS = ["EST-NORTE", "EST-SUR", "EST-ESTE", "EST-OESTE", "EST-CENTRO"]

# Counters that belong to the scenario. AVL rotation counters live in the tree.
METRIC_NAMES = (
    "corrections",          # accepted corrections (including reactivations)
    "discarded",            # old, rejected or invalid reports
    "conflicts",            # same revision with different data
    "archive_operations",   # times the "archive branch" action ran
    "archived_events",      # events moved to the archive by that action
)

ROTATION_NAMES = (
    "count_ll",
    "count_rr",
    "count_lr",
    "count_rl",
    "count_left_rotations",
    "count_right_rotations",
)


def _default_parameters() -> Dict[str, Any]:
    return {"W": 48, "R": 40, "L": 3, "T": 72}


def _default_stations() -> List[str]:
    return list(DEFAULT_STATIONS)


def _positive_tenths(value: Any, name: str) -> int:
    """Return a positive parameter as tenths, or raise ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"El parámetro {name} debe ser un número positivo")
    try:
        tenths = to_tenths(value)
    except ValueError:
        raise ValueError(f"El parámetro {name} debe ser finito y tener máximo un decimal")
    if tenths <= 0:
        raise ValueError(f"El parámetro {name} debe ser positivo")
    return tenths


@dataclass
class ScenarioState:
    """Collect the mutable components that must be saved and restored together."""

    tree: AVLTree = field(default_factory=AVLTree)
    registry: EventRegistry = field(default_factory=EventRegistry)
    zones: ZoneMap = field(default_factory=lambda: ZoneMap([]))
    pending_reports: Queue = field(default_factory=Queue)
    clock_epoch: int = 0
    parameters: Dict[str, Any] = field(default_factory=_default_parameters)
    metrics: Dict[str, int] = field(default_factory=dict)
    associations: AssociationService | Dict[int, int] | None = None
    stations: List[str] = field(default_factory=_default_stations)
    # Ids of the active events in the order they entered the AVL.
    # It is used to rebuild the comparison BST with the same insertion order.
    insertion_order: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.clock_epoch, bool) or not isinstance(self.clock_epoch, int):
            raise TypeError("clock_epoch must be an integer number of UTC seconds")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be a dictionary")
        if not isinstance(self.metrics, dict):
            raise TypeError("metrics must be a dictionary")
        # Old scenarios do not have T: use the default value
        self.parameters.setdefault("T", 72)
        self._validate_parameters()
        self._validate_stations()
        for name in METRIC_NAMES:
            self.metrics.setdefault(name, 0)

        from ..services.association_service import AssociationService

        if self.associations is not None and not isinstance(
            self.associations, (dict, AssociationService)
        ):
            raise TypeError("associations must be an AssociationService or mapping")

        if isinstance(self.associations, dict):
            references = dict(self.associations)
            self.associations = AssociationService(self.registry, self.w10, self.r10)
            for event_id, reference_id in references.items():
                if (
                    isinstance(event_id, bool)
                    or not isinstance(event_id, int)
                    or isinstance(reference_id, bool)
                    or not isinstance(reference_id, int)
                ):
                    raise TypeError("association references must use integer IDs")
            self.associations.references = references
        elif self.associations is None:
            self.associations = AssociationService(self.registry, self.w10, self.r10)
            for record in self.registry.records.values():
                self.associations.recompute(record)
        elif self.associations.registry is not self.registry:
            raise ValueError("AssociationService must use the scenario event registry")
        elif self.associations.w10 != self.w10:
            raise ValueError("AssociationService W must match scenario parameters")
        elif self.associations.r10 != self.r10:
            raise ValueError("AssociationService R must match scenario parameters")

    # ---------- parameters in tenths ----------

    @property
    def w10(self) -> int:
        """W in tenths of an hour (48 h -> 480)."""
        return to_tenths(self.parameters["W"])

    @property
    def r10(self) -> int:
        """R in tenths of km (40 km -> 400)."""
        return to_tenths(self.parameters["R"])

    @property
    def t10(self) -> int:
        """T in tenths of an hour (72 h -> 720)."""
        return to_tenths(self.parameters["T"])

    @property
    def mode(self) -> str:
        """Return the execution mode from the AVL's source-of-truth flag."""
        return "STRESS" if self.tree.stress_mode else "NORMAL"

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in {"NORMAL", "STRESS"}:
            raise ValueError("mode must be 'NORMAL' or 'STRESS'")
        self.tree.stress_mode = value == "STRESS"

    def _validate_parameters(self) -> None:
        for name in ("W", "R", "T"):
            _positive_tenths(self.parameters.get(name), name)

        limit = self.parameters.get("L")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("El parámetro L debe ser un entero no negativo")

    def _validate_stations(self) -> None:
        if not isinstance(self.stations, list) or len(self.stations) == 0:
            raise ValueError("El escenario debe tener al menos una estación")
        for station in self.stations:
            if not isinstance(station, str) or not station.strip():
                raise ValueError("Cada estación debe ser un texto no vacío")
        if len(set(self.stations)) != len(self.stations):
            raise ValueError("Las estaciones no pueden repetirse")

    def has_station(self, station: str) -> bool:
        return station in self.stations

    # ---------- metrics ----------

    def add_metric(self, name: str, amount: int = 1) -> None:
        """Increase one scenario counter. This is the only place they change."""
        self.metrics[name] = self.metrics.get(name, 0) + amount

    def rotation_counters(self) -> Dict[str, int]:
        return {name: getattr(self.tree, name) for name in ROTATION_NAMES}

    def all_metrics(self) -> Dict[str, int]:
        """Scenario counters plus AVL rotation counters, in one dictionary."""
        result = {name: self.metrics.get(name, 0) for name in METRIC_NAMES}
        result.update(self.rotation_counters())
        return result

    # ---------- AVL helpers ----------

    def add_to_tree(self, record) -> None:
        """Insert an active record in the AVL and remember the insertion order."""
        self.tree.insert(record.key(), record)
        event_id = record.data.event_id
        if event_id in self.insertion_order:
            self.insertion_order.remove(event_id)
        self.insertion_order.append(event_id)

    def remove_from_tree(self, record) -> None:
        """Remove a record from the AVL using the key it has right now."""
        removed = self.tree.delete(record.key())
        if removed is None:
            raise ValueError(f"El evento {record.data.event_id} no está en el AVL")
        event_id = record.data.event_id
        if event_id in self.insertion_order:
            self.insertion_order.remove(event_id)
