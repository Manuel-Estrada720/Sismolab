"""Binary search tree WITHOUT balancing. It is used to compare against the AVL.

It uses the same Node class and the same key comparator as the AVL, so both
trees order the events in exactly the same way.
"""

from .Node import Node
from .comparator import compare_keys


class BSTTree:

    def __init__(self):
        self.root = None
        self._size = 0

    # INSERT

    # Public insert method. Returns the new node.
    # A repeated key raises ValueError (the tree never holds duplicates).
    def insert(self, key, event):

        node = Node(key, event)

        if self.root is None:
            self.root = node
            self._size += 1
            return node

        self._insert(node, self.root)
        self._size += 1
        return node

    # Private insert method. It walks down with a loop instead of recursion,
    # so a degenerate tree (ascending keys) does not hit Python's recursion limit.
    def _insert(self, node, current_root):

        current = current_root

        while True:

            comparison = compare_keys(node.getKey(), current.getKey())

            if comparison == 0:
                raise ValueError(
                    "A node with key " + str(node.getKey()) + " already exists"
                )

            if comparison < 0:

                if current.getLeft() is None:
                    current.setLeft(node)
                    return
                current = current.getLeft()

            else:

                if current.getRight() is None:
                    current.setRight(node)
                    return
                current = current.getRight()

    # SEARCH

    # Public search method.
    # Returns (node, visited): the node (or None) and how many nodes were compared.
    def search(self, key):

        current = self.root
        visited = 0

        while current is not None:

            visited += 1
            comparison = compare_keys(key, current.getKey())

            if comparison == 0:
                return current, visited

            if comparison < 0:
                current = current.getLeft()
            else:
                current = current.getRight()

        return None, visited

    # SIZE, HEIGHT, LEAVES AND DEPTH

    def size(self):
        return self._size

    # Height of the empty tree is -1 and height of a leaf is 0
    def height(self):
        return self._height(self.root)

    def _height(self, current_root):

        if current_root is None:
            return -1

        # Breadth-first walk, level by level
        level = [current_root]
        height = -1

        while len(level) > 0:

            height += 1
            next_level = []

            for node in level:
                if node.getLeft() is not None:
                    next_level.append(node.getLeft())
                if node.getRight() is not None:
                    next_level.append(node.getRight())

            level = next_level

        return height

    # The deepest node has depth equal to the tree height
    def max_depth(self):
        return self.height()

    def count_leaves(self):

        leaves = 0

        for node in self.preorder():
            if node.getLeft() is None and node.getRight() is None:
                leaves += 1

        return leaves

    # Depth of every node: {id(node): depth}. The root has depth 0.
    def depths(self):

        result = {}

        if self.root is None:
            return result

        stack = [(self.root, 0)]

        while len(stack) > 0:

            node, depth = stack.pop()
            result[id(node)] = depth

            if node.getLeft() is not None:
                stack.append((node.getLeft(), depth + 1))
            if node.getRight() is not None:
                stack.append((node.getRight(), depth + 1))

        return result

    # BREADTH-FIRST TRAVERSAL

    def breadth_first(self):

        if self.root is None:
            return []

        return self._breadth_first(self.root)

    def _breadth_first(self, current_root):

        queue = [current_root]
        traversal = []
        position = 0

        # The list works as a queue: "position" points to the next node to visit
        while position < len(queue):

            node = queue[position]
            position += 1
            traversal.append(node)

            if node.getLeft() is not None:
                queue.append(node.getLeft())

            if node.getRight() is not None:
                queue.append(node.getRight())

        return traversal

    # PREORDER TRAVERSAL
    # root - left - right

    def preorder(self):

        traversal = []

        if self.root is None:
            return traversal

        stack = [self.root]

        while len(stack) > 0:

            node = stack.pop()
            traversal.append(node)

            # Right first so the left child is visited first
            if node.getRight() is not None:
                stack.append(node.getRight())
            if node.getLeft() is not None:
                stack.append(node.getLeft())

        return traversal

    # INORDER TRAVERSAL
    # left - root - right

    def inorder(self):

        traversal = []
        stack = []
        current = self.root

        while current is not None or len(stack) > 0:

            while current is not None:
                stack.append(current)
                current = current.getLeft()

            current = stack.pop()
            traversal.append(current)
            current = current.getRight()

        return traversal

    # POSTORDER TRAVERSAL
    # left - right - root

    def postorder(self):

        traversal = []

        if self.root is None:
            return traversal

        stack = [self.root]

        while len(stack) > 0:

            node = stack.pop()
            traversal.append(node)

            if node.getLeft() is not None:
                stack.append(node.getLeft())
            if node.getRight() is not None:
                stack.append(node.getRight())

        # root-right-left reversed is left-right-root
        traversal.reverse()
        return traversal

    # DELETE

    # Public delete method. Returns the deleted node or None if the key is absent.
    def delete(self, key):

        parent = None
        node = self.root

        # Find the node and remember its parent
        while node is not None:

            comparison = compare_keys(key, node.getKey())

            if comparison == 0:
                break

            parent = node

            if comparison < 0:
                node = node.getLeft()
            else:
                node = node.getRight()

        if node is None:
            return None

        removed = Node(node.getKey(), node.getEvent())
        self._delete(node, parent)
        self._size -= 1
        return removed

    # Private delete method. "parent" is None when node is the root.
    def _delete(self, node, parent):

        # CASE 3
        # The node has two children
        #
        # We use the predecessor (the largest node of the left subtree)

        if node.getLeft() is not None and node.getRight() is not None:

            predecessor_parent = node
            predecessor = node.getLeft()

            while predecessor.getRight() is not None:
                predecessor_parent = predecessor
                predecessor = predecessor.getRight()

            # Copy the predecessor data
            node.setKey(predecessor.getKey())
            node.setEvent(predecessor.getEvent())

            # Delete the predecessor. It has no right child, so it is case 1 or 2
            self._delete(predecessor, predecessor_parent)
            return

        # CASE 1 and CASE 2
        # The node is a leaf or has only one child

        if node.getLeft() is not None:
            child = node.getLeft()
        else:
            child = node.getRight()

        if parent is None:
            self.root = child
        elif parent.getLeft() is node:
            parent.setLeft(child)
        else:
            parent.setRight(child)

    # DRAW (only for debugging in the console)

    def draw(self):

        if self.root is None:
            print("The tree is empty")
        else:
            print("\nBinary Search Tree:")
            print("-------------------")
            self._draw(self.root, "", "R")

    def _draw(self, current_root, space, position):

        if current_root is not None:
            self._draw(current_root.getRight(), space + "     ", "R")
            print(space + position + "── " + str(current_root.getKey()))
            self._draw(current_root.getLeft(), space + "     ", "L")
