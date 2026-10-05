"""
Comparator for the SismoLab AVL / BST trees.

Key type: Tuple[int, int, int]  ->  (priority, magnitude10, event_id)
  - priority    : 3 = HIGH  /  2 = MEDIUM  /  1 = LOW
  - magnitude10 : seismic magnitude × 10  (e.g. 5.2  stored as 52)
  - event_id    : unique integer identifier  [1, 999999]

Ordering contract (matches the trees' _compare_keys and Node.key()):
  - Higher priority  -> comes first  (descending)
  - Equal priority, higher magnitude -> comes first  (descending)
  - Equal priority and magnitude, lower event_id -> comes first  (ascending)

compare(a, b) returns:
   -1  if  a  should be visited / stored BEFORE  b
    0  if  a  and  b  are the same node (duplicate key)
    1  if  a  should be visited / stored AFTER   b

The sign convention (-1 / 0 / 1) is the same one used by _compare_keys
in Avl.py, so the trees can delegate to this module directly.
"""

from typing import Tuple

KeyType = Tuple[int, int, int]   # (priority, magnitude10, event_id)


def compare(a: KeyType, b: KeyType) -> int:
    """
    Compare two event keys.

    Parameters
    ----------
    a, b : (int, int, int)
        Keys produced by EventRecord.key():
        index 0 -> priority  (3/2/1)
        index 1 -> magnitude10
        index 2 -> event_id

    Returns
    -------
    int
        -1  if a < b  (a goes to the LEFT child / is inserted first)
         0  if a == b (duplicate; the trees raise ValueError on this)
         1  if a > b  (a goes to the RIGHT child)
    """

    a_priority, a_mag, a_id = a
    b_priority, b_mag, b_id = b

    # --- Priority (descending): higher priority is "smaller" in tree order ---
    if a_priority > b_priority:
        return -1
    if a_priority < b_priority:
        return 1

    # --- Magnitude (descending): higher magnitude is "smaller" in tree order ---
    if a_mag > b_mag:
        return -1
    if a_mag < b_mag:
        return 1

    # --- Event ID (ascending): lower ID is "smaller" in tree order ---
    if a_id < b_id:
        return -1
    if a_id > b_id:
        return 1

    return 0   # identical key -> duplicate


def is_less_than(a: KeyType, b: KeyType) -> bool:
    """Return True if key *a* should be placed in the left subtree of *b*."""
    return compare(a, b) < 0


def is_greater_than(a: KeyType, b: KeyType) -> bool:
    """Return True if key *a* should be placed in the right subtree of *b*."""
    return compare(a, b) > 0


def are_equal(a: KeyType, b: KeyType) -> bool:
    """Return True if *a* and *b* identify the same node (duplicate key)."""
    return compare(a, b) == 0