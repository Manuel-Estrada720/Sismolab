"""Section 10: "Archive branch of old events"."""

from ..models.event_record import ARCHIVED
from .priority import LOW
from .tree_info import node_positions, sis


class ArchiveService:

    def __init__(self, state):
        self.state = state

    def is_old_enough(self, record):
        """Age strictly greater than T hours (compared in exact integers)."""
        age_seconds = self.state.clock_epoch - record.data.time_epoch
        # age_seconds / 3600 > t10 / 10   <=>   age_seconds * 10 > t10 * 3600
        return age_seconds * 10 > self.state.t10 * 3600

    def is_eligible_event(self, record):
        return record.priority == LOW and self.is_old_enough(record)

    def _reason(self, record):
        """Why one event blocks a branch (empty text if it does not block)."""
        if record.priority != LOW:
            return sis(record.data.event_id) + " (prioridad " + str(record.priority) + ")"
        if not self.is_old_enough(record):
            return sis(record.data.event_id) + " (antigüedad no mayor que T)"
        return ""

    def evaluate(self):
        """Evaluate every subtree of the active AVL.

        Returns (eligible, blocked):
        - eligible: list of {root, size, depth, ids} for every eligible subtree;
        - blocked: low-priority roots whose branch is not eligible, with the reason.
        """
        tree = self.state.tree
        positions = node_positions(tree)
        info = {}            # event_id -> (eligible, size, ids, blocking_reason)
        eligible = []
        blocked = []

        # Postorder: both children are evaluated before their parent
        for node in tree.postorder():
            record = node.getEvent()
            event_id = record.data.event_id
            size = 1
            ids = [event_id]
            # "blocker" describes one event that makes this branch not eligible
            blocker = self._reason(record)
            for child in (node.getLeft(), node.getRight()):
                if child is None:
                    continue
                child_ok, child_size, child_ids, child_blocker = info[child.getEvent().data.event_id]
                size += child_size
                ids += child_ids
                if not child_ok and not blocker:
                    blocker = child_blocker
            ok = blocker == ""
            info[event_id] = (ok, size, ids, blocker)
            if ok:
                eligible.append(
                    {"root": event_id, "size": size, "depth": positions[event_id][2], "ids": sorted(ids)}
                )
            elif record.priority == LOW and self.is_old_enough(record):
                blocked.append({"root": event_id, "reason": "no es elegible: su rama contiene a " + blocker})
        return eligible, blocked

    def select(self):
        """Choose the branch to archive. Returns a preview dictionary or None.

        Rule: most nodes; tie -> deepest root; tie -> highest root id.
        """
        eligible, blocked = self.evaluate()
        if not eligible:
            return None

        def rank(branch):
            return (branch["size"], branch["depth"], branch["root"])

        best = eligible[0]
        for branch in eligible:
            if rank(branch) > rank(best):
                best = branch

        same_size = [b for b in eligible if b["size"] == best["size"]]
        same_depth = [b for b in same_size if b["depth"] == best["depth"]]
        lines = [
            "Se evaluaron " + str(len(eligible)) + " subárboles elegibles "
            "(todos sus eventos con prioridad baja y antigüedad mayor que T = "
            + str(self.state.parameters["T"]) + " h).",
            "Se elige la rama con raíz " + sis(best["root"]) + " porque tiene "
            + str(best["size"]) + " nodo(s), la mayor cantidad.",
        ]
        if len(same_size) > 1:
            lines.append(
                "Empate en tamaño con " + str(len(same_size) - 1) + " rama(s): se prefiere "
                "la raíz más profunda (profundidad " + str(best["depth"]) + ")."
            )
        if len(same_depth) > 1:
            lines.append(
                "Persiste el empate en profundidad: se prefiere el mayor identificador de raíz ("
                + sis(best["root"]) + ")."
            )
        if self.state.tree.root is not None and best["root"] == self.state.tree.root.getEvent().data.event_id:
            lines.append("Todo el árbol es elegible: se archiva completo.")

        others = sorted(eligible, key=rank, reverse=True)[1:6]
        return {
            "root": best["root"],
            "ids": best["ids"],
            "count": best["size"],
            "depth": best["depth"],
            "justification": lines,
            "other_candidates": [
                {"root": b["root"], "size": b["size"], "depth": b["depth"]} for b in others
            ],
            "blocked": blocked[:10],
        }

    def apply(self, ids):
        """Archive a FIXED set of ids. The set is chosen before touching the tree,
        so rotations made while deleting cannot add or remove events."""
        fixed_ids = list(ids)
        for event_id in fixed_ids:
            record = self.state.registry.get(event_id)
            self.state.remove_from_tree(record)     # normal AVL delete (or stress delete)
            record.state = ARCHIVED                 # data and associations are kept
        self.state.add_metric("archive_operations")
        self.state.add_metric("archived_events", len(fixed_ids))
        return fixed_ids
