from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from puzzle_gui import Launcher


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)
        self.patches = [patch("functions.persistence.GRIDS_DIRECTORY", path / "grids"),
                        patch("functions.persistence.SNAPSHOTS_DIRECTORY", path / "states")]
        for item in self.patches:
            item.start()
        self.root = tk.Tk()
        self.launcher = Launcher(self.root)
        self.launcher.name.set("GUI test")
        self.launcher.rows.set("4")
        self.launcher.columns.set("6")
        self.launcher.create()
        self.gui = self.launcher.editor
        self.root.update()
        self.gui.canvas.focus_force()
        self.root.update()

    def tearDown(self):
        self.gui.flush_save()
        self.root.destroy()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_modes_mouse_keyboard_and_null_protection(self):
        g = self.gui
        g.canvas.event_generate("<Button-1>", x=30, y=30)
        self.root.update()
        self.assertEqual(g.session.selected, (0, 0))
        g.canvas.event_generate("<Control-Key-1>")
        g.canvas.event_generate("<KeyPress-2>")
        g.canvas.event_generate("<KeyPress-7>")
        self.root.update()
        self.assertEqual(g.session.grid["scores"][0][0], 27)
        g.change_mode("Visit number")
        g.canvas.event_generate("<KeyPress-4>")
        self.root.update()
        self.assertEqual(g.session.grid["visits"][0][0], 4)
        texts = [g.canvas.itemcget(i, "text") for i in g.canvas.find_all() if g.canvas.type(i) == "text"]
        self.assertEqual(texts[:2], ["4", "27"])
        g.change_mode("Visit number")
        before = g.session.serialize()
        g.canvas.event_generate("<KeyPress-Delete>")
        g.canvas.event_generate("<KeyPress-8>")
        g.canvas.event_generate("<Button-3>", x=30, y=30)
        self.root.update()
        self.assertEqual(g.session.grid, before["grid"])
        g.canvas.event_generate("<KeyPress-Right>")
        self.root.update()
        self.assertEqual(g.session.selected, (0, 1))
        g.canvas.event_generate("<KeyPress-Escape>")
        self.root.update()
        self.assertIsNone(g.session.selected)

    def test_find_combinations_button_works_without_selected_cell(self):
        g = self.gui
        self.assertEqual(str(g.combinations_button["state"]), "disabled")

        g.session.pending_paths = [
            [[[0, 0, 10, 1, 1]], [[0, 1, 10, 1, 0]]],
            [[[1, 2, 20, 2, 1]]]]
        g.refresh()
        self.assertEqual(str(g.combinations_button["state"]), "normal")
        g.combinations_button.invoke()
        self.root.update()
        self.assertEqual(g.session.grid["visits"][0][1], 1)
        self.assertEqual(g.session.grid["visits"][1][2], 2)
        self.assertIn("1 valid combinations", g.message.get())
        self.assertEqual(str(g.combinations_button["state"]), "disabled")

    def test_visit_final_tower_button_applies_unique_path(self):
        g = self.gui
        from functions.state import Session, new_grid
        g.session = Session(new_grid("GUI test", 1, 3))
        g.session.grid["scores"][0][0] = 2
        g.session.grid["visits"][0][0] = 0
        g.session.mark_tower((0, 0), False)
        self.assertEqual(g.final_tower_button["text"], "visit final tower")
        g.final_tower_button.invoke()
        self.root.update()
        self.assertEqual(g.session.grid["visits"][0][2], 1)
        self.assertIn([0, 2], g.session.grid["towers"])
        self.assertIn("1 legal paths", g.message.get())

    def test_border_edits_and_undo(self):
        g = self.gui
        g.change_mode("Cell border drawing")
        g.canvas.event_generate("<Button-1>", x=74, y=30)
        self.root.update()
        self.assertEqual(g.session.grid["borders"], [[0, 0, 0, 1]])
        g.canvas.event_generate("<Control-Key-z>")
        self.root.update()
        self.assertFalse(g.session.grid["borders"])
        g.canvas.event_generate("<Control-Key-y>")
        self.root.update()
        self.assertEqual(g.session.grid["borders"], [[0, 0, 0, 1]])
        g.canvas.event_generate("<Button-3>", x=74, y=30)
        self.root.update()
        self.assertFalse(g.session.grid["borders"])

    def test_movement_button_and_results(self):
        g = self.gui
        self.assertEqual(str(g.movement_button.cget("state")), "disabled")
        g.session.select((0, 0))
        g.change_mode("Score")
        g.session.set_value(0)
        g.change_mode("Visit number")
        g.session.set_value(0)
        g.refresh()
        self.assertEqual(str(g.movement_button.cget("state")), "normal")
        g.movement_button.invoke()
        self.root.update()
        dialog = next(widget for widget in g.winfo_children() if isinstance(widget, tk.Toplevel))
        output = next(widget for widget in dialog.winfo_children() if isinstance(widget, tk.Text))
        text = output.get("1.0", "end")
        self.assertIn("+++ → 6", text)
        self.assertIn("Valid integers:", text)
        self.assertNotIn("*+* →", text)
        dialog.destroy()

    def test_invalid_value_status_and_snapshot_dialog(self):
        g = self.gui
        g.session.select((1, 2))
        g.change_mode("Score")
        g.value.set("2.5")
        g.apply_value()
        self.assertIsNone(g.session.grid["scores"][1][2])
        self.assertIn("integer", g.message.get())
        g.value.set("12")
        g.apply_value()
        with patch("puzzle_gui.simpledialog.askstring", return_value="checkpoint"):
            g.save_state()
        g.value.set("20")
        g.apply_value()
        g.load_state()
        self.root.update()
        dialog = next(widget for widget in g.winfo_children() if isinstance(widget, tk.Toplevel))
        button = next(widget for widget in dialog.winfo_children() if widget.winfo_class() == "TButton")
        button.invoke()
        self.root.update()
        self.assertEqual(g.session.grid["scores"][1][2], 12)
        self.assertTrue(g.session.undo_stack)

    def test_lower_half_non_tower_and_upper_half_tower(self):
        g = self.gui
        g.change_mode("Tower")
        g.canvas.event_generate("<Button-1>", x=30, y=60)
        self.root.update()
        self.assertIn([0, 0], g.session.grid["non_towers"])
        self.assertFalse(g.session.grid["towers"])
        g.canvas.event_generate("<Button-3>", x=30, y=60)
        self.root.update()
        self.assertNotIn([0, 0], g.session.grid["non_towers"])
        g.canvas.event_generate("<Button-1>", x=30, y=30)
        self.root.update()
        self.assertEqual(g.session.grid["towers"], [[0, 0]])
        self.assertEqual(len(g.session.grid["non_towers"]), 23)

    def test_continue_path_button_commits_unique_path(self):
        g = self.gui
        g.session.grid["scores"][0][0] = 0
        g.session.grid["visits"][0][0] = 0
        g.session.grid["scores"][1][2] = 1
        g.session.select((0, 0))
        g.lookahead.set("1")
        g.refresh()
        self.assertEqual(str(g.continue_button.cget("state")), "normal")
        g.continue_button.invoke()
        self.root.update()
        self.assertEqual(g.session.grid["visits"][1][2], 1)
        self.assertIn("valid paths", g.message.get())
        g.undo()
        self.assertIsNone(g.session.grid["visits"][1][2])
        for dialog in list(g.winfo_children()):
            if isinstance(dialog, tk.Toplevel):
                dialog.destroy()
