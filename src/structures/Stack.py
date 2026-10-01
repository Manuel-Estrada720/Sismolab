from collections import deque


class Queue:

    def __init__(self):
        self.items = deque()


    def enqueue(self, item):
        self.items.append(item)


    def dequeue(self):

        if self.is_empty():
            raise IndexError("The queue is empty")

        return self.items.popleft()


    def peek(self):

        if self.is_empty():
            return None

        return self.items[0]


    def is_empty(self):

        return len(self.items) == 0


    def size(self):

        return len(self.items)


    def to_list(self):

        return list(self.items)


    def clear(self):

        self.items.clear()