


from typing import Optional, Tuple, Any


class Node:

    def __init__(self, key: Tuple[int, float, int], event: Any):

        self.key = key
        self.event = event

        self.left: Optional["Node"] = None
        self.right: Optional["Node"] = None

        self.height = 0


    def getKey(self):
        return self.key


    def setKey(self, key):
        self.key = key


    def getEvent(self):
        return self.event


    def setEvent(self, event):
        self.event = event


    def getLeft(self):
        return self.left


    def setLeft(self, node):
        self.left = node


    def getRight(self):
        return self.right


    def setRight(self, node):
        self.right = node


    def getHeight(self):
        return self.height


    def setHeight(self, height):
        self.height = height


    def balance_factor(self) -> int:

        left_h = self.left.height if self.left is not None else -1
        right_h = self.right.height if self.right is not None else -1

        return left_h - right_h


    def update_height(self):

        left_h = self.left.height if self.left is not None else -1
        right_h = self.right.height if self.right is not None else -1

        self.height = 1 + max(left_h, right_h)


