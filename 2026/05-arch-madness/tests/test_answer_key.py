import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from puzzle_gui import blank_grid, compute_answer_key, PuzzleEditor, Region


class AnswerKeyTests(unittest.TestCase):
    def test_fill_scores_include_existing_clues_and_square_both_axes(self):
        state = {'rows': 2, 'columns': 3, 'cells': blank_grid(2, 3)}
        state['cells'][0][0]['number'] = 24
        before = copy.deepcopy(state)
        key = compute_answer_key(state)
        self.assertEqual(key['values'], [[24, 24, 24], [24, 24, 24]])
        self.assertEqual(key['row_sums'], [72, 72])
        self.assertEqual(key['column_sums'], [48, 48, 48])
        self.assertEqual(key['answer'], 17280)
        self.assertEqual(state, before)

    def test_invalid_geometry_or_clue_blocks_answer(self):
        state = {'rows': 1, 'columns': 1, 'cells': blank_grid(1, 1)}
        state['cells'][0][0]['arc'] = 'tl'
        with self.assertRaises(ValueError):
            compute_answer_key(state)
        state['cells'][0][0]['arc'] = None
        state['cells'][0][0]['number'] = 3
        with self.assertRaises(ValueError):
            compute_answer_key(state)

    def test_arc_cell_uses_majority_fragment(self):
        state = {'rows': 1, 'columns': 1, 'cells': blank_grid(1, 1)}
        state['cells'][0][0]['arc'] = 'tl'
        inside = Region(0, frozenset({(0, 0, 0)}))
        outside = Region(1, frozenset({(0, 0, 1)}))
        object.__setattr__(inside, 'score', 7)
        object.__setattr__(outside, 'score', 99)
        with patch('functions.puzzle_model.determine_regions', return_value=({(0, 0, 0): inside, (0, 0, 1): outside}, {}, [])), \
                patch.object(Region, 'verify', return_value=True):
            self.assertEqual(compute_answer_key(state)['values'], [[7]])

    def test_button_displays_only_unlabelled_values_without_mutating_puzzle(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = {'rows': 1, 'columns': 2, 'cells': blank_grid(1, 2)}
        editor.state['cells'][0][0]['number'] = 8
        before = copy.deepcopy(editor.state)
        editor.mode = SimpleNamespace(set=lambda value: None)
        editor.status = SimpleNamespace(set=lambda value: None)
        editor.draw = lambda: None
        with patch('builtins.print'):
            editor.compute_answer_key()
        self.assertEqual(editor.area_labels, [((0, 1, .5, .5, .8), '8')])
        self.assertEqual(editor.state, before)


if __name__ == '__main__':
    unittest.main()
