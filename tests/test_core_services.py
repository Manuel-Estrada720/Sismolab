import unittest

from src.models.event_data import EventData
from src.models.event_record import ACTIVE, ARCHIVED, EventRecord
from src.models.event_registry import EventRegistry
from src.models.report import Report
from src.models.scenario_state import ScenarioState
from src.models.zone import Zone, ZoneMap
from src.persistence.exporter import scenario_to_dict
from src.services.archive_service import ArchiveService
from src.services.association_service import AssociationService
from src.services.observatory import Observatory
from src.services.report_processor import CREATED, INVALID, ReportProcessor
from src.structures.Avl import AVLTree
from src.structures.Bst import BSTTree


class CoreServiceTests(unittest.TestCase):

    """
           
     Runs before every test. 
     It sets up a basic scenario state and a report processor so we have a fresh environment ready to use.
    """
    def setUp(self):
        
        self.state = ScenarioState(
            zones=ZoneMap([Zone("town", True, 0, 0, 10000, 10000)]),
            clock_epoch=1_000_000,
            stations=["STA-01", "STA-02"],
        )
        self.processor = ReportProcessor(
            self.state.registry, self.state.tree, self.state.zones,
            self.state, self.state.associations,
        )

    """  
    Helper method to quickly create a standard report object for testing purposes.
    """

    def make_report(self, event_id=1, magnitude=45, when=999_000, station="STA-01"):
        
        data = EventData(event_id, magnitude, 200, 1000, 1000, when)
        return Report(data, 1, station)

    """
    Tests that processing a valid report successfully creates an event and stores it in the tree.
"""

    def test_report_creation_uses_key_and_event_tree_arguments(self):
        
        result, _ = self.processor.process(self.make_report())
        self.assertEqual(result, CREATED)
        self.assertEqual(self.state.tree.inorder()[0].getEvent().data.event_id, 1)

    """
    Tests that reports coming from the future (ahead of the scenario clock) are rejected as invalid.
    """
    def test_report_processor_reads_live_scenario_clock(self):
        
        self.state.clock_epoch = 100
        result, _ = self.processor.process(self.make_report(when=101))
        self.assertEqual(result, INVALID)
    """
    Tests that reports coming from an unknown station (not registered in the scenario) are rejected.
    """


    """
    Tests that reports coming from an unknown station (not registered in the scenario) are rejected.
    """
    def test_report_rejects_station_not_in_scenario_list(self):
       
        result, _ = self.processor.process(self.make_report(station="UNKNOWN"))
        self.assertEqual(result, INVALID)
        self.assertIsNone(self.state.registry.get(1))

        """
        Tests AVL tree balance under stress (many insertions). 
        It checks that balancing rotations fix the tree without losing or altering record data.
        """
    def test_stress_recovery_keeps_order_and_record_identity(self):
        
        tree = AVLTree(stress_mode=True)
        records = []
        for event_id in range(1, 201):
            record = EventRecord(EventData(event_id, 40, 10, 1, 1, 1), 1, 1, "STA-01")
            records.append(record)
            tree.insert(record.key(), record)
        before = {node.getEvent().data.event_id: node.getEvent() for node in tree.inorder()}
        self.assertGreater(tree.height, 2)
        rotations = tree.restore_avl_balance()
        self.assertGreater(rotations, 0)
        self.assertEqual(tree.audit_structure(), [])
        after = {node.getEvent().data.event_id: node.getEvent() for node in tree.inorder()}
        self.assertEqual(before, after)
        self.assertLessEqual(tree.height, 8)


        """
            Tests Binary Search Tree (BST) behavior:
            - Prevents duplicate keys by raising an error.
            - Counts visited nodes correctly during a search.
            - Keeps track of tree size, height, and leaves.
            """
    def test_bst_duplicate_raises_and_search_counts_nodes(self):
       
        tree = BSTTree()
        tree.insert((1, 40, 1), object())
        tree.insert((1, 40, 2), object())
        with self.assertRaises(ValueError):
            tree.insert((1, 40, 1), object())
        node, visited = tree.search((1, 40, 2))
        self.assertIsNotNone(node)
        self.assertEqual(visited, 2)
        self.assertEqual(tree.size, 2)
        self.assertEqual(tree.height, 1)
        self.assertEqual(tree.count_leaves(), 1)

        """
        Tests the archiving service: 
        It identifies old and low-priority events, archives them successfully, and removes them from the active tree.
        """
    
    def test_archive_selects_low_old_branch_and_leaves_history(self):
        
        old_time = self.state.clock_epoch - (73 * 3600)
        for event_id in (1, 2, 3):
            record = EventRecord(EventData(event_id, 30, 10, 1, 1, old_time), 1, 1, "STA-01")
            self.state.registry.add(record)
            self.state.tree.insert(record.key(), record)
        service = ArchiveService(self.state, self.state.associations)
        preview = service.preview()
        self.assertEqual(preview["count"], 3)
        ok, _, _ = service.archive(preview)
        self.assertTrue(ok)
        self.assertEqual(self.state.tree.size, 0)
        self.assertEqual(self.state.registry.count_by_state(ARCHIVED), 3)


    """
        Tests the 'undo' functionality in the observatory:
        Creates events, saves the state, adds one more event, and then undoes the action 
        to verify that the tree returns to its exact previous state.
        """    

    def test_undo_restores_exact_tree_topology_after_create(self):
        
        observatory = Observatory(self.state)
        for event_id in (10, 20):
            data = EventData(event_id, 45, 200, 1000, 1000, self.state.clock_epoch - 1)
            observatory.create_event({"event_id": event_id, "magnitude10": data.magnitude10,
                                     "depth10": data.depth10, "x10": data.x10, "y10": data.y10,
                                     "time_epoch": data.time_epoch, "station": "STA-01"})
        expected = scenario_to_dict(observatory.state)["tree"]
        data = EventData(30, 45, 200, 1000, 1000, self.state.clock_epoch - 1)
        observatory.create_event({"event_id": 30, "magnitude10": data.magnitude10,
                                "depth10": data.depth10, "x10": data.x10, "y10": data.y10,
                                "time_epoch": data.time_epoch, "station": "STA-01"})
        observatory.undo()
        self.assertEqual(observatory.export()["tree"], expected)


if __name__ == "__main__":
    unittest.main()