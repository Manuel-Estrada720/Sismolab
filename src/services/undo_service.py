"""Section 13: undo stack.

Before every action that changes the scenario, the complete scenario is
serialized with scenario_to_dict. That dictionary shares nothing with the
live objects, so later changes can never alter an older snapshot.
Memory: O(n) per stored action (n = events + queued reports).
"""

from ..structures.Stack import Stack


class UndoService:

    def __init__(self, limit=200):
        self.stack = Stack()
        self.limit = limit          # oldest snapshots are dropped after this

    def push(self, label, snapshot):
        self.stack.push({"label": label, "snapshot": snapshot})
        if self.stack.size() > self.limit:
            # Drop the oldest entry (bottom of the stack) to bound memory
            self.stack.items.pop(0)

    def pop(self):
        """Return the last {"label", "snapshot"} or None if there is nothing to undo."""
        return self.stack.pop()

    def can_undo(self):
        return not self.stack.is_empty()

    def size(self):
        return self.stack.size()

    def labels(self):
        """Labels from the most recent to the oldest."""
        return [entry["label"] for entry in reversed(self.stack.items)]

    def clear(self):
        self.stack.clear()
