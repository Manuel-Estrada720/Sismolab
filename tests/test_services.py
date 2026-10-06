"""Phase B: undo, queue, stress, archive, queries, audit, comparison, versions."""

import random
import unittest

from src.models.event_record import ACTIVE, ARCHIVED, DELETED
from src.persistence.exporter import scenario_to_dict
from src.services.observatory import Observatory

from tests.helpers import (
    OLD_TIME,
    RECENT_TIME,
    STATION,
    create,
    event_form,
    inorder_ids,
    new_observatory,
    report_form,
    root_id,
)


class UndoTests(unittest.TestCase):
    def test_every_action_is_undone_exactly(self):
        obs = new_observatory()
        create(obs, 10, "5.0")
        create(obs, 20, "3.0")
        actions = [
            lambda: obs.create_event(event_form(30, "6.1")),
            lambda: obs.correct_event(20, {"magnitude": "6.4", "station": STATION}),
            lambda: obs.mark_reviewed(10),
            lambda: obs.delete_event(10),
            lambda: obs.advance_clock(hours="5"),
            lambda: obs.set_parameters({"W": "2", "L": "0", "T": "10"}),
            lambda: obs.enter_stress(),
            lambda: obs.enqueue_reports([report_form(40, "4.0", 1)]),
            lambda: obs.process_step(),
            lambda: obs.recover(),
        ]
        for action in actions:
            before = scenario_to_dict(obs.state)
            result = action()
            self.assertTrue(result["ok"], result["message"])
            self.assertNotEqual(scenario_to_dict(obs.state), before)
            self.assertTrue(obs.undo()["ok"])
            self.assertEqual(scenario_to_dict(obs.state), before)
            action()            # do it again to continue the sequence

    def test_successive_undos(self):
        obs = new_observatory()
        states = [scenario_to_dict(obs.state)]
        for event_id in range(1, 8):
            create(obs, event_id, "4.0")
            states.append(scenario_to_dict(obs.state))
        for expected in reversed(states[:-1]):
            obs.undo()
            self.assertEqual(scenario_to_dict(obs.state), expected)
        self.assertFalse(obs.undo()["ok"])

    def test_snapshots_are_independent(self):
        obs = new_observatory()
        create(obs, 1, "4.0")
        snapshot = obs.undo_service.stack.peek()["snapshot"]
        copy = repr(snapshot)
        obs.correct_event(1, {"magnitude": "6.0", "station": STATION})
        self.assertEqual(repr(snapshot), copy)


class InvalidActionTests(unittest.TestCase):
    def test_invalid_actions_do_not_change_anything(self):
        obs = new_observatory()
        create(obs, 1, "5.0")
        obs.delete_event(1)
        create(obs, 2, "5.0")
        before = scenario_to_dict(obs.state)
        undo_size = obs.undo_service.size()
        attempts = [
            obs.create_event(event_form(2, "4.0")),                       # active id
            obs.create_event(event_form(1, "4.0")),                       # deleted id
            obs.create_event(event_form(3, "10.1")),                      # magnitude
            obs.create_event(event_form(3, "4.0", depth="700.1")),        # depth
            obs.create_event(event_form(3, "4.0", x="1000.1")),           # coordinate
            obs.create_event(event_form(3, "4.0", time="2030-01-01T00:00:00Z")),  # after clock
            obs.create_event(event_form(3, "4.0", station="NOPE")),      # station
            obs.create_event(event_form(3, "4.25")),                      # two decimals
            obs.correct_event(1, {"magnitude": "6", "station": STATION}),  # deleted event
            obs.correct_event(2, {"magnitude": "abc", "station": STATION}),
            obs.delete_event(99),
            obs.mark_reviewed(99),
            obs.recover(),                                                # normal mode
            obs.advance_clock(hours="-1"),
            obs.set_parameters({"W": "0"}),
            obs.set_parameters({"L": "-2"}),
            obs.enqueue_reports([report_form(5, "4.0", 1), report_form(6, "4.0", 1, station="X")]),
            obs.process_step(),                                           # empty queue
            obs.archive_apply(),                                          # nothing eligible
            obs.load_scenario("{not json", "topology"),
            obs.restore_version("does not exist"),
        ]
        for result in attempts:
            self.assertFalse(result["ok"], result["message"])
        self.assertEqual(scenario_to_dict(obs.state), before)
        self.assertEqual(obs.undo_service.size(), undo_size)


class QueueTests(unittest.TestCase):
    def test_fifo_decisions_and_undo_restores_position(self):
        obs = new_observatory()
        create(obs, 1, "5.0")
        burst = [
            report_form(2, "4.0", 1),                          # new
            report_form(1, "5.0", 1, station="EST-SUR"),        # confirmation
            report_form(1, "4.0", 1, station="EST-ESTE"),       # conflict
            report_form(1, "6.5", 3),                           # correction, key changes
            report_form(1, "5.0", 2),                           # old
        ]
        self.assertTrue(obs.enqueue_reports(burst)["ok"])
        self.assertEqual([r.data.event_id for r in obs.state.pending_reports.to_list()], [2, 1, 1, 1, 1])
        decisions = []
        for _ in range(5):
            decisions.append(obs.process_step()["details"]["decision"])
        self.assertEqual(decisions, ["CREATED", "CONFIRMED", "CONFLICT", "UPDATED", "OLD"])
        record = obs.state.registry.get(1)
        self.assertEqual(record.revision, 3)
        self.assertEqual(record.data.magnitude10, 65)
        self.assertEqual(obs.state.metrics["conflicts"], 1)
        self.assertEqual(obs.state.metrics["discarded"], 1)
        # Undo the discarded report: it goes back to the front of the queue
        obs.undo()
        queue = obs.state.pending_reports.to_list()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0].revision, 2)
        self.assertEqual(obs.state.metrics["discarded"], 0)

    def test_confirmation_does_not_duplicate_stations(self):
        obs = new_observatory()
        create(obs, 1, "5.0")
        obs.enqueue_reports([report_form(1, "5.0", 1, station="EST-SUR")] * 2)
        obs.process_all()
        self.assertEqual(obs.state.registry.get(1).stations, [STATION, "EST-SUR"])
        self.assertEqual(obs.state.tree.size, 1)


class StressTests(unittest.TestCase):
    def test_stress_defers_rotations_and_recovery_preserves_everything(self):
        obs = new_observatory()
        obs.enter_stress()
        for event_id in range(1, 31):
            create(obs, event_id, "4.0", x=str(500 + event_id), y="500",
                   time="2026-09-0" + str(1 + event_id % 6) + "T00:00:00Z")
        self.assertEqual(obs.state.tree.height, 29)            # degenerate: no rotations
        audit = obs.audit()["details"]
        self.assertTrue(audit["ok"])
        self.assertFalse(audit["balanced"])
        self.assertGreater(len(audit["expected"]), 0)
        records = {node.getEvent().data.event_id: node.getEvent() for node in obs.state.tree.inorder()}
        order = inorder_ids(obs)
        references = dict(obs.state.associations.references)
        result = obs.recover()
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(obs.state.mode, "NORMAL")
        self.assertEqual(inorder_ids(obs), order)
        self.assertEqual(obs.state.associations.references, references)
        for node in obs.state.tree.inorder():
            self.assertIs(node.getEvent(), obs.state.registry.get(node.getEvent().data.event_id))
            self.assertEqual(node.getKey(), records[node.getEvent().data.event_id].key())
        self.assertTrue(obs.audit()["details"]["balanced"])
        self.assertLessEqual(obs.state.tree.height, 6)


class ArchiveTests(unittest.TestCase):
    def build(self, ids, young=()):
        obs = new_observatory()
        for event_id in ids:
            time = RECENT_TIME if event_id in young else OLD_TIME
            create(obs, event_id, "3.0", time=time)
        return obs

    def test_whole_tree_is_eligible(self):
        obs = self.build(range(1, 8))
        preview = obs.archive_preview()["details"]
        self.assertEqual(preview["count"], 7)
        self.assertEqual(preview["root"], 4)

    def test_tie_by_root_id(self):
        obs = self.build(range(1, 8), young={4})
        preview = obs.archive_preview()["details"]
        self.assertEqual((preview["root"], preview["count"]), (6, 3))

    def test_tie_by_depth_beats_id(self):
        obs = self.build([5, 4, 3, 2, 1], young={4, 2, 3})
        # Shape: 4 -> (2 -> 1, 3), 5. Eligible leaves: 1 (depth 2) and 5 (depth 1)
        preview = obs.archive_preview()["details"]
        self.assertEqual(preview["root"], 1)

    def test_low_root_with_high_descendant_is_not_eligible(self):
        obs = new_observatory()
        create(obs, 1, "3.0", time=OLD_TIME)
        create(obs, 2, "3.0", time=OLD_TIME)
        create(obs, 3, "6.5", time=OLD_TIME)             # high priority
        self.assertEqual(root_id(obs), 2)
        result = obs.archive_preview()
        self.assertEqual(result["details"]["root"], 1)
        self.assertIn(2, [item["root"] for item in result["details"]["blocked"]])

    def test_age_must_be_strictly_greater_than_t(self):
        obs = self.build([1], young={1})
        obs.set_parameters({"T": "2"})                    # event is exactly 2 h old
        self.assertFalse(obs.archive_preview()["ok"])
        obs.advance_clock(hours="0.1")
        self.assertTrue(obs.archive_preview()["ok"])

    def test_apply_keeps_identity_and_undo_restores(self):
        obs = self.build(range(1, 8), young={4})
        before = scenario_to_dict(obs.state)
        record = obs.state.registry.get(6)
        result = obs.archive_apply([5, 6, 7])
        self.assertTrue(result["ok"], result["message"])
        self.assertIs(obs.state.registry.get(6), record)
        self.assertEqual(record.state, ARCHIVED)
        self.assertEqual(obs.state.tree.size, 4)
        self.assertEqual(obs.audit()["details"]["errors"], [])
        self.assertEqual(obs.state.metrics["archive_operations"], 1)
        self.assertEqual(obs.state.metrics["archived_events"], 3)
        obs.undo()
        self.assertEqual(scenario_to_dict(obs.state), before)

    def test_stale_preview_is_rejected(self):
        obs = self.build(range(1, 8), young={4})
        self.assertFalse(obs.archive_apply([1, 2, 3])["ok"])


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.obs = new_observatory()
        rng = random.Random(7)
        for event_id in range(1, 81):
            create(self.obs, event_id, str(rng.randint(-20, 90) / 10),
                   depth=str(rng.randint(0, 900) / 10), x=str(rng.randint(0, 10000) / 10),
                   y=str(rng.randint(0, 10000) / 10),
                   time="2026-09-0" + str(rng.randint(1, 7)) + "T0" + str(rng.randint(0, 9)) + ":00:00Z")
        for event_id in range(1, 81, 3):
            self.obs.mark_reviewed(event_id)
        self.records = [n.getEvent() for n in self.obs.state.tree.inorder()]

    def test_pending_top_k(self):
        result = self.obs.query("pending", {"k": "5"})["details"]
        expected = [r.data.event_id for r in reversed(self.records) if r.attention == "PENDING"][:5]
        self.assertEqual([item["id"] for item in result["results"]], expected)
        self.assertLess(result["examined"], len(self.records))
        everything = self.obs.query("pending", {"k": "500"})["details"]
        self.assertEqual(len(everything["results"]), sum(r.attention == "PENDING" for r in self.records))

    def test_magnitude_range_matches_brute_force_and_prunes(self):
        for low, high in [("4.5", "5.9"), ("-2", "10"), ("6", "6"), ("0", "1.2")]:
            result = self.obs.query("magnitude", {"min": low, "max": high})["details"]
            expected = sorted(r.data.event_id for r in self.records
                              if float(low) * 10 <= r.data.magnitude10 <= float(high) * 10)
            self.assertEqual(sorted(item["id"] for item in result["results"]), expected)
            self.assertLessEqual(result["examined"], len(self.records))
        narrow = self.obs.query("magnitude", {"min": "0", "max": "1.2"})["details"]
        self.assertLess(narrow["examined"], len(self.records))

    def test_depth_and_dates_examines_all_nodes(self):
        result = self.obs.query("depth-dates", {"max_depth": "30", "from": "2026-09-02T00:00:00Z",
                                                "to": "2026-09-05T23:59:59Z"})["details"]
        self.assertEqual(result["examined"], len(self.records))
        for item in result["results"]:
            self.assertLessEqual(item["depth"], 30)

    def test_costly_events(self):
        self.obs.set_parameters({"L": "2"})
        result = self.obs.query("costly", {})["details"]
        positions = {}
        for node in self.obs.state.tree.inorder():
            found, visited = self.obs.state.tree.search(node.getKey())
            positions[node.getEvent().data.event_id] = visited - 1
        expected = sorted(r.data.event_id for r in self.records
                          if r.priority == 3 and positions[r.data.event_id] > 2)
        self.assertEqual(sorted(item["id"] for item in result["results"]), expected)
        for item in result["results"]:
            self.assertEqual(item["search_cost"], item["node_depth"] + 1)

    def test_search_by_id_reports_state(self):
        self.obs.delete_event(5)
        self.assertIn("eliminado", self.obs.get_event(5)["message"])
        result = self.obs.get_event(6)
        self.assertEqual(result["details"]["examined"], result["details"]["node_depth"] + 1)
        self.assertFalse(self.obs.get_event(999)["ok"])


class AuditTests(unittest.TestCase):
    def test_audit_detects_each_inconsistent_event(self):
        obs = new_observatory()
        for event_id in range(1, 8):
            create(obs, event_id, "4.0")
        self.assertTrue(obs.audit()["ok"])
        root = obs.state.tree.root
        root.getLeft().setHeight(9)                                  # wrong height
        root.getRight().getRight().setKey((1, 40, 1))                # breaks global order
        report = obs.audit()["details"]
        self.assertFalse(report["ok"])
        kinds = {(issue["event_id"], issue["type"]) for issue in report["errors"]}
        self.assertIn((2, "altura"), kinds)
        self.assertIn((7, "orden"), kinds)


class ComparisonTests(unittest.TestCase):
    def test_ascending_order_degenerates_bst_only(self):
        obs = new_observatory()
        for event_id in range(1, 33):
            create(obs, event_id, "3.0")
        rows = {row["order"]: row for row in obs.compare()["details"]["rows"]}
        self.assertEqual(rows["ascending"]["bst"]["height"], 31)
        self.assertEqual(rows["ascending"]["avl"]["height"], 5)
        self.assertEqual(rows["ascending"]["bst"]["total_comparisons"], sum(range(1, 33)))
        self.assertEqual(rows["random"]["size"], 32)


class ParameterTests(unittest.TestCase):
    def test_changing_w_and_r_recomputes_associations(self):
        obs = new_observatory()
        create(obs, 1, "6.0", x="500", y="500", time="2026-09-05T00:00:00Z")
        create(obs, 2, "4.0", x="530", y="500", time="2026-09-07T00:00:00Z")
        self.assertEqual(obs.state.associations.reference_of(2), 1)      # 48 h, 30 km
        obs.set_parameters({"W": "47.9"})
        self.assertIsNone(obs.state.associations.reference_of(2))
        obs.set_parameters({"W": "48", "R": "29.9"})
        self.assertIsNone(obs.state.associations.reference_of(2))
        obs.set_parameters({"R": "30"})
        self.assertEqual(obs.state.associations.reference_of(2), 1)


class VersionTests(unittest.TestCase):
    def test_version_survives_a_new_instance_and_restore_is_undoable(self):
        obs = new_observatory()
        create(obs, 1, "5.0")
        create(obs, 2, "6.0")
        saved = scenario_to_dict(obs.state)
        self.assertTrue(obs.save_version("antes")["ok"])
        directory = obs.versions.directory

        fresh = Observatory(versions_dir=directory)        # like restarting the program
        self.assertEqual([v["name"] for v in fresh.list_versions()["details"]["versions"]], ["antes"])
        empty = scenario_to_dict(fresh.state)
        self.assertTrue(fresh.restore_version("antes")["ok"])
        self.assertEqual(scenario_to_dict(fresh.state), saved)
        fresh.undo()
        self.assertEqual(scenario_to_dict(fresh.state), empty)


if __name__ == "__main__":
    unittest.main()
