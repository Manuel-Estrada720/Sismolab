"""Tkinter window: it opens, its buttons call the Observatory and it redraws.

Skipped automatically when Tkinter or a screen is not available.
"""

import tempfile
import unittest

try:
    import tkinter
    from tkinter import messagebox
except ImportError:          # Python without Tkinter
    tkinter = None

from src.services.observatory import Observatory


def open_app():
    from src.gui.app import SismoLabApp
    try:
        app = SismoLabApp(Observatory(versions_dir=tempfile.mkdtemp()))
    except tkinter.TclError as error:     # no screen (for example a server)
        raise unittest.SkipTest("sin pantalla: " + str(error))
    app.withdraw()
    return app


@unittest.skipIf(tkinter is None, "Tkinter no está instalado")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.app = open_app()
        self.original_ask = messagebox.askyesno
        messagebox.askyesno = lambda *args, **kwargs: True   # answer "Sí" to confirmations

    def tearDown(self):
        messagebox.askyesno = self.original_ask
        self.app.destroy()

    def fill(self, entries_and_values):
        for entry, value in entries_and_values:
            entry.delete(0, "end")
            entry.insert(0, value)

    def create(self, event_id, magnitude):
        tab = self.app.events_tab
        self.fill([(tab.new_id, event_id), (tab.new_magnitude, magnitude), (tab.new_depth, "20"),
                   (tab.new_x, "450"), (tab.new_y, "450")])
        tab.create()

    def test_create_select_delete_and_undo(self):
        for event_id, magnitude in (("10", "5.2"), ("20", "3.0"), ("30", "6.4")):
            self.create(event_id, magnitude)
        self.assertEqual(self.app.view["avl"]["size"], 3)
        self.assertEqual(len(self.app.events_tab.catalog.get_children()), 3)
        self.assertTrue(self.app.tree_view.canvas.find_withtag("id:20"))
        self.app.select(20)
        self.assertIn("SIS-000020", self.app.node_panel.title.cget("text"))
        self.app.node_panel.delete()
        self.assertEqual(self.app.view["avl"]["size"], 2)
        self.app.undo()
        self.assertEqual(self.app.view["avl"]["size"], 3)

    def test_rejected_action_is_red_and_changes_nothing(self):
        self.create("10", "5.2")
        before = self.app.obs.export()
        self.create("11", "11")             # magnitude out of range
        self.assertTrue(self.app.message.cget("text").startswith("No se aplicó"))
        self.assertEqual(self.app.obs.export(), before)

    def test_queue_stress_and_recovery_buttons(self):
        queue = self.app.queue_tab
        queue.enter_stress()
        for event_id in range(1, 9):
            self.fill([(queue.rep_id, str(event_id)), (queue.rep_magnitude, "3.0"), (queue.rep_depth, "10"),
                       (queue.rep_x, "950"), (queue.rep_y, "950")])
            queue.add_report()
        queue.send_burst()
        self.assertEqual(len(queue.queue_table.get_children()), 8)
        queue.process_all()
        self.assertEqual(self.app.view["avl"]["height"], 7)
        queue.recover()
        self.assertEqual(self.app.view["mode"], "NORMAL")
        self.app.audit_tab.audit()
        self.assertIn("correcta", self.app.audit_tab.audit_label.cget("text"))

    def test_every_tab_draws(self):
        self.create("10", "5.2")
        self.app.queries_tab.pending()
        self.assertIn("examinados", self.app.queries_tab.pending_out[0].cget("text"))
        self.app.comparison_tab.compare()
        self.assertEqual(len(self.app.comparison_tab.table.get_children()), 8)
        self.app.map_tab.draw()
        self.assertTrue(self.app.map_tab.canvas.find_withtag("id:10"))
        self.app.tree_view.choice.set("Ambos")
        self.app.tree_view.draw()
        self.assertTrue(self.app.tree_view.canvas.find_withtag("id:10"))


if __name__ == "__main__":
    unittest.main()
