"""Section 14: "Verify structure". One entry per inconsistent event.

Checks the GLOBAL order by K (each node is compared with the bounds inherited
from all its ancestors, not only with its parent), unique keys and ids,
links (no cycles, no repeated nodes), stored keys against the event data,
recalculated heights, balance factors and the association references.
In stress mode an unbalanced node is reported as EXPECTED, not as an error.
"""

from ..models.event_record import ACTIVE, DELETED
from ..structures.comparator import compare_keys
from .tree_info import key_text, sis

ORDER = "orden"
DUPLICATE = "duplicado"
LINK = "enlace"
KEY = "clave"
HEIGHT = "altura"
BALANCE = "balance"
EXPECTED = "desbalance esperado"
REFERENCE = "referencia"


class AuditService:

    def __init__(self, state):
        self.state = state

    def audit(self):
        issues = []
        tree = self.state.tree
        stress = tree.stress_mode

        def add(event_id, kind, detail, expected=False):
            issues.append({
                "event_id": event_id,
                "label": sis(event_id) if event_id is not None else "árbol",
                "type": kind,
                "detail": detail,
                "expected": expected,
            })

        seen_nodes = set()
        seen_ids = set()
        seen_keys = set()
        heights = {}
        # (node, lower bound, upper bound, exiting?)
        stack = [(tree.root, None, None, False)] if tree.root is not None else []
        while stack:
            node, lower, upper, exiting = stack.pop()
            record = node.getEvent()
            event_id = record.data.event_id
            key = node.getKey()

            if exiting:
                left, right = node.getLeft(), node.getRight()
                left_h = heights.get(id(left), -1) if left is not None else -1
                right_h = heights.get(id(right), -1) if right is not None else -1
                real_height = 1 + max(left_h, right_h)
                heights[id(node)] = real_height
                if node.getHeight() != real_height:
                    add(event_id, HEIGHT, "altura guardada " + str(node.getHeight())
                        + ", recalculada " + str(real_height))
                balance = left_h - right_h
                if abs(balance) > 1:
                    if stress:
                        add(event_id, EXPECTED, "factor de balance " + str(balance)
                            + " (permitido en modo estrés)", expected=True)
                    else:
                        add(event_id, BALANCE, "factor de balance " + str(balance)
                            + " fuera de {-1, 0, 1}")
                continue

            if id(node) in seen_nodes:
                add(event_id, LINK, "el nodo aparece dos veces (ciclo o enlace repetido)")
                continue
            seen_nodes.add(id(node))

            if event_id in seen_ids:
                add(event_id, DUPLICATE, "el identificador aparece en más de un nodo")
            seen_ids.add(event_id)
            if key in seen_keys:
                add(event_id, DUPLICATE, "la clave " + key_text(key) + " está repetida")
            seen_keys.add(key)

            if tuple(key) != tuple(record.key()):
                add(event_id, KEY, "la clave del nodo " + key_text(key)
                    + " no coincide con sus datos " + key_text(record.key()))
            if record.state != ACTIVE or self.state.registry.get(event_id) is not record:
                add(event_id, LINK, "el nodo no apunta al registro activo del evento")
            if lower is not None and compare_keys(key, lower) <= 0:
                add(event_id, ORDER, "su clave " + key_text(key)
                    + " debería ser mayor que " + key_text(lower))
            if upper is not None and compare_keys(key, upper) >= 0:
                add(event_id, ORDER, "su clave " + key_text(key)
                    + " debería ser menor que " + key_text(upper))

            stack.append((node, lower, upper, True))
            if node.getRight() is not None:
                stack.append((node.getRight(), key, upper, False))
            if node.getLeft() is not None:
                stack.append((node.getLeft(), lower, key, False))

        # Every active event must be in the tree exactly once
        for event_id, record in self.state.registry.records.items():
            if record.state == ACTIVE and event_id not in seen_ids:
                add(event_id, LINK, "evento activo que no está en el AVL")
        if len(seen_nodes) != tree.size:
            add(None, LINK, "tamaño guardado " + str(tree.size) + ", nodos alcanzables "
                + str(len(seen_nodes)))

        self._audit_references(add)

        errors = [issue for issue in issues if not issue["expected"]]
        expected = [issue for issue in issues if issue["expected"]]
        return {
            "ok": len(errors) == 0,
            "balanced": not any(issue["type"] in (BALANCE, EXPECTED) for issue in issues),
            "mode": self.state.mode,
            "checked_nodes": len(seen_nodes),
            "errors": errors,
            "expected": expected,
        }

    def _audit_references(self, add):
        service = self.state.associations
        registry = self.state.registry
        for event_id, reference_id in service.references.items():
            reference = registry.get(reference_id)
            if reference is None or reference.state == DELETED:
                add(event_id, REFERENCE, "su referencia " + str(reference_id) + " no es válida")
                continue
            # Follow the chain: a reference must never come back to the start
            seen = {event_id}
            current = reference_id
            while current is not None:
                if current in seen:
                    add(event_id, REFERENCE, "las referencias forman un ciclo")
                    break
                seen.add(current)
                current = service.references.get(current)
        for record in registry.records.values():
            if record.state == DELETED:
                continue
            candidates = service.candidates_of(record)
            expected = service.choose(candidates, record).data.event_id if candidates else None
            if service.reference_of(record.data.event_id) != expected:
                add(record.data.event_id, REFERENCE,
                    "la referencia guardada no coincide con la política (esperada "
                    + str(expected) + ")")
