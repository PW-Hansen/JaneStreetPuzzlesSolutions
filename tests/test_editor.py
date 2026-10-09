from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from functions.state import Session, new_grid, edge_key
from functions.persistence import read_session, write_session
from functions.rendering import cell_at, edge_at, dimensions, export_png
from functions.workflow import create_named, open_named, autosave, save_snapshot, load_snapshot


class StateTests(unittest.TestCase):
    def setUp(self):
        self.session = Session(new_grid("example", 3, 4))
        self.session.select((1, 1))

    def test_null_mode_never_edits(self):
        before = self.session.serialize()
        for key in ("1", "-", "BackSpace", "Delete"):
            self.assertFalse(self.session.type_key(key))
        self.assertFalse(self.session.toggle_edge([0, 0, 0, 1]))
        self.assertFalse(self.session.set_value(7))
        self.assertEqual(before, self.session.serialize())

    def test_values_coexist_and_mode_toggle(self):
        s = self.session
        s.set_mode("Score")
        s.input_text("-21")
        s.set_mode("Visit number")
        s.input_text("0")
        self.assertEqual(s.grid["scores"][1][1], -21)
        self.assertEqual(s.grid["visits"][1][1], 0)
        s.type_key("Delete")
        self.assertEqual(s.grid["scores"][1][1], -21)
        s.set_mode("Visit number")
        self.assertEqual(s.mode, "Select")

    def test_invalid_integer_does_not_change_state(self):
        s = self.session
        s.set_mode("Score")
        s.input_text("5")
        before = s.serialize()
        for text in ("1.5", "a", "2e3", "-", "12 3"):
            with self.assertRaises(ValueError):
                s.input_text(text)
            self.assertEqual(before, s.serialize())

    def test_typing_replaces_then_appends_and_backspaces(self):
        s = self.session
        s.set_mode("Score")
        s.input_text("999")
        s.type_key("1")
        s.type_key("2")
        self.assertEqual(s.grid["scores"][1][1], 12)
        s.type_key("BackSpace")
        self.assertEqual(s.grid["scores"][1][1], 1)
        s.type_key("BackSpace")
        self.assertIsNone(s.grid["scores"][1][1])

    def test_borders_history_and_reset(self):
        s = self.session
        s.set_mode("Score")
        s.input_text("20")
        s.set_mode("Visit number")
        s.input_text("3")
        s.set_mode("Cell border drawing")
        edge = edge_key((0, 1), (0, 0))
        s.toggle_edge(edge)
        self.assertEqual(s.grid["borders"], [[0, 0, 0, 1]])
        s.reset_visits()
        self.assertIsNone(s.grid["visits"][1][1])
        self.assertEqual(s.grid["scores"][1][1], 20)
        self.assertEqual(s.grid["borders"], [edge])
        s.history()
        self.assertEqual(s.grid["visits"][1][1], 3)
        s.history(True)
        self.assertIsNone(s.grid["visits"][1][1])
        s.history()
        s.toggle_edge(edge, clear=True)
        self.assertFalse(s.redo_stack)
        self.assertFalse(s.grid["borders"])

    def test_history_roundtrip_validation(self):
        s = self.session
        s.set_mode("Score")
        s.input_text("7")
        s.input_text("8")
        s.history()
        data = json.loads(json.dumps(s.serialize()))
        restored = Session.deserialize(data)
        restored.history(True)
        self.assertEqual(restored.grid["scores"][1][1], 8)
        invalid = deepcopy(data)
        invalid["undo"][0]["grid"]["scores"][0][0] = True
        with self.assertRaises(ValueError):
            Session.deserialize(invalid)
        invalid = deepcopy(data)
        invalid["grid"]["borders"] = [[0, 0, 1, 1]]
        with self.assertRaises(ValueError):
            Session.deserialize(invalid)

    def test_hit_testing(self):
        grid = self.session.grid
        self.assertEqual(cell_at(grid, 20, 20), (0, 0))
        self.assertIsNone(cell_at(grid, 0, 0))
        self.assertEqual(edge_at(grid, 74, 25), [0, 0, 0, 1])
        self.assertEqual(edge_at(grid, 25, 74), [0, 0, 1, 0])
        self.assertIsNone(edge_at(grid, 10, 25))
        self.assertIsNone(edge_at(grid, 42, 42))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.patches = [patch("functions.persistence.GRIDS_DIRECTORY", root / "grids"),
                        patch("functions.persistence.SNAPSHOTS_DIRECTORY", root / "states"),
                        patch("functions.rendering.PROJECT_ROOT", root)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def test_reopen_snapshots_and_history(self):
        s = create_named("example", "3", "4")
        s.select((1, 2))
        s.set_mode("Score")
        s.input_text("45")
        s.input_text("46")
        s.history()
        autosave(s)
        restored = open_named("example")
        self.assertEqual(restored.mode, "Select")
        self.assertEqual(restored.selected, (1, 2))
        self.assertEqual(restored.grid["scores"][1][2], 45)
        restored.history(True)
        self.assertEqual(restored.grid["scores"][1][2], 46)
        save_snapshot(s, "checkpoint")
        loaded = load_snapshot(restored, "checkpoint")
        self.assertEqual(loaded.grid["scores"][1][2], 45)
        self.assertTrue(loaded.redo_stack)
        self.assertEqual(open_named("example").grid, loaded.grid)

    def test_bad_files_names_and_duplicate_creation(self):
        s = create_named("example", "2", "3")
        with self.assertRaises(ValueError):
            create_named("example", "4", "5")
        for name in ("../escape", "CON", "name/child", "", "name."):
            with self.assertRaises(ValueError):
                create_named(name, "2", "3")
        path = Path(self.directory.name) / "bad.json"
        path.write_text('{"version":1}', encoding="utf-8")
        before = s.serialize()
        with self.assertRaises(ValueError):
            read_session(path)
        self.assertEqual(before, s.serialize())
        write_session(path, s)
        with self.assertRaises(ValueError):
            read_session(path, "other")

    def test_png_export_dimensions_and_pixels(self):
        from PIL import Image
        s = create_named("example", "2", "3")
        s.select((0, 0))
        s.set_mode("Score")
        s.input_text("27")
        s.set_mode("Visit number")
        s.input_text("4")
        path = export_png(s, "image")
        with Image.open(path) as image:
            self.assertEqual(image.size, dimensions(s.grid))
            self.assertEqual(image.getpixel((10, 10)), (0, 0, 0))
            self.assertEqual(image.getpixel((150, 35)), (255, 255, 255))
            colors = image.getcolors(image.width * image.height)
            self.assertGreater(len(colors), 3)
