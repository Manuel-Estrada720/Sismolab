"""AVL tree implementation for the SismoLab event catalog."""

from collections import deque
from typing import Any, Deque, List, Optional, Set, Tuple

from .Node import Node


KeyType = Tuple[int, float, int]


def _compare_keys(first: KeyType, second: KeyType) -> int:
    """Compare event keys lexicographically without converting their values."""
    if first < second:
        return -1
    if first > second:
        return 1
    return 0


class AVLTree:
    """Binary search tree ordered by the event key (priority, magnitude, ID)."""

    def __init__(self, stress_mode: bool = False):
        self.root: Optional[Node] = None
        self._size = 0
        self.stress_mode = stress_mode

        self.count_ll = 0
        self.count_rr = 0
        self.count_lr = 0
        self.count_rl = 0
        self.count_left_rotations = 0
        self.count_right_rotations = 0

    @property
    def size(self) -> int:
        """Return the number of nodes in the tree."""
        return self._size

    @property
    def height(self) -> int:
        """Return the tree height, using -1 for an empty tree."""
        return self.root.getHeight() if self.root is not None else -1

    def _height(self, node: Optional[Node]) -> int:
        return node.getHeight() if node is not None else -1

    def _balance_factor(self, node: Optional[Node]) -> int:
        if node is None:
            return 0
        return self._height(node.getLeft()) - self._height(node.getRight())

    def _rotate_right(self, node: Node) -> Node:
        """Perform one right rotation and return the new subtree root."""
        new_root = node.getLeft()
        if new_root is None:
            return node

        subtree = new_root.getRight()
        new_root.setRight(node)
        node.setLeft(subtree)

        node.update_height()
        new_root.update_height()
        self.count_right_rotations += 1
        return new_root

    def _rotate_left(self, node: Node) -> Node:
        """Perform one left rotation and return the new subtree root."""
        new_root = node.getRight()
        if new_root is None:
            return node

        subtree = new_root.getLeft()
        new_root.setLeft(node)
        node.setRight(subtree)

        node.update_height()
        new_root.update_height()
        self.count_left_rotations += 1
        return new_root

    def _rebalance_node(self, node: Node) -> Node:
        """Restore AVL balance at a node and update rotation-case counters."""
        balance = self._balance_factor(node)

        if balance > 1:
            left_child = node.getLeft()
            if left_child is not None and self._balance_factor(left_child) >= 0:
                self.count_ll += 1
                return self._rotate_right(node)

            self.count_lr += 1
            if left_child is not None:
                node.setLeft(self._rotate_left(left_child))
            return self._rotate_right(node)

        if balance < -1:
            right_child = node.getRight()
            if right_child is not None and self._balance_factor(right_child) <= 0:
                self.count_rr += 1
                return self._rotate_left(node)

            self.count_rl += 1
            if right_child is not None:
                node.setRight(self._rotate_right(right_child))
            return self._rotate_left(node)

        return node

    def insert(self, key: KeyType, event: Any) -> Node:
        """Insert an event and return its node; duplicate keys raise ValueError."""
        new_node = Node(key, event)
        self.root, inserted_node = self._insert_recursive(self.root, new_node)
        self._size += 1
        return inserted_node

    def _insert_recursive(
        self, current: Optional[Node], new_node: Node
    ) -> Tuple[Node, Node]:
        if current is None:
            return new_node, new_node

        comparison = _compare_keys(new_node.getKey(), current.getKey())
        if comparison == 0:
            raise ValueError(f"Key {new_node.getKey()} already exists in the tree.")
        if comparison < 0:
            current.setLeft(
                self._insert_recursive(current.getLeft(), new_node)[0]
            )
        else:
            current.setRight(
                self._insert_recursive(current.getRight(), new_node)[0]
            )

        current.update_height()
        if self.stress_mode:
            return current, new_node
        return self._rebalance_node(current), new_node

    def search(self, key: KeyType) -> Tuple[Optional[Node], int]:
        """Return the matching node and the number of nodes visited."""
        current = self.root
        visited = 0

        while current is not None:
            visited += 1
            comparison = _compare_keys(key, current.getKey())
            if comparison == 0:
                return current, visited
            current = (
                current.getLeft() if comparison < 0 else current.getRight()
            )

        return None, visited

    def delete(self, key: KeyType) -> Optional[Node]:
        """Delete and return the removed node, or None if the key is absent."""
        deleted_node, self.root = self._delete_recursive(self.root, key)
        if deleted_node is not None:
            self._size -= 1
        return deleted_node

    def _delete_recursive(
        self, current: Optional[Node], key: KeyType
    ) -> Tuple[Optional[Node], Optional[Node]]:
        if current is None:
            return None, None

        comparison = _compare_keys(key, current.getKey())
        deleted: Optional[Node] = None

        if comparison < 0:
            deleted, child = self._delete_recursive(current.getLeft(), key)
            current.setLeft(child)
        elif comparison > 0:
            deleted, child = self._delete_recursive(current.getRight(), key)
            current.setRight(child)
        else:
            if current.getLeft() is None:
                replacement = current.getRight()
                current.setRight(None)
                return current, replacement
            if current.getRight() is None:
                replacement = current.getLeft()
                current.setLeft(None)
                return current, replacement

            deleted = Node(current.getKey(), current.getEvent())
            predecessor = self._find_max(current.getLeft())
            current.setKey(predecessor.getKey())
            current.setEvent(predecessor.getEvent())
            _, left_subtree = self._delete_recursive(
                current.getLeft(), predecessor.getKey()
            )
            current.setLeft(left_subtree)

        current.update_height()
        if self.stress_mode:
            return deleted, current
        return deleted, self._rebalance_node(current)

    def _find_max(self, node: Node) -> Node:
        """Return the largest-key node in a subtree."""
        current = node
        while current.getRight() is not None:
            current = current.getRight()
        return current

    def restore_avl_balance(self) -> int:
        """Restore AVL balance bottom-up without rebuilding from a sorted list."""
        rotations_before = self.count_left_rotations + self.count_right_rotations
        max_passes = max(5, self._size)

        def repair_subtree(node: Optional[Node]) -> Optional[Node]:
            if node is None:
                return None
            node.setLeft(repair_subtree(node.getLeft()))
            node.setRight(repair_subtree(node.getRight()))
            node.update_height()

            while abs(self._balance_factor(node)) > 1:
                node = self._rebalance_node(node)
                if node.getLeft() is not None:
                    node.getLeft().update_height()
                if node.getRight() is not None:
                    node.getRight().update_height()
                node.update_height()

            return node

        for _ in range(max_passes):
            self.root = repair_subtree(self.root)
            if not self.audit_balance():
                self.stress_mode = False
                rotations_after = (
                    self.count_left_rotations + self.count_right_rotations
                )
                return rotations_after - rotations_before

        raise RuntimeError("AVL recovery did not converge; stress mode remains active.")

    def audit_balance(self) -> List[str]:
        """Return balance-factor violations in the tree."""
        violations = []
        stack = [self.root] if self.root is not None else []
        while stack:
            node = stack.pop()
            balance = self._balance_factor(node)
            if abs(balance) > 1:
                violations.append(
                    f"Node {node.getKey()} has balance factor {balance}."
                )
            if node.getLeft() is not None:
                stack.append(node.getLeft())
            if node.getRight() is not None:
                stack.append(node.getRight())
        return violations

    def audit_structure(self) -> List[str]:
        """Check key ordering, node uniqueness, heights, and AVL balance."""
        issues = []
        visited: Set[int] = set()
        seen_keys: Set[KeyType] = set()

        def verify(
            node: Optional[Node],
            minimum: Optional[KeyType],
            maximum: Optional[KeyType],
        ) -> int:
            if node is None:
                return -1

            node_id = id(node)
            if node_id in visited:
                issues.append(
                    f"Cycle or duplicate node reference detected at key {node.getKey()}."
                )
                return -1
            visited.add(node_id)

            key = node.getKey()
            if key in seen_keys:
                issues.append(f"Duplicate key {key} detected in tree.")
            seen_keys.add(key)

            if minimum is not None and _compare_keys(key, minimum) <= 0:
                issues.append(f"BST order violation: {key} <= {minimum}.")
            if maximum is not None and _compare_keys(key, maximum) >= 0:
                issues.append(f"BST order violation: {key} >= {maximum}.")

            left_height = verify(node.getLeft(), minimum, key)
            right_height = verify(node.getRight(), key, maximum)
            expected_height = 1 + max(left_height, right_height)
            if node.getHeight() != expected_height:
                issues.append(
                    f"Height mismatch at {key}: stored {node.getHeight()}, "
                    f"calculated {expected_height}."
                )

            expected_balance = left_height - right_height
            if self._balance_factor(node) != expected_balance:
                issues.append(f"Balance factor mismatch at {key}.")
            if not self.stress_mode and abs(expected_balance) > 1:
                issues.append(f"AVL balance violation at {key}.")

            return expected_height

        verify(self.root, None, None)
        if len(visited) != self._size:
            issues.append(
                f"Stored size {self._size} does not match reachable node count "
                f"{len(visited)}."
            )
        return issues

    def count_leaves(self) -> int:
        """Return the number of leaf nodes."""
        if self.root is None:
            return 0

        leaves = 0
        stack = [self.root]
        while stack:
            node = stack.pop()
            left = node.getLeft()
            right = node.getRight()
            if left is None and right is None:
                leaves += 1
            else:
                if right is not None:
                    stack.append(right)
                if left is not None:
                    stack.append(left)
        return leaves

    def max_depth(self) -> int:
        """Return the maximum node depth, equal to the tree height."""
        return self.height

    def inorder(self) -> List[Node]:
        """Return nodes in ascending key order."""
        result = []
        stack = []
        current = self.root
        while current is not None or stack:
            while current is not None:
                stack.append(current)
                current = current.getLeft()
            current = stack.pop()
            result.append(current)
            current = current.getRight()
        return result

    def preorder(self) -> List[Node]:
        """Return nodes in root-left-right order."""
        if self.root is None:
            return []

        result = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            result.append(node)
            if node.getRight() is not None:
                stack.append(node.getRight())
            if node.getLeft() is not None:
                stack.append(node.getLeft())
        return result

    def postorder(self) -> List[Node]:
        """Return nodes in left-right-root order."""
        if self.root is None:
            return []

        result = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            result.append(node)
            if node.getLeft() is not None:
                stack.append(node.getLeft())
            if node.getRight() is not None:
                stack.append(node.getRight())
        return result[::-1]

    def level_order(self) -> List[Node]:
        """Return nodes in breadth-first order."""
        if self.root is None:
            return []

        result = []
        queue: Deque[Node] = deque([self.root])
        while queue:
            node = queue.popleft()
            result.append(node)
            if node.getLeft() is not None:
                queue.append(node.getLeft())
            if node.getRight() is not None:
                queue.append(node.getRight())
        return result

    def breadth_first(self) -> List[Node]:
        """Alias for level-order traversal."""
        return self.level_order()

    def draw(self) -> None:
        """Print a sideways view of the tree."""
        if self.root is None:
            print("The tree is empty")
            return

        print("\nAVL Tree:")
        print("---------")
        self._draw(self.root, "", "R")

    def _draw(self, node: Optional[Node], space: str, position: str) -> None:
        if node is None:
            return
        self._draw(node.getRight(), space + "     ", "R")
        print(f"{space}{position}-- {node.getKey()}")
        self._draw(node.getLeft(), space + "     ", "L")
