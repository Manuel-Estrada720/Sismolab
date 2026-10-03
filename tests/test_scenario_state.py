import unittest

from src.models.scenario_state import ScenarioState


class ScenarioStateTests(unittest.TestCase):
    def test_defaults_create_independent_empty_scenarios(self):
        first = ScenarioState()
        second = ScenarioState()

        self.assertEqual(first.mode, "NORMAL")
        self.assertEqual(first.clock_epoch, 0)
        self.assertEqual(first.parameters, {"W": 48, "R": 40, "L": 3})
        self.assertEqual(first.tree.size, 0)
        self.assertEqual(first.registry.records, {})
        self.assertEqual(first.zones.zones, [])
        self.assertTrue(first.pending_reports.is_empty())
        self.assertIsNot(first.tree, second.tree)
        self.assertIsNot(first.registry, second.registry)
        self.assertIsNot(first.parameters, second.parameters)

    def test_mode_updates_avl_stress_flag(self):
        state = ScenarioState()

        state.mode = "STRESS"
        self.assertTrue(state.tree.stress_mode)
        self.assertEqual(state.mode, "STRESS")

        state.mode = "NORMAL"
        self.assertFalse(state.tree.stress_mode)

    def test_rejects_invalid_scenario_clock_and_parameters(self):
        with self.assertRaises(TypeError):
            ScenarioState(clock_epoch=1.5)
        with self.assertRaises(ValueError):
            ScenarioState(parameters={"W": 0, "R": 40, "L": 3})
        with self.assertRaises(ValueError):
            ScenarioState(parameters={"W": 48, "R": 40, "L": -1})


if __name__ == "__main__":
    unittest.main()
