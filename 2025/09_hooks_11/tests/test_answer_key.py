import copy
import tkinter as tk
import unittest
from unittest.mock import patch

from functions.answer_key import compute_answer_key
from functions.model import Puzzle
from functions.pentominoes import PentominoSearch
from pentomino_fixtures import example_puzzle
from puzzle_gui import Editor


def numbered_grid(size, filled):
    puzzle = Puzzle('Answer',size,size)
    digits = [str(digit) for digit in range(1,size+1) for _ in range(digit)]
    puzzle.data['entries'] = {f'{r},{c}':digit for (r,c),digit in zip(sorted(filled),digits)}
    return puzzle


class AnswerKeyTests(unittest.TestCase):
    def test_empty_region_areas_ignore_borders_colors_and_outside_clues(self):
        filled = {(0,0),(0,1),(0,2),(1,1),(2,1),(2,2)}
        puzzle = numbered_grid(3,filled)
        puzzle.data['entries']['-1,0'] = '99'
        puzzle.data['colors']['1,0'] = 2
        puzzle.data['borders']['h,2,0'] = True
        answer = compute_answer_key(puzzle.data)
        self.assertEqual(answer.areas,(1,2))
        self.assertEqual(answer.value,2)
        self.assertIn('Answer key: 2',answer.report())

    def test_diagonally_touching_empty_cells_stay_in_separate_regions(self):
        empty = {(1,1),(1,3),(2,2),(2,3),(3,0),(3,3)}
        puzzle = numbered_grid(4,{(r,c) for r in range(4) for c in range(4)}-empty)
        answer = compute_answer_key(puzzle.data)
        self.assertEqual(answer.areas,(1,1,4))
        self.assertEqual(answer.value,4)

    def test_incomplete_and_invalid_filled_grids_have_no_answer(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):
            compute_answer_key(Puzzle('Empty',3,3).data)
        puzzle = numbered_grid(3,{(r,c) for r in range(3) for c in range(2)})
        with self.assertRaisesRegex(ValueError,'2x2'):
            compute_answer_key(puzzle.data)
        puzzle = numbered_grid(3,{(r,c) for r in range(3) for c in range(3) if r != c})
        with self.assertRaisesRegex(ValueError,'connected'):
            compute_answer_key(puzzle.data)

    def test_selected_preview_is_used_without_changing_confirmed_entries(self):
        puzzle = example_puzzle()
        search = PentominoSearch(puzzle.data)
        list(search.run())
        puzzle.set_pentomino_analysis(search,0.0)
        original = copy.deepcopy(puzzle.data)
        answer = compute_answer_key(puzzle.data)
        self.assertEqual(answer.areas,(1,1,1,2,2,3))
        self.assertEqual(answer.value,12)
        self.assertEqual(puzzle.data,original)
        puzzle.preview_pentominoes(-1)
        with self.assertRaisesRegex(ValueError,'incomplete'):
            compute_answer_key(puzzle.data)


class AnswerKeyGuiTests(unittest.TestCase):
    def test_gui_generates_answer_and_invalidates_it_after_editing(self):
        root = tk.Tk()
        root.withdraw()
        try:
            puzzle = numbered_grid(3,{(0,0),(0,1),(0,2),(1,1),(2,1),(2,2)})
            editor = Editor(root,puzzle)
            editor.generate_answer_key()
            self.assertIn('Answer key: 2',editor.answer_text.get('1.0','end'))
            with patch('puzzle_gui.write'):
                puzzle.change('entries','0,0',None)
                editor.changed()
            self.assertNotIn('Answer key: 2',editor.answer_text.get('1.0','end'))
            editor.generate_answer_key()
            self.assertIn('unavailable',editor.answer_text.get('1.0','end'))
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
