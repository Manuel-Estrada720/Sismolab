"""Phase C: schema v2, both loading modes, atomic loading, sample files."""

import json
import unittest
from pathlib import Path

from src.models.event_record import ACTIVE
from src.persistence.exporter import (
    ScenarioLoadError,
    load_by_insertions_from_dict,
    load_by_topology_from_dict,
    scenario_to_dict,
)
from tests.helpers import OLD_TIME, STATION, create, inorder_ids, new_observatory

DATA = Path(__file__).resolve().parents[1] / "data"


def tree_shape(state):
    shape = {}
    for node in state.tree.preorder():
        left, right = node.getLeft(), node.getRight()
        shape[node.getEvent().data.event_id] = (
            left.getEvent().data.event_id if left else None,
            right.getEvent().data.event_id if right else None,
        )
    return shape


class SchemaTests(unittest.TestCase):
    def test_json_uses_iso_dates_and_decimal_points(self):
        obs = new_observatory()
        create(obs, 10, "5.2", depth="30", x="12.5", y="900", time="2026-09-07T10:00:00Z")
        document = obs.export()
        event = document["events"][0]
        self.assertEqual(event["magnitude"], 5.2)
        self.assertEqual(event["x"], 12.5)
        self.assertEqual(event["time"], "2026-09-07T10:00:00Z")
        self.assertEqual(document["clock"], "2026-09-07T12:00:00Z")
        self.assertEqual(document["tree"]["nodes"][0]["key"], [2, 5.2, 10])
        self.assertEqual(document["parameters"]["T"], 72)
        self.assertIn("EST-NORTE", document["stations"])
        json.dumps(document)

    def test_version_1_document_still_loads(self):
        v1 = {
            "schema_version": 1, "mode": "NORMAL", "clock_epoch": 2000,
            "parameters": {"W": 48, "R": 40, "L": 3},
            "metrics": {"scenario": {}, "avl": {}},
            "associations": {"2": 1},
            "zones": [{"zone_id": "Z", "populated": True, "x1": 0, "y1": 0, "x2": 500, "y2": 500}],
            "events": [
                {"data": {"event_id": 1, "magnitude10": 50, "depth10": 100, "x10": 100,
                          "y10": 100, "time_epoch": 1000},
                 "revision": 1, "priority": 3, "stations": ["old-station"],
                 "attention": "PENDING", "state": "ACTIVE"},
                {"data": {"event_id": 2, "magnitude10": 40, "depth10": 100, "x10": 120,
                          "y10": 100, "time_epoch": 1500},
                 "revision": 1, "priority": 1, "stations": ["old-station"],
                 "attention": "REVIEWED", "state": "ACTIVE"},
            ],
            "tree": {"root": 1, "nodes": [
                {"event_id": 1, "key": [3, 50, 1], "height": 1, "balance_factor": 1, "left": 2, "right": None},
                {"event_id": 2, "key": [1, 40, 2], "height": 0, "balance_factor": 0, "left": None, "right": None},
            ]},
            "insertion_order": [1, 2],
            "pending_reports": [],
        }
        state = load_by_topology_from_dict(v1)
        self.assertEqual(state.parameters["T"], 72)
        self.assertIn("old-station", state.stations)
        self.assertEqual(state.associations.reference_of(2), 1)
        self.assertEqual(scenario_to_dict(state)["schema_version"], 2)


class TopologyTests(unittest.TestCase):
    def test_normal_round_trip_keeps_exact_topology(self):
        obs = new_observatory()
        for event_id in (50, 30, 70, 20, 40, 60, 80, 35):
            create(obs, event_id, "4.0")
        obs.delete_event(30)                      # topology no longer equals reinsertion
        document = obs.export()
        restored = load_by_topology_from_dict(json.loads(json.dumps(document)))
        self.assertEqual(tree_shape(restored), tree_shape(obs.state))
        self.assertEqual(scenario_to_dict(restored), document)

    def test_stress_round_trip_and_rejection_in_normal_mode(self):
        obs = new_observatory()
        obs.enter_stress()
        for event_id in range(1, 9):
            create(obs, event_id, "3.0")
        document = obs.export()
        restored = load_by_topology_from_dict(document)
        self.assertEqual(restored.mode, "STRESS")
        self.assertEqual(restored.tree.height, 7)
        self.assertEqual(tree_shape(restored), tree_shape(obs.state))
        document["mode"] = "NORMAL"
        with self.assertRaises(ScenarioLoadError) as context:
            load_by_topology_from_dict(document)
        self.assertTrue(any("estrés" in p for p in context.exception.problems))

    def test_inconsistent_files_are_rejected(self):
        obs = new_observatory()
        for event_id in range(1, 6):
            create(obs, event_id, "4.0")
        good = obs.export()

        def broken(change):
            document = json.loads(json.dumps(good))
            change(document)
            with self.assertRaises(ScenarioLoadError):
                load_by_topology_from_dict(document)

        broken(lambda d: d["events"][0].update(priority=3))              # wrong priority
        broken(lambda d: d["tree"]["nodes"][0].update(height=7))         # wrong height
        broken(lambda d: d["tree"].update(root=999))                     # unknown root
        broken(lambda d: d["events"].append(dict(d["events"][0])))       # duplicated id
        broken(lambda d: d["tree"]["nodes"][1].update(left=d["tree"]["root"]))   # cycle
        broken(lambda d: d.update(associations={"2": 999}))              # bad reference
        broken(lambda d: d["events"][0].update(time="2030-01-01T00:00:00Z"))     # after clock
        broken(lambda d: d.update(clock="ayer"))                         # bad date

    def test_failed_load_keeps_current_scenario(self):
        obs = new_observatory()
        create(obs, 1, "5.0")
        before = obs.export()
        with open(DATA / "scenarios" / "invalido_topologia.json", encoding="utf-8") as stream:
            result = obs.load_scenario(stream.read(), "topology")
        self.assertFalse(result["ok"])
        self.assertGreater(len(result["details"]["problems"]), 1)
        self.assertEqual(obs.export(), before)


class InsertionLoadTests(unittest.TestCase):
    def test_simple_file_builds_avl_and_bst_with_same_order(self):
        events = [{"id": i, "magnitude": 3.0, "depth": 5, "x": 900, "y": 900,
                   "time": OLD_TIME} for i in range(1, 16)]
        state, bst = load_by_insertions_from_dict({"events": events})
        self.assertEqual(state.mode, "NORMAL")
        self.assertEqual(state.tree.height, 3)
        self.assertEqual(bst.height(), 14)
        self.assertEqual(state.insertion_order, list(range(1, 16)))
        self.assertEqual([n.getKey() for n in bst.inorder()], [n.getKey() for n in state.tree.inorder()])
        self.assertEqual(state.tree.audit_structure(), [])

    def test_duplicate_id_invalidates_the_file(self):
        events = [{"id": 1, "magnitude": 3.0, "depth": 5, "x": 1, "y": 1, "time": OLD_TIME}] * 2
        with self.assertRaises(ScenarioLoadError):
            load_by_insertions_from_dict({"events": events})

    def test_complete_file_reinserts_in_insertion_order(self):
        obs = new_observatory()
        obs.enter_stress()
        for event_id in range(1, 10):
            create(obs, event_id, "4.0")
        state, bst = load_by_insertions_from_dict(obs.export())
        self.assertEqual(state.mode, "NORMAL")
        self.assertEqual(state.tree.height, 3)
        self.assertEqual(bst.height(), 8)


class SampleFileTests(unittest.TestCase):
    def load(self, name):
        with open(DATA / "scenarios" / name, encoding="utf-8") as stream:
            return json.load(stream)

    def test_valid_samples_load(self):
        for name in ("escenario_normal.json", "escenario_estres.json"):
            state = load_by_topology_from_dict(self.load(name))
            self.assertGreater(state.tree.size, 0)
        self.assertEqual(load_by_topology_from_dict(self.load("escenario_estres.json")).mode, "STRESS")
        for name, size in (("insercion_5.json", 5), ("insercion_30.json", 30), ("insercion_200.json", 200)):
            state, bst = load_by_insertions_from_dict(self.load(name))
            self.assertEqual(state.tree.size, size)
            self.assertEqual(bst.size(), size)

    def test_invalid_samples_are_rejected(self):
        with self.assertRaises(ScenarioLoadError):
            load_by_topology_from_dict(self.load("invalido_topologia.json"))
        with self.assertRaises(ScenarioLoadError):
            load_by_insertions_from_dict(self.load("invalido_insercion.json"))

    def test_burst_sample_produces_every_decision(self):
        obs = new_observatory()
        with open(DATA / "scenarios" / "escenario_normal.json", encoding="utf-8") as stream:
            self.assertTrue(obs.load_scenario(stream.read(), "topology")["ok"])
        with open(DATA / "reports" / "rafaga_escenario_normal.json", encoding="utf-8") as stream:
            burst = json.load(stream)["reports"]
        self.assertTrue(obs.enqueue_reports(burst)["ok"])
        obs.process_all()
        decisions = {entry["decision"] for entry in obs.queue_log}
        for expected in ("CREATED", "CONFIRMED", "CONFLICT", "UPDATED", "OLD", "REJECTED", "REACTIVATED"):
            self.assertIn(expected, decisions)
        self.assertTrue(obs.audit()["ok"])


if __name__ == "__main__":
    unittest.main()
