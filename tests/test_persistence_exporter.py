import json
import tempfile
import unittest
from pathlib import Path

from src.models.event_data import EventData
from src.models.event_record import ACTIVE, ARCHIVED, DELETED, EventRecord
from src.models.report import Report
from src.models.scenario_state import DEFAULT_STATIONS, ScenarioState
from src.persistence.exporter import (
    export_to_file,
    load_by_insertions,
    load_by_topology,
    scenario_to_dict,
)
from src.services.priority import calculate_priority


class ScenarioPersistenceTests(unittest.TestCase):
    def create_scenario(self):
        state = ScenarioState(clock_epoch=2000)

        def add_event(event_id, magnitude10, time_epoch, lifecycle=ACTIVE):
            data = EventData(event_id, magnitude10, 100, 100, 100, time_epoch)
            record = EventRecord(
                data,
                1,
                calculate_priority(data, state.zones),
                DEFAULT_STATIONS[event_id % len(DEFAULT_STATIONS)],
            )
            record.state = lifecycle
            state.registry.add(record)
            if lifecycle == ACTIVE:
                state.tree.insert(record.key(), record)
            if lifecycle != DELETED:
                state.associations.on_event_changed(event_id)
            return record

        add_event(1, 50, 1000)
        add_event(2, 60, 1100)
        add_event(3, 40, 1200)
        add_event(4, 55, 900, ARCHIVED)
        add_event(5, 70, 900, DELETED)
        state.pending_reports.enqueue(
            Report(EventData(6, 45, 200, 150, 150, 1300), 1, DEFAULT_STATIONS[0])
        )
        state.metrics["accepted"] = 3
        return state

    def test_empty_scenario_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "empty.json"
            export_to_file(filepath, ScenarioState())
            restored = load_by_topology(filepath)

        self.assertIsNone(restored.tree.root)
        self.assertEqual(restored.registry.records, {})
        self.assertEqual(restored.associations.references, {})
        self.assertEqual(restored.tree.audit_structure(), [])

    def test_topology_round_trip_preserves_scenario_state(self):
        state = self.create_scenario()
        expected = scenario_to_dict(state)

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "scenario.json"
            export_to_file(filepath, state)
            restored = load_by_topology(filepath)

        actual = scenario_to_dict(restored)
        self.assertEqual(actual["tree"], expected["tree"])
        self.assertEqual(actual["associations"], expected["associations"])
        self.assertEqual(actual["pending_reports"], expected["pending_reports"])
        self.assertEqual(restored.registry.get(4).state, ARCHIVED)
        self.assertEqual(restored.registry.get(5).state, DELETED)
        self.assertEqual(restored.metrics, state.metrics)
        self.assertEqual(restored.tree.audit_structure(), [])

    def test_insertion_load_rebuilds_avl_and_comparison_bst(self):
        state = self.create_scenario()

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "scenario.json"
            export_to_file(filepath, state)
            restored, bst = load_by_insertions(filepath)

        self.assertEqual(restored.tree.size, 3)
        self.assertEqual(len(restored.tree.inorder()), 3)
        self.assertEqual(len(bst.breadth_first()), 3)
        self.assertEqual(restored.tree.audit_structure(), [])
        self.assertEqual(restored.mode, "NORMAL")

    def test_topology_loader_rejects_unknown_root(self):
        state = self.create_scenario()
        document = scenario_to_dict(state)
        document["tree"]["root"] = 999

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "scenario.json"
            filepath.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_by_topology(filepath)


if __name__ == "__main__":
    unittest.main()
