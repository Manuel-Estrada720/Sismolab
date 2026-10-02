from src.models.event_record import EventRecord, PENDING, REVIEWED, ACTIVE, ARCHIVED, DELETED
from src.services.priority import calculate_priority

# Possible results of processing a report
CREATED = "CREATED"
UPDATED = "UPDATED"
REACTIVATED = "REACTIVATED"
CONFIRMED = "CONFIRMED"
CONFLICT = "CONFLICT"
OLD = "OLD"
REJECTED = "REJECTED"
INVALID = "INVALID"

class ReportProcessor:
    def __init__(self, registry, tree, zone_map, clock):
        self.registry = registry
        self.tree = tree
        self.zone_map = zone_map
        self.clock = clock              # Simulation clock (epoch seconds)
        self.counters = {"corrections": 0, "discarded": 0, "conflicts": 0}

    def process(self, report):
        # Resolve one report completely. Returns (result, message)
        event_id = report.data.event_id
        record = self.registry.get(event_id)
        
        # Case 1: Unknown id -> create
        if record is None:
            return self._create(report)
        
        # A deleted id is never reactivated by a report 
        if record.state == DELETED:
            self.counters["discarded"] += 1
            return (REJECTED, "Event is deleted; undo the deletion first")
        
        # Case 2 to 5: Compare revisions
        if report.revision > record.revision:
            return self._update(record, report)
        
        if report.revision == record.revision:
            if report.data == record.data:
                return self._confirm(record, report)
            self.counters["conflicts"] += 1
            return (CONFLICT, "Same revision but different data; report rejected")
        self.counters["discarded"] += 1
        return (OLD, "Older revision; report discarded")
    
    def _create(self, report):
        if report.data.time_epoch > self.clock:
            return (INVALID, "Occurrence time is after the simulation clock")
        
        priority = calculate_priority(report.data, self.zone_map)
        record = EventRecord(report.data, report.revision, priority, report.station)
        
        self.registry.add(record)
        self.tree.insert(record)
        return (CREATED, "New event created with revision " + str(report.revision))
    
    def _confirm(self, record, report):
        added = record.add_station(report.station)
        if added:
            return (CONFIRMED, "Station " + report.station + " added")
        return (CONFIRMED, "Already confirmed by this station; nothing changes")
    
    def _update(self, record, report):
        if report.data.time_epoch > self.clock:
            return (INVALID, "Occurrence time is after the simulation clock")

        was_active = (record.state == ACTIVE)

        # 1. Compute the OLD and the NEW key BEFORE changing anything
        old_key = record.key()
        new_priority = calculate_priority(report.data, self.zone_map)
        new_key = (new_priority, report.data.magnitude10, report.data.event_id)
        key_changes = was_active and (new_key != old_key)

        # 2. Remove from the tree while the record still has its OLD data
        if key_changes:
            self.tree.delete(old_key)

        # 3. Replace the data
        record.data = report.data
        record.revision = report.revision
        record.priority = new_priority
        record.stations = [report.station]
        record.attention = PENDING

        # 4. Put it back in the tree
        if key_changes:
            self.tree.insert(record)
            result = UPDATED
            message = "Corrected; key changed, event relocated in the tree"
        elif was_active:
            result = UPDATED
            message = "Corrected; key is the same, event stays in place"
        else:
            record.state = ACTIVE
            self.tree.insert(record)
            result = REACTIVATED
            message = "Archived event reactivated as pending"

        self.counters["corrections"] += 1
        return (result, message)