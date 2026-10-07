"""Regression tests for the bugs found in the original code (phase A)."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.models.event_data import EventData
from src.models.report import Report
from src.models.scenario_state import DEFAULT_STATIONS, ScenarioState
from src.persistence.exporter import load_by_topology, scenario_to_dict
from src.services.report_processor import (
    CREATED,
    INVALID,
    OLD,
    CONFLICT,
    ReportProcessor,
)
from src.structures.Avl import AVLTree
from src.structures.Bst import BSTTree
from src.structures.comparator import compare_keys


def event(event_id, magnitude10=50, time_epoch=100, depth10=100, x10=100, y10=100):
    return EventData(event_id, magnitude10, depth10, x10, y10, time_epoch)


class ComparatorTests(unittest.TestCase):
    def test_examples_of_section_5(self):
        node_key = (3, 52, 10)
        self.assertEqual(compare_keys((2, 58, 20), node_key), -1)   # left
        self.assertEqual(compare_keys((3, 61, 30), node_key), 1)    # right
        self.assertEqual(compare_keys((3, 52, 5), node_key), -1)    # left
        self.assertEqual(compare_keys((3, 52, 25), node_key), 1)    # right
        self.assertEqual(compare_keys(node_key, node_key), 0)

    def test_avl_and_bst_use_the_same_order(self):
        keys = [(2, 58, 20), (3, 61, 30), (3, 52, 5), (3, 52, 25), (3, 52, 10)]
        avl, bst = AVLTree(), BSTTree()
        for key in keys:
            avl.insert(key, None)
            bst.insert(key, None)
        expected = sorted(keys)
        self.assertEqual([n.getKey() for n in avl.inorder()], expected)
        self.assertEqual([n.getKey() for n in bst.inorder()], expected)


class BSTTests(unittest.TestCase):
    def build(self, keys):
        tree = BSTTree()
        for key in keys:
            tree.insert((1, key, key), None)
        return tree

    def keys(self, nodes):
        return [node.getKey()[2] for node in nodes]

    def test_traversals_return_lists_and_do_not_print(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            tree = self.build([50, 30, 70, 20, 40])
            # Keys are read now: deleting with two children copies keys between nodes
            inorder = self.keys(tree.inorder())
            preorder = self.keys(tree.preorder())
            postorder = self.keys(tree.postorder())
            levels = self.keys(tree.breadth_first())
            tree.delete((1, 30, 30))
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(inorder, [20, 30, 40, 50, 70])
        self.assertEqual(preorder, [50, 30, 20, 40, 70])
        self.assertEqual(postorder, [20, 40, 30, 70, 50])
        self.assertEqual(levels, [50, 30, 70, 20, 40])

    def test_duplicate_key_raises(self):
        tree = self.build([5])
        with self.assertRaises(ValueError):
            tree.insert((1, 5, 5), None)
        self.assertEqual(tree.size(), 1)

    def test_size_height_leaves_depth(self):
        tree = self.build([50, 30, 70, 20, 40, 35])
        self.assertEqual(tree.size(), 6)
        self.assertEqual(tree.height(), 3)
        self.assertEqual(tree.max_depth(), 3)
        self.assertEqual(tree.count_leaves(), 3)          # 20, 35, 70
        self.assertEqual(BSTTree().height(), -1)
        self.assertEqual(BSTTree().count_leaves(), 0)

    def test_search_returns_node_and_visited(self):
        tree = self.build([50, 30, 70, 20, 40])
        node, visited = tree.search((1, 40, 40))
        self.assertEqual(node.getKey(), (1, 40, 40))
        self.assertEqual(visited, 3)
        node, visited = tree.search((1, 99, 99))
        self.assertIsNone(node)
        self.assertEqual(visited, 2)

    def test_delete_with_deep_predecessor(self):
        # This case crashed before: the predecessor (45) is not a direct child of 50
        tree = self.build([50, 30, 70, 20, 40, 35, 45, 60, 80])
        removed = tree.delete((1, 50, 50))
        self.assertEqual(removed.getKey(), (1, 50, 50))
        self.assertEqual(tree.root.getKey(), (1, 45, 45))
        self.assertEqual(self.keys(tree.inorder()), [20, 30, 35, 40, 45, 60, 70, 80])
        self.assertEqual(tree.size(), 8)
        self.assertIsNone(tree.delete((1, 99, 99)))

    def test_delete_every_node(self):
        keys = [50, 30, 70, 20, 40, 35, 45, 60, 80, 10]
        tree = self.build(keys)
        for key in keys:
            tree.delete((1, key, key))
        self.assertIsNone(tree.root)
        self.assertEqual(tree.size(), 0)

    def test_ascending_insertion_does_not_hit_recursion_limit(self):
        tree = self.build(range(1, 1500))
        self.assertEqual(tree.height(), 1498)
        self.assertEqual(len(tree.inorder()), 1499)


class ReportProcessorTests(unittest.TestCase):
    def test_create_inserts_in_avl(self):
        state = ScenarioState(clock_epoch=1000)
        processor = ReportProcessor(state)
        result, _ = processor.process(Report(event(1), 1, DEFAULT_STATIONS[0]))
        self.assertEqual(result, CREATED)
        node, _ = state.tree.search(state.registry.get(1).key())
        self.assertIs(node.getEvent(), state.registry.get(1))
        self.assertEqual(state.insertion_order, [1])

    def test_processor_reads_the_current_clock(self):
        state = ScenarioState(clock_epoch=1000)
        processor = ReportProcessor(state)
        future = Report(event(2, time_epoch=5000), 1, DEFAULT_STATIONS[0])
        self.assertEqual(processor.process(future)[0], INVALID)
        self.assertIsNone(state.registry.get(2))
        state.clock_epoch = 6000                     # the user advances the clock
        self.assertEqual(processor.process(future)[0], CREATED)

    def test_unknown_station_is_rejected(self):
        state = ScenarioState(clock_epoch=1000)
        result, message = ReportProcessor(state).process(Report(event(3), 1, "NOPE"))
        self.assertEqual(result, INVALID)
        self.assertIn("NOPE", message)
        self.assertIsNone(state.registry.get(3))

    def test_metrics_live_in_scenario_state(self):
        state = ScenarioState(clock_epoch=1000)
        processor = ReportProcessor(state)
        station = DEFAULT_STATIONS[0]
        processor.process(Report(event(1), 2, station))
        processor.process(Report(event(1, magnitude10=60), 3, station))   # correction
        processor.process(Report(event(1), 1, station))                   # old
        processor.process(Report(event(1, magnitude10=61), 3, station))   # conflict
        self.assertEqual(state.metrics["corrections"], 1)
        self.assertEqual(state.metrics["discarded"], 1)
        self.assertEqual(state.metrics["conflicts"], 1)
        self.assertFalse(hasattr(processor, "counters"))

    def test_rejected_reports_do_not_change_the_event(self):
        state = ScenarioState(clock_epoch=1000)
        processor = ReportProcessor(state)
        processor.process(Report(event(1), 2, DEFAULT_STATIONS[0]))
        before = scenario_to_dict(state)["tree"]
        self.assertEqual(processor.process(Report(event(1, 70), 1, DEFAULT_STATIONS[1]))[0], OLD)
        self.assertEqual(processor.process(Report(event(1, 70), 2, DEFAULT_STATIONS[1]))[0], CONFLICT)
        self.assertEqual(scenario_to_dict(state)["tree"], before)


class ScenarioParameterTests(unittest.TestCase):
    def test_defaults(self):
        state = ScenarioState()
        self.assertEqual(state.parameters["T"], 72)
        self.assertEqual(state.t10, 720)
        self.assertEqual(state.stations, DEFAULT_STATIONS)

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            ScenarioState(parameters={"W": 48, "R": 40, "L": 3, "T": 0})
        with self.assertRaises(ValueError):
            ScenarioState(stations=["A", "A"])

    def test_old_file_without_t_and_stations_loads(self):
        state = ScenarioState(clock_epoch=1000)
        ReportProcessor(state).process(Report(event(1), 1, DEFAULT_STATIONS[0]))
        document = scenario_to_dict(state)
        del document["parameters"]["T"]
        del document["stations"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            restored = load_by_topology(path)
        self.assertEqual(restored.parameters["T"], 72)
        self.assertIn(DEFAULT_STATIONS[0], restored.stations)


class AVLRecoveryTests(unittest.TestCase):
    def test_recovery_of_degenerate_tree(self):
        tree = AVLTree(stress_mode=True)
        for key in range(1, 201):
            tree.insert((1, key, key), key)
        self.assertEqual(tree.height, 199)
        tree.restore_avl_balance()
        self.assertFalse(tree.stress_mode)
        self.assertEqual(tree.audit_structure(), [])
        self.assertEqual([n.getEvent() for n in tree.inorder()], list(range(1, 201)))


if __name__ == "__main__":
    unittest.main()
