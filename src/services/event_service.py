# src/service/event_service.py
from src.models.event_record import REVIEWED, ACTIVE, DELETED
from src.models.report import Report
from src.services.report_processor import CREATED, UPDATED


class EventService:
    """Manual operations of section 6. The GUI calls this class."""

    def __init__(self, registry, tree, zone_map, processor, associations):
        self.registry = registry
        self.tree = tree
        self.zone_map = zone_map
        self.processor = processor
        self.associations = associations

    def create_event(self, data, station):
        """Manual creation. `data` is an EventData (already validated)."""
        if self.registry.get(data.event_id) is not None:
            return (False, "Id already used by an active, archived or deleted event")
        result, message = self.processor.process(Report(data, 1, station))
        return (result == CREATED, message)

    def correct_event(self, event_id, new_data, station):
        record = self.registry.get(event_id)
        if record is None:
            return (False, "Event does not exist")
        if record.state != ACTIVE:
            return (False, "Only active events can be corrected")
        if new_data.event_id != event_id:
            return (False, "The id is immutable")
        # A correction is a report with revision r + 1
        report = Report(new_data, record.revision + 1, station)
        result, message = self.processor.process(report)
        return (result == UPDATED, message)

    def mark_reviewed(self, event_id):
        record = self.registry.get(event_id)
        if record is None:
            return (False, "Event does not exist")
        if record.state != ACTIVE:
            return (False, "Only active events can be marked as reviewed")
        if record.attention == REVIEWED:
            return (False, "Event is already reviewed")
        record.attention = REVIEWED     # P, M and I do not change: the tree is untouched
        return (True, "Event marked as reviewed")

    def delete_event(self, event_id):
        record = self.registry.get(event_id)
        if record is None:
            return (False, "Event does not exist")
        if record.state != ACTIVE:
            return (False, "Only active events can be deleted")
        self.tree.delete(record.key())            # while the record still has its key
        record.state = DELETED                    # it STAYS in the registry
        self.associations.on_event_deleted(event_id)
        return (True, "Event deleted")

    def get_event_info(self, event_id):
        """What section 6 asks to show. Returns None if the id is unknown."""
        record = self.registry.get(event_id)
        if record is None:
            return None
        info = {"id": event_id, "state": record.state}
        if record.state == ACTIVE:
            info["data"] = record.data
            info["revision"] = record.revision
            info["stations"] = list(record.stations)
            info["populated"] = self.zone_map.is_populated(record.data.x10, record.data.y10)
            info["priority"] = record.priority
            info["key"] = record.key()
            info["attention"] = record.attention
            info["reference"] = self.associations.reference_of(event_id)
            info["used_by"] = self.associations.used_by(event_id)
        return info