from Node import Node
from typing import Optional, Tuple, Any



class AVLTree:

    def __init__(self):

        self.root = None


    
    # INSERT
    

    # Public insert method
    def insert(self, value):


        node = Node(value)

        if self.root is None:

            self.root = node

            node.setPadre(None)

            print(
                "Value ",
                value,
                " was inserted as the root of the tree"
            )

        else:

            self._insert(
                node,
                self.root
            )


    # Private insert method
    def _insert(self, node, current_root):

        # Check if the value already exists
        if node.getValor() == current_root.getValor():

            print(
                "A node with value ",
                node.getValor(),
                " already exists"
            )

            return


        
        if node.getValor() < current_root.getValor():

            left = current_root.getHijoIzquierdo()

            if left is None:

                current_root.setHijoIzquierdo(node)

                node.setPadre(current_root)

                print(
                    node.getValor(),
                    " was inserted as the left child of ",
                    current_root.getValor()
                )

                self._rebalance(current_root)

            else:

                self._insert(
                    node,
                    left
                )


        
        else:

            right = current_root.getHijoDerecho()

            if right is None:

                current_root.setHijoDerecho(node)

                node.setPadre(current_root)

                print(
                    node.getValor(),
                    " was inserted as the right child of ",
                    current_root.getValor()
                )

                self._rebalance(current_root)

            else:

                self._insert(
                    node,
                    right
                )


    
    # HEIGHT
    

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


    
    # BALANCE FACTOR
    

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


    
    # REBALANCE
    

    def _rebalance(self, node):

        current = node

        while current is not None:

            balance = self._balance_factor(
                current
            )


            
            # LEFT HEAVY
            

            if balance > 1:

                left_child = current.getHijoIzquierdo()

                left_balance = self._balance_factor(
                    left_child
                )


                # Left-Left case
                if left_balance >= 0:

                    if current == self.root:

                        self._rotate_right(current)

                    else:

                        parent = current.getPadre()

                        new_root = self._rotate_right(
                            current
                        )

                        if parent.getHijoIzquierdo() == current:

                            parent.setHijoIzquierdo(
                                new_root
                            )

                        else:

                            parent.setHijoDerecho(
                                new_root
                            )

                            new_root.setPadre(
                                parent
                            )


                # Left-Right case
                else:

                    left_child = current.getHijoIzquierdo()

                    self._rotate_left(
                        left_child
                    )

                    if current == self.root:

                        self._rotate_right(
                            current
                        )

                    else:

                        parent = current.getPadre()

                        new_root = self._rotate_right(
                            current
                        )

                        if parent.getHijoIzquierdo() == current:

                            parent.setHijoIzquierdo(
                                new_root
                            )

                        else:

                            parent.setHijoDerecho(
                                new_root
                            )

                        new_root.setPadre(
                            parent
                        )


            
            # RIGHT HEAVY

            elif balance < -1:

                right_child = current.getHijoDerecho()

                right_balance = self._balance_factor(
                    right_child
                )


                # Right-Right case
                if right_balance <= 0:

                    if current == self.root:

                        self._rotate_left(
                            current
                        )

                    else:

                        parent = current.getPadre()

                        new_root = self._rotate_left(
                            current
                        )

                        if parent.getHijoIzquierdo() == current:

                            parent.setHijoIzquierdo(
                                new_root
                            )

                        else:

                            parent.setHijoDerecho(
                                new_root
                            )

                        new_root.setPadre(
                            parent
                        )


                # Right-Left case
                else:

                    right_child = current.getHijoDerecho()

                    self._rotate_right(
                        right_child
                    )

                    if current == self.root:

                        self._rotate_left(
                            current
                        )

                    else:

                        parent = current.getPadre()

                        new_root = self._rotate_left(
                            current
                        )

                        if parent.getHijoIzquierdo() == current:

                            parent.setHijoIzquierdo(
                                new_root
                            )

                        else:

                            parent.setHijoDerecho(
                                new_root
                            )

                        new_root.setPadre(
                            parent
                        )


            current = current.getPadre()


    # --------------------------------------------------
    # RIGHT ROTATION
    # --------------------------------------------------

    def _rotate_right(self, node):

        new_root = node.getHijoIzquierdo()

        subtree = new_root.getHijoDerecho()

        parent = node.getPadre()


        # Perform rotation
        new_root.setHijoDerecho(node)

        node.setPadre(new_root)

        node.setHijoIzquierdo(subtree)


        if subtree is not None:

            subtree.setPadre(node)


        # Connect new root with parent
        new_root.setPadre(parent)


        if parent is None:

            self.root = new_root

        else:

            if parent.getHijoIzquierdo() == node:

                parent.setHijoIzquierdo(
                    new_root
                )

            else:

                parent.setHijoDerecho(
                    new_root
                )


        return new_root


    # LEFT ROTATION

    def _rotate_left(self, node):

        new_root = node.getHijoDerecho()

        subtree = new_root.getHijoIzquierdo()

        parent = node.getPadre()


        # Perform rotation
        new_root.setHijoIzquierdo(node)

        node.setPadre(new_root)

        node.setHijoDerecho(subtree)


        if subtree is not None:

            subtree.setPadre(node)


        # Connect new root with parent
        new_root.setPadre(parent)


        if parent is None:

            self.root = new_root

        else:

            if parent.getHijoIzquierdo() == node:

                parent.setHijoIzquierdo(
                    new_root
                )

            else:

                parent.setHijoDerecho(
                    new_root
                )


        return new_root


    # SEARCH

    def search(self, value):

        if self.root is None:

            print("The tree is empty")

            return None

        return self._search(
            value,
            self.root
        )


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

        else:

            return self._search(
                value,
                current_root.getHijoDerecho()
            )


    # DELETE

    def delete(self, value):

        node = self.search(value)

        if node is None:

            print(
                "There is no node with value ",
                value
            )

            return


        parent = node.getPadre()

        self._delete(node)

        print(
            "Node with value ",
            value,
            " was deleted"
        )


        # Rebalance from the parent
        if parent is not None:

            self._rebalance(parent)

        elif self.root is not None:

            self._rebalance(
                self.root
            )


    # Private delete method
    def _delete(self, node):

        # CASE 1
        # Node is a leaf

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

            return


        # CASE 2
        # Only right child

        if node.getHijoIzquierdo() is None:

            child = node.getHijoDerecho()

            parent = node.getPadre()


            if parent is None:

                self.root = child

                child.setPadre(None)

            else:

                if parent.getHijoIzquierdo() == node:

                    parent.setHijoIzquierdo(
                        child
                    )

                else:

                    parent.setHijoDerecho(
                        child
                    )

                child.setPadre(parent)


            node.setPadre(None)

            node.setHijoDerecho(None)

            return


        # CASE 3
        # Only left child

        if node.getHijoDerecho() is None:

            child = node.getHijoIzquierdo()

            parent = node.getPadre()


            if parent is None:

                self.root = child

                child.setPadre(None)

            else:

                if parent.getHijoIzquierdo() == node:

                    parent.setHijoIzquierdo(
                        child
                    )

                else:

                    parent.setHijoDerecho(
                        child
                    )

                child.setPadre(parent)


            node.setPadre(None)

            node.setHijoIzquierdo(None)

            return


        # CASE 4
        # Two children
        #
        # Use predecessor

        predecessor = self._get_predecessor(
            node
        )


        # Copy predecessor value
        node.setValor(
            predecessor.getValor()
        )


        # Delete predecessor
        self._delete(
            predecessor
        )


    # GET PREDECESSOR

    def _get_predecessor(self, node):

        current = node.getHijoIzquierdo()

        while current.getHijoDerecho() is not None:

            current = current.getHijoDerecho()

        return current


    # BREADTH-FIRST TRAVERSAL

    def breadth_first(self):

        if self.root is None:

            print("The tree is empty")

            return []


        queue = []

        traversal = []

        queue.append(
            self.root
        )


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


    # PREORDER
    # root - left - right

    def preorder(self):

        if self.root is None:

            print("The tree is empty")

        else:

            self._preorder(
                self.root
            )


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


    # INORDER
    # left - root - right

    def inorder(self):

        if self.root is None:

            print("The tree is empty")

        else:

            self._inorder(
                self.root
            )


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


    # POSTORDER
    # left - right - root

    def postorder(self):

        if self.root is None:

            print("The tree is empty")

        else:

            self._postorder(
                self.root
            )


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


    # DRAW

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

