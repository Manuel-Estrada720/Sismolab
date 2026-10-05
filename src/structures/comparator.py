"""Key comparison shared by the AVL and the BST.

A key is the tuple K = (P, M, I):
    P = priority (1, 2 or 3)
    M = magnitude in tenths (5.2 -> 52)
    I = numeric event id

The comparison is lexicographic: the first different component decides.
"""


def compare_keys(first, second):
    """Return -1 if first < second, 1 if first > second and 0 if they are equal."""
    for a, b in zip(first, second):
        if a < b:
            return -1
        if a > b:
            return 1
    # All shared components are equal: the shorter key is the smaller one
    if len(first) < len(second):
        return -1
    if len(first) > len(second):
        return 1
    return 0
