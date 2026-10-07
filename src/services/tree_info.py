"""Small read-only helpers about where each event sits in a tree."""

from ..models.units import from_tenths
from .priority import HIGH


def node_positions(tree):
    """Return {event_id: (parent_id, side, depth)} for every node.

    The root has parent None, side "root" and depth 0. Works for AVL and BST.
    """
    positions = {}
    if tree.root is None:
        return positions
    stack = [(tree.root, None, "root", 0)]
    while stack:
        node, parent_id, side, depth = stack.pop()
        event_id = node.getEvent().data.event_id
        positions[event_id] = (parent_id, side, depth)
        if node.getLeft() is not None:
            stack.append((node.getLeft(), event_id, "left", depth + 1))
        if node.getRight() is not None:
            stack.append((node.getRight(), event_id, "right", depth + 1))
    return positions


def moved_events(before, after):
    """Ids whose parent, side or depth changed between two position maps."""
    moved = []
    for event_id, position in after.items():
        if event_id in before and before[event_id] != position:
            moved.append(event_id)
    return sorted(moved)


def is_costly(record, depth, limit):
    """Section 9: high priority and node depth strictly greater than L."""
    return record.priority == HIGH and depth > limit


def subtree_heights(tree):
    """Real height of every node, computed again from the links.

    The BST does not keep heights, so its view uses this function.
    Returns {event_id: height}. A leaf has height 0.
    """
    heights = {}
    if tree.root is None:
        return heights
    # Postorder without recursion: children are always processed first
    for node in tree.postorder():
        left = node.getLeft()
        right = node.getRight()
        left_h = heights[left.getEvent().data.event_id] if left is not None else -1
        right_h = heights[right.getEvent().data.event_id] if right is not None else -1
        heights[node.getEvent().data.event_id] = 1 + max(left_h, right_h)
    return heights


def key_text(key):
    """Show a key with a decimal point: (3, 52, 10) -> "(3, 5.2, 10)"."""
    priority, magnitude10, event_id = key
    return "(" + str(priority) + ", " + str(from_tenths(magnitude10) * 1.0) + ", " + str(event_id) + ")"


def sis(event_id):
    """Display format of an id: 10 -> SIS-000010."""
    return "SIS-" + str(event_id).zfill(6)
