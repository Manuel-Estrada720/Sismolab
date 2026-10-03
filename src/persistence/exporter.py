from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from structures import Node


def _node_to_dict(node: Optional[Node]) -> Optional[Dict]:
    """Serializes a Node recursively (pre-order DFS)."""
    if node is None:
        return None
    return {
        "key": list(node.getKey()),
        "height": node.getHeight(),
        "balance": node.balance_factor(),
        "left": _node_to_dict(node.getLeft()),
        "right": _node_to_dict(node.getRight()),
        "event": _event_to_dict(node.getEvent()),
    }


def _event_to_dict(event: Any) -> Dict:
    """Converts an Event domain object to a plain dict."""
    return {
        "id": event.id,
        "magnitude": event.magnitude,
        "depth": event.depth,
        "epicenter_x": event.epicenter_x,
        "epicenter_y": event.epicenter_y,
        "occurred_at": event.occurred_at,
        "priority": event.priority,
        "in_populated_zone": event.in_populated_zone,
        "revision": event.revision,
        "stations": list(event.stations),
        "attention": event.attention,
        "reference_id": event.reference_id,
    }


def _dict_to_event(d: Dict, event_factory) -> Any:
    return event_factory(d)


def _dict_to_node(d: Optional[Dict], event_factory) -> Optional[Node]:
    """Recursively restores a Node tree from a topology dict."""
    if d is None:
        return None
    event = _dict_to_event(d["event"], event_factory)
    node = Node(tuple(d["key"]), event)
    node.setHeight(d["height"])
    node.setLeft(_dict_to_node(d.get("left"), event_factory))
    node.setRight(_dict_to_node(d.get("right"), event_factory))
    return node


def _validate_topology(
    node: Optional[Node],
    min_key: Optional[Tuple] = None,
    max_key: Optional[Tuple] = None,
    errors: Optional[List[str]] = None,
    seen_ids: Optional[set] = None,
) -> List[str]:
    """Validates BST order, heights, and ID uniqueness."""
    if errors is None: errors = []
    if seen_ids is None: seen_ids = set()
    if node is None: return errors

    key, event_id = node.getKey(), node.getEvent().id
    if event_id in seen_ids:
        errors.append(f"Duplicate event id {event_id}.")
    seen_ids.add(event_id)

    if min_key is not None and key <= min_key:
        errors.append(f"BST violation: {key} <= min {min_key}.")
    if max_key is not None and key >= max_key:
        errors.append(f"BST violation: {key} >= max {max_key}.")

    left_h = node.getLeft().getHeight() if node.getLeft() else -1
    right_h = node.getRight().getHeight() if node.getRight() else -1
    if node.getHeight() != 1 + max(left_h, right_h):
        errors.append(f"Height mismatch at {key}.")

    _validate_topology(node.getLeft(), min_key, key, errors, seen_ids)
    _validate_topology(node.getRight(), key, max_key, errors, seen_ids)
    return errors


def _check_avl_balance(node: Optional[Node], errors: List[str]) -> None:
    """Checks for AVL balance violations."""
    if node is None: return
    if node.balance_factor() not in (-1, 0, 1):
        errors.append(f"AVL balance violation at {node.getKey()}.")
    _check_avl_balance(node.getLeft(), errors)
    _check_avl_balance(node.getRight(), errors)


def _collect_active_ids(node: Optional[Node], ids: set) -> None:
    if node is None: return
    ids.add(node.getEvent().id)
    _collect_active_ids(node.getLeft(), ids)
    _collect_active_ids(node.getRight(), ids)


def save_scenario(
    avl_root, history, retired_ids, report_queue,
    simulation_clock, zones, parameters, metrics, execution_mode
) -> Dict:
    """Builds and returns the full scenario dictionary."""
    return {
        "schema_version": "1.0",
        "execution_mode": execution_mode,
        "simulation_clock": simulation_clock,
        "parameters": {
            "W": parameters["W"], "R": parameters["R"],
            "L": parameters["L"], "T": parameters["T"],
        },
        "zones": zones,
        "avl_tree": _node_to_dict(avl_root),
        "history": history,
        "retired_ids": sorted(retired_ids),
        "report_queue": report_queue,
        "metrics": metrics,
    }


def export_to_file(filepath: str, scenario_dict: Dict) -> None:
    """Writes scenario dict to file as JSON."""
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(scenario_dict, fh, indent=2, ensure_ascii=False)


def load_raw(filepath: str) -> Dict:
    """Reads and parses the JSON file."""
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_by_insertions(
    filepath: str, avl_insert_fn, bst_insert_fn,
    event_factory, priority_fn, zone_membership_fn
) -> Tuple[Optional[Node], Optional[Node], List[str]]:
    """Rebuilds AVL and BST trees by re-inserting events."""
    errors: List[str] = []
    raw = load_raw(filepath)
    events_data = raw.get("events", [])
    if not events_data:
        return None, None, ["File contains no 'events' list."]

    seen_ids, avl_root, bst_root = set(), None, None
    for ed in events_data:
        eid = ed.get("id")
        if eid in seen_ids:
            return None, None, [f"Duplicate identifier {eid}."]
        seen_ids.add(eid)

        event = event_factory(ed)
        event.in_populated_zone = zone_membership_fn(event)
        event.priority = priority_fn(event)
        node = Node((event.priority, event.magnitude, event.id), event)
        avl_root = avl_insert_fn(avl_root, node)
        bst_root = bst_insert_fn(bst_root, node)

    return avl_root, bst_root, errors


def load_by_topology(
    filepath: str, event_factory, priority_fn,
    zone_membership_fn, stress_mode: bool = False
) -> Tuple[Optional[Node], Dict, List[str]]:
    """Restores tree directly from stored topology without re-inserting."""
    errors: List[str] = []
    raw = load_raw(filepath)
    root = _dict_to_node(raw.get("avl_tree"), event_factory)
    history = raw.get("history", [])
    retired_ids = set(raw.get("retired_ids", []))

    _verify_derived_fields(root, priority_fn, zone_membership_fn, errors)

    active_ids = set()
    _collect_active_ids(root, active_ids)
    errors.extend(_validate_topology(root, seen_ids=set(active_ids)))

    hist_ids = {h["id"] for h in history}
    if active_ids & hist_ids: errors.append("ID collision between active tree and history.")
    if active_ids & retired_ids: errors.append("ID collision between active tree and retired set.")
    if hist_ids & retired_ids: errors.append("ID collision between history and retired set.")

    balance_errors = []
    _check_avl_balance(root, balance_errors)
    if balance_errors and not stress_mode:
        errors.extend(balance_errors)

    if errors:
        return None, {}, errors

    scenario_meta = {
        "execution_mode": raw.get("execution_mode", "normal"),
        "simulation_clock": raw.get("simulation_clock"),
        "parameters": raw.get("parameters", {}),
        "zones": raw.get("zones", []),
        "history": history,
        "retired_ids": retired_ids,
        "report_queue": raw.get("report_queue", []),
        "metrics": raw.get("metrics", {}),
        "stress_flagged": bool(balance_errors),
    }
    return root, scenario_meta, errors


def _verify_derived_fields(
    node: Optional[Node], priority_fn, zone_membership_fn, errors: List[str]
) -> None:
    """Verifies stored vs calculated priority, zones, and keys."""
    if node is None: return
    event = node.getEvent()
    if event.in_populated_zone != zone_membership_fn(event):
        errors.append(f"Zone mismatch at event {event.id}.")
    if event.priority != priority_fn(event):
        errors.append(f"Priority mismatch at event {event.id}.")
    if tuple(node.getKey()) != (event.priority, event.magnitude, event.id):
        errors.append(f"Key mismatch at event {event.id}.")
    _verify_derived_fields(node.getLeft(), priority_fn, zone_membership_fn, errors)
    _verify_derived_fields(node.getRight(), priority_fn, zone_membership_fn, errors)