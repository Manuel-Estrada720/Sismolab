"""Section 11: queries over the active AVL. Every query counts the AVL nodes examined.

Which branches can be skipped depends only on K = (P, M, I):
- P comes first, so the tree is ordered by priority, then magnitude, then id.
- A magnitude range is NOT a single key range: equal magnitudes appear once
  per priority. But priority limits the magnitude (P1 -> M < 4.5,
  P2 -> 4.5 <= M < 6.0, P3 -> M >= 4.5), so the range becomes at most three
  key intervals and the search skips every branch outside all of them.
- Depth of the hypocenter and occurrence time are not part of K: that query
  must examine every node.
"""

from ..models.event_record import ACTIVE, ARCHIVED, DELETED, PENDING
from ..models.units import from_tenths
from ..structures.comparator import compare_keys
from .priority import HIGH, LOW, MEDIUM
from .tree_info import is_costly, sis

MIN_ID, MAX_ID = 1, 999999
MIN_M, MAX_M = -20, 100

# Magnitudes (tenths) that each priority can have, from the rules of section 4
PRIORITY_MAGNITUDES = {
    LOW: (MIN_M, 44),
    MEDIUM: (45, 59),
    HIGH: (45, MAX_M),
}


def event_summary(record, depth=None):
    data = record.data
    summary = {
        "id": data.event_id,
        "label": sis(data.event_id),
        "state": record.state,
        "priority": record.priority,
        "magnitude": from_tenths(data.magnitude10),
        "depth": from_tenths(data.depth10),
        "attention": record.attention,
        "key": [record.priority, from_tenths(data.magnitude10), data.event_id],
    }
    if depth is not None:
        summary["node_depth"] = depth
    return summary


class QueryService:

    def __init__(self, state):
        self.state = state

    # ---------- generic pruned search ----------

    def _interval_search(self, intervals, accept):
        """Visit only the branches that may contain a key inside some interval.

        intervals: list of (low_key, high_key), both inclusive.
        accept(record, depth) decides if a node inside an interval is a result.
        Returns (results in ascending key order, examined nodes).
        """
        results = []
        examined = 0

        def inside(key):
            for low, high in intervals:
                if compare_keys(low, key) <= 0 and compare_keys(key, high) <= 0:
                    return True
            return False

        def visit(node, depth):
            nonlocal examined
            if node is None:
                return
            examined += 1
            key = node.getKey()
            # Smaller keys live on the left: go there only if some interval starts before key
            if any(compare_keys(low, key) < 0 for low, _ in intervals):
                visit(node.getLeft(), depth + 1)
            if inside(key) and accept(node.getEvent(), depth):
                results.append(event_summary(node.getEvent(), depth))
            if any(compare_keys(high, key) > 0 for _, high in intervals):
                visit(node.getRight(), depth + 1)

        visit(self.state.tree.root, 0)
        return results, examined

    # ---------- queries ----------

    def pending_top(self, k):
        """First k pending events in DESCENDING order of K (reverse inorder)."""
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ValueError("k debe ser un entero positivo")
        results = []
        examined = 0
        stack = []
        current = self.state.tree.root
        depth = 0
        while (current is not None or stack) and len(results) < k:
            while current is not None:
                examined += 1
                stack.append((current, depth))
                current = current.getRight()
                depth += 1
            node, node_depth = stack.pop()
            record = node.getEvent()
            if record.attention == PENDING:
                results.append(event_summary(record, node_depth))
            current = node.getLeft()
            depth = node_depth + 1
        return {
            "results": results,
            "examined": examined,
            "explanation": (
                "Recorrido inorden inverso (claves descendentes). Se detiene al encontrar "
                + str(k) + " pendientes. El estado de atención no forma parte de K, "
                "por eso no se pueden descartar ramas: solo se corta el recorrido al llegar a k."
            ),
        }

    def magnitude_range(self, low10, high10):
        if low10 > high10:
            raise ValueError("El mínimo de magnitud no puede ser mayor que el máximo")
        intervals = []
        parts = []
        for priority in (LOW, MEDIUM, HIGH):
            p_low, p_high = PRIORITY_MAGNITUDES[priority]
            low = max(low10, p_low)
            high = min(high10, p_high)
            if low <= high:
                intervals.append(((priority, low, MIN_ID), (priority, high, MAX_ID)))
                parts.append("P" + str(priority) + ": M en [" + str(from_tenths(low))
                             + ", " + str(from_tenths(high)) + "]")
        if not intervals:
            results, examined = [], 0
        else:
            results, examined = self._interval_search(intervals, lambda record, depth: True)
        results.reverse()          # show the most important first
        return {
            "results": results,
            "examined": examined,
            "explanation": (
                "K empieza por la prioridad, así que una misma magnitud aparece en varias "
                "zonas del árbol. Como la prioridad limita la magnitud, el rango se convierte "
                "en intervalos de clave (" + "; ".join(parts) + ") y se descartan las ramas "
                "que quedan fuera de todos ellos. En el peor caso se examinan todos los nodos."
            ),
        }

    def depth_and_dates(self, max_depth10, start_epoch, end_epoch):
        if start_epoch > end_epoch:
            raise ValueError("La fecha inicial no puede ser posterior a la final")
        results = []
        examined = 0
        for node in self.state.tree.inorder():
            examined += 1
            data = node.getEvent().data
            if data.depth10 <= max_depth10 and start_epoch <= data.time_epoch <= end_epoch:
                results.append(event_summary(node.getEvent()))
        results.reverse()
        return {
            "results": results,
            "examined": examined,
            "explanation": (
                "La profundidad del hipocentro y la fecha no forman parte de K = (P, M, I), "
                "por eso ninguna rama se puede descartar: se examinan los n nodos (O(n))."
            ),
        }

    def costly_events(self):
        """High priority events whose node depth is greater than L."""
        limit = self.state.parameters["L"]
        interval = [((HIGH, MIN_M, MIN_ID), (HIGH, MAX_M, MAX_ID))]
        results, examined = self._interval_search(
            interval, lambda record, depth: is_costly(record, depth, limit)
        )
        for result in results:
            result["limit"] = limit
            result["search_cost"] = result["node_depth"] + 1
        results.reverse()
        return {
            "results": results,
            "examined": examined,
            "explanation": (
                "Solo la prioridad alta (P = 3) puede ser costosa y sus claves son las mayores, "
                "así que se descartan las ramas izquierdas cuyas claves tienen P < 3. "
                "El costo de búsqueda de cada evento es su profundidad + 1."
            ),
        }

    def find_by_id(self, event_id):
        """Locate an event by id. The registry (hash table) finds the record in O(1)
        and the AVL search by its current key gives the node and the cost."""
        record = self.state.registry.get(event_id)
        if record is None:
            return {"found": False, "examined": 0, "state": None}
        if record.state != ACTIVE:
            return {"found": True, "examined": 0, "state": record.state, "record": record}
        node, visited = self.state.tree.search(record.key())
        return {
            "found": True,
            "examined": visited,
            "state": ACTIVE,
            "record": record,
            "node": node,
            "node_depth": visited - 1,
        }

    def associations_of(self, event_id):
        """Candidates, chosen reference and events that use this one (active or archived)."""
        record = self.state.registry.get(event_id)
        if record is None:
            raise ValueError("El evento " + str(event_id) + " no existe")
        if record.state == DELETED:
            raise ValueError("El evento " + sis(event_id) + " está eliminado: no tiene asociaciones")
        service = self.state.associations
        located = self.find_by_id(event_id)

        candidates = []
        for candidate in service.candidates_of(record):
            dx = (candidate.data.x10 - record.data.x10) / 10
            dy = (candidate.data.y10 - record.data.y10) / 10
            hours = (record.data.time_epoch - candidate.data.time_epoch) / 3600
            item = event_summary(candidate)
            item["distance_km"] = round((dx * dx + dy * dy) ** 0.5, 2)
            item["hours_before"] = round(hours, 2)
            item["rank"] = [-candidate.data.magnitude10, service.distance2(candidate, record), candidate.data.event_id]
            candidates.append(item)
        candidates.sort(key=lambda item: item["rank"])

        reference_id = service.reference_of(event_id)
        reference = None
        if reference_id is not None:
            reference = event_summary(self.state.registry.get(reference_id))
        used_by = [event_summary(self.state.registry.get(i)) for i in service.used_by(event_id)]
        return {
            "event": event_summary(record),
            "candidates": candidates,
            "reference": reference,
            "used_by": used_by,
            "examined": located["examined"],
            "registry_scanned": len(self.state.registry.records),
            "explanation": (
                "Se localiza el evento en el AVL por su clave (nodos examinados). Los candidatos "
                "se buscan en el registro completo (activos y archivados), porque W y R no forman "
                "parte de K. Política: mayor magnitud, luego menor distancia, luego menor ID."
            ),
        }


def describe_state_name(state):
    names = {ACTIVE: "activo", ARCHIVED: "archivado", DELETED: "eliminado"}
    return names.get(state, state)
