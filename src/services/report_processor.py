from ..models.event_record import EventRecord, PENDING, ACTIVE, ARCHIVED, DELETED
from ..services.priority import calculate_priority
from .tree_info import key_text

# Possible results of processing a report
CREATED = "CREATED"
UPDATED = "UPDATED"
REACTIVATED = "REACTIVATED"
CONFIRMED = "CONFIRMED"
CONFLICT = "CONFLICT"
OLD = "OLD"
REJECTED = "REJECTED"
INVALID = "INVALID"

# Results that change the event catalog
ACCEPTED_RESULTS = (CREATED, UPDATED, REACTIVATED, CONFIRMED)


class ReportProcessor:
    """Apply the rules of section 6 to one report at a time.

    It reads everything from the ScenarioState, so a clock advance or a
    reloaded tree is seen immediately (nothing is copied at construction time).
    """

    def __init__(self, state):
        self.state = state

    # The scenario parts are read every time, never cached
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
    def clock(self):
        return self.state.clock_epoch

    @property
    def associations(self):
        return self.state.associations

    def process(self, report):
        # Resolve one report completely. Returns (result, message)
        if not self.state.has_station(report.station):
            self.state.add_metric("discarded")
            return (INVALID, "La estación " + report.station + " no existe en el escenario")

        event_id = report.data.event_id
        record = self.registry.get(event_id)

        # Case 1: Unknown id -> create
        if record is None:
            return self._create(report)

        # A deleted id is never reactivated by a report
        if record.state == DELETED:
            self.state.add_metric("discarded")
            return (REJECTED, "El evento fue eliminado; solo se recupera deshaciendo la eliminación")

        # Case 2 to 5: Compare revisions
        if report.revision > record.revision:
            return self._update(record, report)

        if report.revision == record.revision:
            if report.data == record.data:
                return self._confirm(record, report)
            self.state.add_metric("conflicts")
            return (CONFLICT, "Misma revisión con datos distintos: conflicto, reporte rechazado")

        self.state.add_metric("discarded")
        return (OLD, "Revisión " + str(report.revision) + " menor que la vigente ("
                + str(record.revision) + "): reporte antiguo descartado")

    def _create(self, report):
        if report.data.time_epoch > self.clock:
            self.state.add_metric("discarded")
            return (INVALID, "La hora de ocurrencia es posterior al reloj de simulación")

        priority = calculate_priority(report.data, self.zone_map)
        record = EventRecord(report.data, report.revision, priority, report.station)

        # Insert in the tree first: if it fails, the registry is still untouched
        self.state.add_to_tree(record)
        self.registry.add(record)
        self._refresh_associations(report.data.event_id)
        return (CREATED, "Evento nuevo creado con revisión " + str(report.revision)
                + " y clave " + key_text(record.key()))

    def _confirm(self, record, report):
        added = record.add_station(report.station)
        if added:
            return (CONFIRMED, "Confirmación: se añadió la estación " + report.station)
        return (CONFIRMED, "Confirmación repetida de " + report.station + "; no cambia nada")

    def _update(self, record, report):
        if report.data.time_epoch > self.clock:
            self.state.add_metric("discarded")
            return (INVALID, "La hora de ocurrencia es posterior al reloj de simulación")

        was_active = (record.state == ACTIVE)

        # 1. Compute the OLD and the NEW key BEFORE changing anything
        old_key = record.key()
        new_priority = calculate_priority(report.data, self.zone_map)
        new_key = (new_priority, report.data.magnitude10, report.data.event_id)
        key_changes = was_active and (new_key != old_key)

        # 2. Remove from the tree while the record still has its OLD data
        if key_changes:
            self.state.remove_from_tree(record)

        # 3. Replace the data. The station list restarts with the new revision
        record.data = report.data
        record.revision = report.revision
        record.priority = new_priority
        record.stations = [report.station]
        record.attention = PENDING

        # 4. Put it back in the tree
        if key_changes:
            self.state.add_to_tree(record)
            result = UPDATED
            message = ("Corrección aceptada: la clave cambió de " + key_text(old_key) + " a "
                       + key_text(new_key) + " y el evento se reubicó en el árbol")
        elif was_active:
            result = UPDATED
            message = "Corrección aceptada: la clave " + key_text(new_key) + " no cambió; el nodo se queda en su lugar"
        else:
            # Only ARCHIVED events reach this point (DELETED was rejected before)
            record.state = ACTIVE
            self.state.add_to_tree(record)
            result = REACTIVATED
            message = "Evento archivado reactivado como pendiente con clave " + key_text(new_key)

        self.state.add_metric("corrections")
        self._refresh_associations(report.data.event_id)
        return (result, message)

    def _refresh_associations(self, event_id):
        if self.associations is not None:
            self.associations.on_event_changed(event_id)
