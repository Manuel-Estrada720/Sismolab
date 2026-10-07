import tempfile
import unittest

from src.models.event_data import EventData
from src.models.event_record import ARCHIVED, EventRecord
from src.models.report import Report
from src.models.scenario_state import ScenarioState
from src.models.units import format_utc
from src.models.zone import Zone, ZoneMap
from src.persistence.exporter import scenario_to_dict
from src.services.archive_service import ArchiveService
from src.services.observatory import Observatory
from src.services.report_processor import CREATED, INVALID, ReportProcessor
from src.structures.Avl import AVLTree
from src.structures.Bst import BSTTree


class CoreServiceTests(unittest.TestCase):

    def setUp(self):
        """Runs before every test: a small scenario and a report processor."""
        self.state = ScenarioState(
            zones=ZoneMap([Zone("town", True, 0, 0, 10000, 10000)]),
            clock_epoch=1_000_000,
            stations=["STA-01", "STA-02"],
        )
        self.processor = ReportProcessor(self.state)

    def make_report(self, event_id=1, magnitude=45, when=999_000, station="STA-01"):
        """Helper: a standard report with revision 1."""
        data = EventData(event_id, magnitude, 200, 1000, 1000, when)
        return Report(data, 1, station)

    def test_report_creation_uses_key_and_event_tree_arguments(self):
        """A valid report creates the event and stores it in the AVL tree."""
        result, _ = self.processor.process(self.make_report())
        self.assertEqual(result, CREATED)
        self.assertEqual(self.state.tree.inorder()[0].getEvent().data.event_id, 1)

    def test_report_processor_reads_live_scenario_clock(self):
        """A report that happens after the scenario clock is rejected as invalid."""
        self.state.clock_epoch = 100
        result, _ = self.processor.process(self.make_report(when=101))
        self.assertEqual(result, INVALID)

    def test_report_rejects_station_not_in_scenario_list(self):
        """A report from an unknown station is rejected and nothing is created."""
        result, _ = self.processor.process(self.make_report(station="UNKNOWN"))
        self.assertEqual(result, INVALID)
        self.assertIsNone(self.state.registry.get(1))

    def test_stress_recovery_keeps_order_and_record_identity(self):
        """In stress mode the tree grows tall; the recovery balances it without losing records."""
        tree = AVLTree(stress_mode=True)
        for event_id in range(1, 201):
            record = EventRecord(EventData(event_id, 40, 10, 1, 1, 1), 1, 1, "STA-01")
            tree.insert(record.key(), record)
        before = {node.getEvent().data.event_id: node.getEvent() for node in tree.inorder()}
        self.assertGreater(tree.height, 2)
        rotations = tree.restore_avl_balance()
        self.assertGreater(rotations, 0)
        self.assertEqual(tree.audit_structure(), [])
        after = {node.getEvent().data.event_id: node.getEvent() for node in tree.inorder()}
        self.assertEqual(before, after)
        self.assertLessEqual(tree.height, 8)

    def test_bst_duplicate_raises_and_search_counts_nodes(self):
        """The BST rejects duplicate keys, counts visited nodes and reports size, height and leaves."""
        tree = BSTTree()
        tree.insert((1, 40, 1), object())
        tree.insert((1, 40, 2), object())
        with self.assertRaises(ValueError):
            tree.insert((1, 40, 1), object())
        node, visited = tree.search((1, 40, 2))
        self.assertIsNotNone(node)
        self.assertEqual(visited, 2)
        self.assertEqual(tree.size(), 2)
        self.assertEqual(tree.height(), 1)
        self.assertEqual(tree.count_leaves(), 1)

    def test_archive_selects_low_old_branch_and_leaves_history(self):
        """Old low-priority events are archived: they leave the AVL but stay in the history."""
        old_time = self.state.clock_epoch - (73 * 3600)
        for event_id in (1, 2, 3):
            record = EventRecord(EventData(event_id, 30, 10, 1, 1, old_time), 1, 1, "STA-01")
            self.state.registry.add(record)
            self.state.tree.insert(record.key(), record)
        service = ArchiveService(self.state)
        preview = service.select()
        self.assertEqual(preview["count"], 3)
        service.apply(preview["ids"])
        self.assertEqual(self.state.tree.size, 0)
        self.assertEqual(self.state.registry.count_by_state(ARCHIVED), 3)

    def test_undo_restores_exact_tree_topology_after_create(self):
        """After undo, the tree has exactly the same topology as before the last action."""
        observatory = Observatory(self.state, versions_dir=tempfile.mkdtemp())
        when = format_utc(self.state.clock_epoch - 1)
        for event_id in (10, 20):
            observatory.create_event({"id": event_id, "magnitude": "4.5", "depth": "20", "x": "100",
                                      "y": "100", "time": when, "station": "STA-01"})
        expected = scenario_to_dict(observatory.state)["tree"]
        observatory.create_event({"id": 30, "magnitude": "4.5", "depth": "20", "x": "100",
                                  "y": "100", "time": when, "station": "STA-01"})
        observatory.undo()
        self.assertEqual(observatory.export()["tree"], expected)


if __name__ == "__main__":
    unittest.main()
