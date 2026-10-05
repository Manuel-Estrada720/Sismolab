"""In-memory state for one SismoLab simulation scenario."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Any, Dict

from ..structures.Avl import AVLTree
from ..structures.Queue import Queue
from .event_registry import EventRegistry
from .zone import ZoneMap

if TYPE_CHECKING:
    from ..services.association_service import AssociationService


def _default_parameters() -> Dict[str, Any]:
    return {"W": 48, "R": 40, "L": 3}


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

    def __post_init__(self) -> None:
        if isinstance(self.clock_epoch, bool) or not isinstance(self.clock_epoch, int):
            raise TypeError("clock_epoch must be an integer number of UTC seconds")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be a dictionary")
        if not isinstance(self.metrics, dict):
            raise TypeError("metrics must be a dictionary")
        self._validate_parameters()
        from ..services.association_service import AssociationService

        if self.associations is not None and not isinstance(
            self.associations, (dict, AssociationService)
        ):
            raise TypeError("associations must be an AssociationService or mapping")

        if isinstance(self.associations, dict):
            references = dict(self.associations)
            self.associations = AssociationService(
                self.registry,
                self.parameters["W"] * 10,
                self.parameters["R"] * 10,
            )
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
            self.associations = AssociationService(
                self.registry,
                self.parameters["W"] * 10,
                self.parameters["R"] * 10,
            )
            for record in self.registry.records.values():
                self.associations.recompute(record)
        elif self.associations.registry is not self.registry:
            raise ValueError("AssociationService must use the scenario event registry")
        elif self.associations.w10 != self.parameters["W"] * 10:
            raise ValueError("AssociationService W must match scenario parameters")
        elif self.associations.r10 != self.parameters["R"] * 10:
            raise ValueError("AssociationService R must match scenario parameters")

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
        for name in ("W", "R"):
            value = self.parameters.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"Parameter {name} must be a positive finite number")

        limit = self.parameters.get("L")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("Parameter L must be a non-negative integer")
