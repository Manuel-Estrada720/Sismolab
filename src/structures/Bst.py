
from Node import Node
from typing import Optional, Tuple, Any


class BSTTree:

    def __init__(self):
        self.root = None


    
    def insert(self, key, event):

        node = Node(key, event)

        if self.root is None:

            self.root = node

            print(
                "Key ", key,
                " was inserted as the root of the tree"
            )

        else:

            self._insert(
                node,
                self.root
            )


    
    def _insert(self, node, current_root):

        
        if current_root.getKey() == node.getKey():

            print(
                "A node with key ",
                node.getKey(),
                " already exists"
            )

        else:

            
            if node.getKey() < current_root.getKey():

                left = current_root.getLeft()

                if left is None:

                    current_root.setLeft(node)

                    print(
                        node.getKey(),
                        " was inserted as the left child of ",
                        current_root.getKey()
                    )

                else:

                    self._insert(
                        node,
                        left
                    )


            
            else:

                right = current_root.getRight()

                if right is None:

                    current_root.setRight(node)

                    print(
                        node.getKey(),
                        " was inserted as the right child of ",
                        current_root.getKey()
                    )

                else:

                    self._insert(
                        node,
                        right
                    )


    
    # SEARCH
    

    # Public search method
    def search(self, key):

        if self.root is None:

            print("The tree is empty")

            return None

        else:

            return self._search(
                key,
                self.root
            )


    # Private search method
    def _search(self, key, current_root):

        if key == current_root.getKey():

            return current_root


        if key < current_root.getKey():

            left = current_root.getLeft()

            if left is None:

                return None

            else:

                return self._search(
                    key,
                    left
                )


        else:

            right = current_root.getRight()

            if right is None:

                return None

            else:

                return self._search(
                    key,
                    right
                )


    # BREADTH-FIRST TRAVERSAL

    def breadth_first(self):

        if self.root is None:

            print("The tree is empty")

            return []

        else:

            return self._breadth_first(
                self.root
            )


    def _breadth_first(self, current_root):

        queue = []
        traversal = []

        queue.append(current_root)

        while len(queue) > 0:

            node = queue.pop(0)

            traversal.append(node)

            if node.getLeft() is not None:

                queue.append(
                    node.getLeft()
                )

            if node.getRight() is not None:

                queue.append(
                    node.getRight()
                )

        return traversal


    # PREORDER TRAVERSAL
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
                current_root.getKey()
            )

            self._preorder(
                current_root.getLeft()
            )

            self._preorder(
                current_root.getRight()
            )


    # INORDER TRAVERSAL
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
                current_root.getLeft()
            )

            print(
                current_root.getKey()
            )

            self._inorder(
                current_root.getRight()
            )


    # POSTORDER TRAVERSAL
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
                current_root.getLeft()
            )

            self._postorder(
                current_root.getRight()
            )

            print(
                current_root.getKey()
            )


    # DELETE

    # Public delete method
    def delete(self, key):

        if self.root is None:

            print("The tree is empty")

        else:

            node = self.search(key)

            if node is None:

                print(
                    "There is no node with key ",
                    key
                )

            else:

                self._delete(node)

                print(
                    "Node with key ",
                    key,
                    " was deleted"
                )


    # Private delete method
    def _delete(self, node):

        # CASE 1
        # The node is a leaf

        if (
            node.getLeft() is None
            and
            node.getRight() is None
        ):

            if node == self.root:

                self.root = None

            else:

                parent = self._get_parent(node)

                if parent.getLeft() == node:

                    parent.setLeft(None)

                else:

                    parent.setRight(None)

            return


        # CASE 2
        # The node only has a right child

        if node.getLeft() is None:

            child = node.getRight()

            if node == self.root:

                self.root = child

            else:

                parent = self._get_parent(node)

                if parent.getLeft() == node:

                    parent.setLeft(child)

                else:

                    parent.setRight(child)

            return


        # CASE 2
        # The node only has a left child

        if node.getRight() is None:

            child = node.getLeft()

            if node == self.root:

                self.root = child

            else:

                parent = self._get_parent(node)

                if parent.getLeft() == node:

                    parent.setLeft(child)

                else:

                    parent.setRight(child)

            return


        # CASE 3
        # The node has two children
        #
        # We use the predecessor

        predecessor = self._get_predecessor(node)

        # Copy the predecessor data
        node.setKey(
            predecessor.getKey()
        )

        node.setEvent(
            predecessor.getEvent()
        )

        # Delete the predecessor
        self._delete(
            predecessor
        )


    # GET PARENT

    def _get_parent(self, node):

        if node == self.root:

            return None

        current = self.root

        while current is not None:

            if (
                current.getLeft() == node
                or
                current.getRight() == node
            ):

                return current

            if node.getKey() < current.getKey():

                current = current.getLeft()

            else:

                current = current.getRight()

        return None


    # GET PREDECESSOR
    #
    # Returns the largest node
    # from the left subtree

    def _get_predecessor(self, node):

        current = node.getLeft()

        while current.getRight() is not None:

            current = current.getRight()

        return current


    # DRAW

    def draw(self):

        if self.root is None:

            print("The tree is empty")

        else:

            print("\nBinary Search Tree:")
            print("-------------------")

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
                current_root.getRight(),
                space + "     ",
                "R"
            )

            print(
                space +
                position +
                "── " +
                str(current_root.getKey())
            )

            self._draw(
                current_root.getLeft(),
                space + "     ",
                "L"
            )