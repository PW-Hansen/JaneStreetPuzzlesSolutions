import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageChops
from functions.clue_analysis import ClueAnalysis
from puzzle_gui import PuzzleEditor, blank_grid, render_grid


class Variable:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class NamedStateTests(unittest.TestCase):
    def editor(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = {'rows': 1, 'columns': 2, 'cells': blank_grid(1, 2)}
        editor.state['cells'][0][0]['number'] = 8
        editor.puzzle_name = 'example'
        editor.root = SimpleNamespace()
        editor.analysis_cancel = None
        editor.batch_token = None
        editor.analysis_result = ClueAnalysis(accepted_states=[((0, 0, 'tl'),), ((0, 0, 'br'),)], source_clue=(0, 0))
        editor.preview_index = 1
        editor.selected = (0, 0)
        editor.mode = Variable('arc')
        editor.simplify_arcs = Variable(True)
        editor.prioritize_cells = Variable(False)
        editor.check_other_clues = Variable(True)
        editor.undo_stack = [copy.deepcopy(editor.state)]
        editor.redo_stack = []
        editor.smooth_colors = {(0, 0): '#1769aa'}
        editor.region_colors = {(0, 0, 0): '#a8dfac'}
        editor.area_labels = [((0, 1, .5, .5, .8), '2')]
        editor.analysis_elapsed_seconds = 1.5
        editor.batch_elapsed_seconds = 4.5
        editor.status = Variable('')
        editor.draw = lambda: None
        editor.save = lambda: True
        return editor

    def test_named_snapshot_and_print_restore_grid_view_and_history(self):
        editor = self.editor()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            with patch('puzzle_gui.SAVED_STATES_DIRECTORY', root / 'saved states'), \
                    patch('puzzle_gui.__file__', str(root / 'puzzle_gui.py')), \
                    patch('puzzle_gui.simpledialog.askstring', return_value='checkpoint'):
                editor.print_state()
            path = root / 'saved states' / 'example' / 'checkpoint.json'
            self.assertTrue(path.exists())
            with Image.open(root / 'checkpoint.png') as image:
                self.assertEqual(image.format, 'PNG')
                self.assertEqual(image.size, (192, 112))
            expected = copy.deepcopy(editor.state)
            editor.state['cells'][0][0]['arc'] = 'tr'
            editor.preview_index = 0
            editor.undo_stack = []
            editor.smooth_colors = None
            self.assertTrue(editor.load_named_state(path))
            self.assertEqual(editor.state['cells'], expected['cells'])
            self.assertEqual(editor.preview_index, 1)
            self.assertEqual(editor.selected, (0, 0))
            self.assertEqual(len(editor.undo_stack), 1)
            self.assertEqual(editor.smooth_colors, {(0, 0): '#1769aa'})
            self.assertEqual(editor.area_labels, [((0, 1, .5, .5, .8), '2')])
            self.assertFalse(editor.prioritize_cells.get())
            editor.puzzle_name = 'other'
            before = copy.deepcopy(editor.state)
            self.assertFalse(editor.load_named_state(path))
            self.assertEqual(editor.state, before)

    def test_png_includes_digits_and_cancel_does_not_write(self):
        editor = self.editor()
        plain = render_grid(editor.state, 80)
        labeled = render_grid(editor.state, 80, include_labels=True)
        self.assertIsNotNone(ImageChops.difference(plain, labeled).getbbox())
        with patch('puzzle_gui.simpledialog.askstring', return_value=None), \
                patch.object(editor, 'named_snapshot') as snapshot:
            editor.save_named_state()
        snapshot.assert_not_called()


if __name__ == '__main__':
    unittest.main()
