
from Node import Node


class AVLTree:

    def __init__(self):
        self.root = None

    # --------------------------------------------------
    # INSERT
    # --------------------------------------------------

    def insert(self, value):
        node = Node(value)

        if self.root is None:
            self.root = node
            node.setPadre(None)

            print(
                "Value",
                value,
                "was inserted as the root of the tree"
            )

        else:
            self._insert(node, self.root)

    def _insert(self, node, current_root):

        # Check if the value already exists
        if node.getValor() == current_root.getValor():
            print(
                "A node with value",
                node.getValor(),
                "already exists"
            )
            return

        # Insert on the left
        if node.getValor() < current_root.getValor():

            left = current_root.getHijoIzquierdo()

            if left is None:
                current_root.setHijoIzquierdo(node)
                node.setPadre(current_root)

                print(
                    node.getValor(),
                    "was inserted as the left child of",
                    current_root.getValor()
                )

                self._rebalance(current_root)

            else:
                self._insert(node, left)

        # Insert on the right
        else:

            right = current_root.getHijoDerecho()

            if right is None:
                current_root.setHijoDerecho(node)
                node.setPadre(current_root)

                print(
                    node.getValor(),
                    "was inserted as the right child of",
                    current_root.getValor()
                )

                self._rebalance(current_root)

            else:
                self._insert(node, right)

    # --------------------------------------------------
    # HEIGHT
    # --------------------------------------------------

    def _height(self, node):

        if node is None:
            return -1

        left_height = self._height(
            node.getHijoIzquierdo()
        )

        right_height = self._height(
            node.getHijoDerecho()
        )

        return 1 + max(
            left_height,
            right_height
        )

    # --------------------------------------------------
    # BALANCE FACTOR
    # --------------------------------------------------

    def _balance_factor(self, node):

        if node is None:
            return 0

        left_height = self._height(
            node.getHijoIzquierdo()
        )

        right_height = self._height(
            node.getHijoDerecho()
        )

        return left_height - right_height

    # --------------------------------------------------
    # REBALANCE
    # --------------------------------------------------

    def _rebalance(self, node):

        current = node

        while current is not None:

            balance = self._balance_factor(current)

            # Left heavy
            if balance > 1:

                left_child = current.getHijoIzquierdo()

                # Left-Right case
                if self._balance_factor(left_child) < 0:
                    self._rotate_left(left_child)

                # Left-Left case
                new_root = self._rotate_right(current)

                current = new_root.getPadre()

            # Right heavy
            elif balance < -1:

                right_child = current.getHijoDerecho()

                # Right-Left case
                if self._balance_factor(right_child) > 0:
                    self._rotate_right(right_child)

                # Right-Right case
                new_root = self._rotate_left(current)

                current = new_root.getPadre()

            else:
                current = current.getPadre()

    # --------------------------------------------------
    # RIGHT ROTATION
    # --------------------------------------------------

    def _rotate_right(self, node):

        new_root = node.getHijoIzquierdo()

        if new_root is None:
            return node

        subtree = new_root.getHijoDerecho()
        parent = node.getPadre()

        # Move subtree
        node.setHijoIzquierdo(subtree)

        if subtree is not None:
            subtree.setPadre(node)

        # Rotate
        new_root.setHijoDerecho(node)
        node.setPadre(new_root)

        # Connect with parent
        new_root.setPadre(parent)

        if parent is None:
            self.root = new_root

        else:
            if parent.getHijoIzquierdo() == node:
                parent.setHijoIzquierdo(new_root)
            else:
                parent.setHijoDerecho(new_root)

        return new_root

    # --------------------------------------------------
    # LEFT ROTATION
    # --------------------------------------------------

    def _rotate_left(self, node):

        new_root = node.getHijoDerecho()

        if new_root is None:
            return node

        subtree = new_root.getHijoIzquierdo()
        parent = node.getPadre()

        # Move subtree
        node.setHijoDerecho(subtree)

        if subtree is not None:
            subtree.setPadre(node)

        # Rotate
        new_root.setHijoIzquierdo(node)
        node.setPadre(new_root)

        # Connect with parent
        new_root.setPadre(parent)

        if parent is None:
            self.root = new_root

        else:
            if parent.getHijoIzquierdo() == node:
                parent.setHijoIzquierdo(new_root)
            else:
                parent.setHijoDerecho(new_root)

        return new_root

    # --------------------------------------------------
    # SEARCH
    # --------------------------------------------------

    def search(self, value):

        if self.root is None:
            print("The tree is empty")
            return None

        return self._search(value, self.root)

    def _search(self, value, current_root):

        if current_root is None:
            return None

        if value == current_root.getValor():
            return current_root

        if value < current_root.getValor():
            return self._search(
                value,
                current_root.getHijoIzquierdo()
            )

        return self._search(
            value,
            current_root.getHijoDerecho()
        )

    # --------------------------------------------------
    # DELETE
    # --------------------------------------------------

    def delete(self, value):

        node = self.search(value)

        if node is None:
            print(
                "There is no node with value",
                value
            )
            return

        rebalance_node = self._delete(node)

        print(
            "Node with value",
            value,
            "was deleted"
        )

        if rebalance_node is not None:
            self._rebalance(rebalance_node)

        elif self.root is not None:
            self._rebalance(self.root)

    def _delete(self, node):

        # CASE 1: Node has no children
        if (
            node.getHijoIzquierdo() is None
            and
            node.getHijoDerecho() is None
        ):

            parent = node.getPadre()

            if parent is None:
                self.root = None

            else:
                if parent.getHijoIzquierdo() == node:
                    parent.setHijoIzquierdo(None)
                else:
                    parent.setHijoDerecho(None)

            node.setPadre(None)

            return parent

        # CASE 2: Node has only right child
        if node.getHijoIzquierdo() is None:

            child = node.getHijoDerecho()
            parent = node.getPadre()

            if parent is None:
                self.root = child
                child.setPadre(None)

            else:
                if parent.getHijoIzquierdo() == node:
                    parent.setHijoIzquierdo(child)
                else:
                    parent.setHijoDerecho(child)

                child.setPadre(parent)

            node.setPadre(None)
            node.setHijoDerecho(None)

            return parent

        # CASE 3: Node has only left child
        if node.getHijoDerecho() is None:

            child = node.getHijoIzquierdo()
            parent = node.getPadre()

            if parent is None:
                self.root = child
                child.setPadre(None)

            else:
                if parent.getHijoIzquierdo() == node:
                    parent.setHijoIzquierdo(child)
                else:
                    parent.setHijoDerecho(child)

                child.setPadre(parent)

            node.setPadre(None)
            node.setHijoIzquierdo(None)

            return parent

        # CASE 4: Node has two children

        predecessor = self._get_predecessor(node)

        # Copy predecessor value
        node.setValor(
            predecessor.getValor()
        )

        # Delete predecessor
        return self._delete(predecessor)

    # --------------------------------------------------
    # GET PREDECESSOR
    # --------------------------------------------------

    def _get_predecessor(self, node):

        current = node.getHijoIzquierdo()

        while current.getHijoDerecho() is not None:
            current = current.getHijoDerecho()

        return current

    # --------------------------------------------------
    # BREADTH-FIRST TRAVERSAL
    # --------------------------------------------------

    def breadth_first(self):

        if self.root is None:
            print("The tree is empty")
            return []

        queue = [self.root]
        traversal = []

        while len(queue) > 0:

            node = queue.pop(0)
            traversal.append(node)

            if node.getHijoIzquierdo() is not None:
                queue.append(
                    node.getHijoIzquierdo()
                )

            if node.getHijoDerecho() is not None:
                queue.append(
                    node.getHijoDerecho()
                )

        return traversal

    # --------------------------------------------------
    # PREORDER
    # Root - Left - Right
    # --------------------------------------------------

    def preorder(self):

        if self.root is None:
            print("The tree is empty")
        else:
            self._preorder(self.root)

    def _preorder(self, current_root):

        if current_root is not None:

            print(
                current_root.getValor()
            )

            self._preorder(
                current_root.getHijoIzquierdo()
            )

            self._preorder(
                current_root.getHijoDerecho()
            )

    # --------------------------------------------------
    # INORDER
    # Left - Root - Right
    # --------------------------------------------------

    def inorder(self):

        if self.root is None:
            print("The tree is empty")
        else:
            self._inorder(self.root)

    def _inorder(self, current_root):

        if current_root is not None:

            self._inorder(
                current_root.getHijoIzquierdo()
            )

            print(
                current_root.getValor()
            )

            self._inorder(
                current_root.getHijoDerecho()
            )

    # --------------------------------------------------
    # POSTORDER
    # Left - Right - Root
    # --------------------------------------------------

    def postorder(self):

        if self.root is None:
            print("The tree is empty")
        else:
            self._postorder(self.root)

    def _postorder(self, current_root):

        if current_root is not None:

            self._postorder(
                current_root.getHijoIzquierdo()
            )

            self._postorder(
                current_root.getHijoDerecho()
            )

            print(
                current_root.getValor()
            )

    # --------------------------------------------------
    # DRAW
    # --------------------------------------------------

    def draw(self):

        if self.root is None:
            print("The tree is empty")
        else:
            print("\nAVL Tree:")
            print("---------")

            self._draw(
                self.root,
                "",
                "R"
            )

    def _draw(
        self,
        current_root,
        space,
        position
    ):

        if current_root is not None:

            self._draw(
                current_root.getHijoDerecho(),
                space + "     ",
                "D"
            )

            print(
                space +
                position +
                "── " +
                str(current_root.getValor())
            )

            self._draw(
                current_root.getHijoIzquierdo(),
                space + "     ",
                "I"
            )
