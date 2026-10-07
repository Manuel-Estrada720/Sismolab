"""The Observatory facade: the only entry point the Tkinter window uses."""

import json
import tempfile
import unittest
from pathlib import Path

from src.services.observatory import Observatory

from tests.helpers import OLD_TIME, STATION, event_form, report_form

DATA = Path(__file__).resolve().parents[1] / "data"


class ObservatoryFacadeTests(unittest.TestCase):
    def setUp(self):
        self.obs = Observatory(versions_dir=tempfile.mkdtemp())

    def assertShape(self, result):
        self.assertEqual(set(result), {"ok", "message", "details"})
        return result

    def test_state_view_shape(self):
        view = self.obs.state_view()
        for name in ("mode", "clock", "parameters", "metrics", "queue", "undo", "events",
                     "avl", "bst", "indicators", "zones", "stations", "last_action"):
            self.assertIn(name, view)
        self.assertEqual(view["parameters"]["T"], 72)

    def test_event_lifecycle_with_spanish_messages(self):
        self.assertTrue(self.assertShape(self.obs.create_event(event_form(10, "5.2")))["ok"])
        result = self.obs.create_event(event_form(10, "5.2"))
        self.assertFalse(result["ok"])
        self.assertIn("identificador", result["message"])
        self.obs.create_event(event_form(20, "4.0"))
        self.obs.create_event(event_form(30, "3.0"))
        result = self.obs.correct_event(30, {"magnitude": "7.0", "station": STATION})
        self.assertTrue(result["ok"])
        self.assertTrue(result["details"]["key_changed"])
        self.assertIn("moved", result["details"])
        details = self.obs.get_event(30)["details"]
        self.assertEqual(details["magnitude"], 7)
        self.assertEqual(details["revision"], 2)
        self.assertIn("node_depth", details)
        self.assertTrue(self.obs.mark_reviewed(30)["ok"])
        self.assertTrue(self.obs.delete_event(20)["ok"])
        self.assertIn("eliminado", self.obs.get_event(20)["message"])
        self.assertTrue(self.obs.undo()["ok"])
        self.assertIn("activo", self.obs.get_event(20)["message"])

    def test_failed_action_leaves_state_intact(self):
        self.obs.create_event(event_form(1, "5.0"))
        before = self.obs.export()
        self.assertFalse(self.obs.create_event(event_form(2, "11"))["ok"])
        self.assertFalse(self.obs.set_parameters({"W": "-3"})["ok"])
        self.assertFalse(self.obs.create_event(dict(event_form(3, "5.0"), station="NO-EXISTE"))["ok"])
        self.assertEqual(self.obs.export(), before)

    def test_queue_stress_recover_and_trees(self):
        reports = [report_form(i, "3.0", 1) for i in range(1, 21)]
        self.obs.enter_stress()
        self.assertTrue(self.obs.enqueue_reports(reports)["ok"])
        self.assertEqual(len(self.obs.state_view()["queue"]), 20)
        self.assertEqual(self.obs.process_step()["details"]["decision"], "CREATED")
        self.obs.process_all()
        view = self.obs.state_view()
        self.assertEqual(view["mode"], "STRESS")
        self.assertEqual(view["avl"]["height"], 19)
        self.assertTrue(any(node["unbalanced"] for node in view["avl"]["nodes"]))
        self.assertTrue(self.obs.audit()["ok"])
        result = self.obs.recover()
        self.assertTrue(result["ok"], result["message"])
        self.assertGreater(len(result["details"]["moved"]), 0)
        view = self.obs.state_view()
        self.assertEqual(view["mode"], "NORMAL")
        self.assertEqual(view["bst"]["height"], 19)
        node = view["avl"]["nodes"][0]
        for name in ("left", "right", "depth", "balance", "height", "costly", "key", "inorder"):
            self.assertIn(name, node)

    def test_archive_clock_parameters_queries_comparison(self):
        for i in range(1, 8):
            self.obs.create_event(event_form(i, "3.0", time=OLD_TIME))
        preview = self.obs.archive_preview()
        self.assertEqual(preview["details"]["count"], 7)
        self.assertTrue(self.obs.archive_apply(preview["details"]["ids"])["ok"])
        self.assertEqual(self.obs.state_view()["metrics"]["archived_events"], 7)
        self.assertTrue(self.obs.advance_clock(hours="1.5")["ok"])
        self.assertEqual(self.obs.state_view()["clock"], "2026-09-07T13:30:00Z")
        self.assertTrue(self.obs.set_parameters({"L": "1"})["ok"])
        for _ in range(3):
            self.obs.undo()
        queries = (
            ("pending", {"k": "3"}),
            ("magnitude", {"min": "2", "max": "4"}),
            ("costly", {}),
            ("depth-dates", {"max_depth": "50", "from": "2026-09-01T00:00:00Z", "to": "2026-09-07T00:00:00Z"}),
            ("associations", {"id": "3"}),
        )
        for name, params in queries:
            result = self.obs.query(name, params)
            self.assertTrue(result["ok"], name + " " + result["message"])
            self.assertIn("examined", result["details"])
        self.assertFalse(self.obs.query("magnitude", {"min": "x", "max": "2"})["ok"])
        self.assertEqual(len(self.obs.compare()["details"]["rows"]), 4)

    def test_load_content_and_versions(self):
        content = (DATA / "scenarios" / "escenario_estres.json").read_text(encoding="utf-8")
        result = self.obs.load_scenario(content, "topology")
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(self.obs.state_view()["mode"], "STRESS")
        simple = json.loads((DATA / "scenarios" / "insercion_30.json").read_text(encoding="utf-8"))
        result = self.obs.load_scenario(simple, "insertions")
        self.assertTrue(result["ok"])
        self.assertIn("bst", result["details"])
        bad = (DATA / "scenarios" / "invalido_topologia.json").read_text(encoding="utf-8")
        before = self.obs.export()
        result = self.obs.load_scenario(bad, "topology")
        self.assertFalse(result["ok"])
        self.assertGreater(len(result["details"]["problems"]), 1)
        self.assertEqual(self.obs.export(), before)
        self.assertTrue(self.obs.save_version("v1")["ok"])
        self.assertEqual(self.obs.list_versions()["details"]["versions"][0]["name"], "v1")
        self.obs.new_scenario()
        self.assertTrue(self.obs.restore_version("v1")["ok"])
        self.assertEqual(self.obs.export(), before)


if __name__ == "__main__":
    unittest.main()
