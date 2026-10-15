import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

from functions.model import Puzzle, read, write, save_snapshot, load_snapshot
from functions.rendering import export_png, draw
from puzzle_gui import Editor


class ModelTests(unittest.TestCase):
    def test_snapshot_restores_history_and_selection(self):
        puzzle = Puzzle('Snapshot', 3, 4)
        puzzle.change('entries', '0,0', '9')
        puzzle.change('colors', '0,0', 2)
        puzzle.undo()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'snapshot.json'
            save_snapshot(path, puzzle, (-1, 0))
            puzzle.change('entries', '0,0', '8')
            selection = load_snapshot(path, puzzle)
            self.assertEqual(selection, (-1, 0))
            self.assertEqual(puzzle.data['entries']['0,0'], '9')
            puzzle.redo()
            self.assertEqual(puzzle.data['colors']['0,0'], 2)

    def test_digits_black_inside_and_outside(self):
        puzzle = Puzzle('Colors', 2, 2)
        for key, value in [('0,0', '9'), ('-1,0', '123'), ('0,2', 'F')]:
            puzzle.change('entries', key, value)
        rendered = {}
        draw(puzzle.data, lambda *args: None, lambda *args: None,
             lambda position, value, color: rendered.update({value: color}))
        self.assertEqual(rendered, {'9': 'black', '123': 'black', 'F': '#c62828'})

    def test_roundtrip_history_and_independent_layers(self):
        puzzle = Puzzle('Example', 3, 4)
        puzzle.change('entries', '0,0', '9')
        puzzle.change('colors', '0,0', 2)
        puzzle.change('borders', 'v,0,1', True)
        puzzle.undo()
        self.assertEqual(puzzle.data['entries']['0,0'], '9')
        puzzle.redo()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'grid.json'
            write(path, puzzle.data)
            self.assertEqual(read(path), puzzle.data)
        puzzle.undo()
        puzzle.change('entries', '-1,0', '123')
        self.assertEqual(puzzle.redo_stack, [])

    def test_invalid_load_preserves_current_state(self):
        puzzle = Puzzle('Example', 3, 4)
        original = copy.deepcopy(puzzle.data)
        invalid = dict(original, colors={'100,0': 3})
        with self.assertRaises(ValueError):
            puzzle.replace(invalid)
        self.assertEqual(puzzle.data, original)
        with self.assertRaises(ValueError):
            puzzle.replace(dict(original, name='Other'))


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent.resolve())
        self.patch = patch('puzzle_gui.ROOT', Path(self.folder.name))
        self.patch.start()
        self.root = tk.Tk()
        self.editor = Editor(self.root, Puzzle('Inspection', 9, 9))
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self.patch.stop()
        self.folder.cleanup()

    def key(self, char='', keysym=''):
        self.editor.key(SimpleNamespace(char=char, keysym=keysym or char, state=0))

    def test_editing_select_and_restore(self):
        editor = self.editor
        editor.selected = (0, 0)
        self.key('9')
        self.assertFalse(editor.puzzle.data['entries'])
        editor.set_mode(1)
        self.key('1')
        self.key('2')
        self.assertEqual(editor.puzzle.data['entries']['0,0'], '12')
        editor.set_mode(3)
        self.key('4')
        editor.click(SimpleNamespace(x=90, y=90), False)
        self.assertEqual(editor.puzzle.data['colors']['0,0'], 4)
        self.assertEqual(editor.puzzle.data['entries']['0,0'], '12')
        editor.undo()
        self.assertFalse(editor.puzzle.data['colors'])
        editor.redo()
        self.assertEqual(editor.puzzle.data['colors']['0,0'], 4)
        restored = read(Path(self.folder.name) / 'grids' / 'Inspection.json')
        self.assertEqual(restored, editor.puzzle.data)
        editor.set_mode(3)
        self.assertEqual(editor.mode.get(), 0)
        self.key(keysym='Delete')
        self.assertEqual(restored, editor.puzzle.data)

    def test_borders_outside_entries_and_export(self):
        editor = self.editor
        editor.set_mode(2)
        editor.click(SimpleNamespace(x=120, y=90), False)
        self.assertIn('v,0,1', editor.puzzle.data['borders'])
        editor.set_mode(1)
        editor.click(SimpleNamespace(x=90, y=30), False)
        self.key('F')
        self.assertEqual(editor.puzzle.data['entries']['-1,0'], 'F')
        editor.puzzle.change('colors', '0,0', 5)
        path = Path(self.folder.name) / 'export.png'
        export_png(path, editor.puzzle.data, editor.selected)
        from PIL import Image
        with Image.open(path) as image:
            self.assertEqual(image.size, (660, 660))
            self.assertEqual(image.getpixel((80,80)), (189,230,238))


if __name__ == '__main__':
    unittest.main()
