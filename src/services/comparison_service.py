"""Section 11 (end): compare the AVL with a plain BST on the same events.

Both trees use the same comparator. For every insertion order the same keys
are inserted, then every key is searched once and the comparisons are added.
"""

import random

from ..models.event_record import ACTIVE
from ..structures.Avl import AVLTree
from ..structures.Bst import BSTTree

ORDER_NAMES = {
    "original": "Orden original (inserción en el catálogo)",
    "ascending": "Claves ascendentes",
    "descending": "Claves descendentes",
    "random": "Aleatorio con semilla fija",
}


class ComparisonService:

    def __init__(self, state, seed=2026):
        self.state = state
        self.seed = seed

    def _orders(self):
        records = []
        for event_id in self.state.insertion_order:
            record = self.state.registry.get(event_id)
            if record is not None and record.state == ACTIVE:
                records.append(record)
        # Ascending order comes from the AVL inorder (no sort of a parallel list)
        ascending = [node.getEvent() for node in self.state.tree.inorder()]
        shuffled = list(records)
        random.Random(self.seed).shuffle(shuffled)
        return {
            "original": records,
            "ascending": ascending,
            "descending": list(reversed(ascending)),
            "random": shuffled,
        }

    @staticmethod
    def _measure(tree, records, height, leaves):
        total = 0
        worst = 0
        for record in records:
            _, visited = tree.search(record.key())
            total += visited
            worst = max(worst, visited)
        count = len(records)
        return {
            "height": height,
            "leaves": leaves,
            "total_comparisons": total,
            "average_comparisons": round(total / count, 2) if count else 0,
            "max_comparisons": worst,
        }

    def compare(self):
        rows = []
        for name, records in self._orders().items():
            avl = AVLTree()
            bst = BSTTree()
            for record in records:
                avl.insert(record.key(), record)
                bst.insert(record.key(), record)
            rows.append({
                "order": name,
                "title": ORDER_NAMES[name],
                "size": len(records),
                "avl": self._measure(avl, records, avl.height, avl.count_leaves()),
                "bst": self._measure(bst, records, bst.height(), bst.count_leaves()),
            })
        return {"seed": self.seed, "rows": rows}
