
"""
A stack is a structure that allows for storing history and undoing actions, 
operating according to stack principles.
"""

class Stack:
    def __init__(self):
        self.items = []

    def push(self, nodo):
        self.items.append(nodo)

    def pop(self):
        if self.is_empty():
            return None

        return self.items.pop()

    def peek(self):
        if self.is_empty():
            return None

        return self.items[-1]

    def is_empty(self):
        return len(self.items) == 0

    def size(self):
        return len(self.items)

    def clear(self):
        self.items.clear()