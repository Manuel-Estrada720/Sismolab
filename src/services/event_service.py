from ..models.event_record import REVIEWED, ACTIVE, DELETED
from ..models.report import Report
from .report_processor import ReportProcessor, CREATED, UPDATED


class EventService:
    """Manual operations of section 6. The Observatory facade calls this class."""

    def __init__(self, state, processor=None):
        self.state = state
        self.processor = processor if processor is not None else ReportProcessor(state)

    @property
    def registry(self):
        return self.state.registry

    @property
    def tree(self):
        return self.state.tree

    @property
    def zone_map(self):
        return self.state.zones

    @property
    def associations(self):
        return self.state.associations

    def create_event(self, data, station):
        """Manual creation. `data` is an EventData (already validated)."""
        if self.registry.get(data.event_id) is not None:
            return (False, "El identificador ya pertenece a un evento activo, archivado o eliminado")
        result, message = self.processor.process(Report(data, 1, station))
        return (result == CREATED, message)

    def correct_event(self, event_id, new_data, station):
        record = self.registry.get(event_id)
        if record is None:
            return (False, "El evento no existe")
        if record.state != ACTIVE:
            return (False, "Solo se pueden corregir eventos activos")
        if new_data.event_id != event_id:
            return (False, "El identificador es inmutable")
        # A correction is a report with revision r + 1 (even if the key stays the same)
        report = Report(new_data, record.revision + 1, station)
        result, message = self.processor.process(report)
        return (result == UPDATED, message)

    def mark_reviewed(self, event_id):
        record = self.registry.get(event_id)
        if record is None:
            return (False, "El evento no existe")
        if record.state != ACTIVE:
            return (False, "Solo los eventos activos se pueden marcar como revisados")
        if record.attention == REVIEWED:
            return (False, "El evento ya está revisado")
        record.attention = REVIEWED     # P, M and I do not change: the tree is untouched
        return (True, "Evento marcado como revisado; su clave no cambia")

    def delete_event(self, event_id):
        record = self.registry.get(event_id)
        if record is None:
            return (False, "El evento no existe")
        if record.state != ACTIVE:
            return (False, "Solo se pueden eliminar eventos activos")
        self.state.remove_from_tree(record)       # while the record still has its key
        record.state = DELETED                    # it STAYS in the registry
        self.associations.on_event_deleted(event_id)
        return (True, "Evento eliminado; sus descendientes siguen activos")

    def get_event_info(self, event_id):
        """What section 6 asks to show. Returns None if the id is unknown."""
        record = self.registry.get(event_id)
        if record is None:
            return None
        info = {"id": event_id, "state": record.state}
        info["data"] = record.data
        info["revision"] = record.revision
        info["stations"] = list(record.stations)
        info["populated"] = self.zone_map.is_populated(record.data.x10, record.data.y10)
        info["priority"] = record.priority
        info["key"] = record.key()
        info["attention"] = record.attention
        info["reference"] = self.associations.reference_of(event_id)
        info["used_by"] = self.associations.used_by(event_id)
        if record.state == ACTIVE:
            node, visited = self.tree.search(record.key())
            info["node_depth"] = visited - 1          # root has depth 0
            info["visited"] = visited
            info["node_height"] = node.getHeight()
            info["balance_factor"] = node.balance_factor()
        return info
