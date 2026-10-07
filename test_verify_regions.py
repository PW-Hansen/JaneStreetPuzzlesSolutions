import unittest
from types import SimpleNamespace

from puzzle_gui import PuzzleEditor, blank_grid, determine_regions


class VerifyRegionTests(unittest.TestCase):
    def board(self, rows=1, columns=2):
        return {'rows': rows, 'columns': columns, 'cells': blank_grid(rows, columns)}

    def test_geometry_and_all_clue_scores_are_verified(self):
        state = self.board()
        state['cells'][0][0]['number'] = 8
        state['cells'][0][1]['number'] = 8
        region = next(iter(determine_regions(state)[0].values()))
        self.assertTrue(region.verify(state))
        self.assertEqual(region.score, 8)
        state['cells'][0][1]['number'] = 9
        self.assertFalse(region.verify(state))

    def test_noninteger_and_reconnected_arcs_are_invalid(self):
        state = self.board(1, 1)
        state['cells'][0][0]['arc'] = 'tl'
        self.assertTrue(all(not region.verify(state) for region in determine_regions(state)[0].values()))
        state = self.board(3, 3)
        state['cells'][1][1]['arc'] = 'tl'
        region = next(iter(determine_regions(state)[0].values()))
        self.assertTrue(region.is_integer)
        self.assertFalse(region.verify(state))

    def test_button_colors_regions_and_clears_speculative_preview(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = self.board()
        editor.state['cells'][0][0]['number'] = 8
        editor.preview_index = 2
        editor.draw = lambda: None
        editor.status = SimpleNamespace(set=lambda message: None)
        editor.verify_regions()
        self.assertEqual(editor.preview_index, 0)
        self.assertEqual(set(editor.region_colors.values()), {'#a8dfac'})
        editor.state['cells'][0][0]['number'] = 7
        editor.verify_regions()
        self.assertEqual(set(editor.region_colors.values()), {'#c4c4c4'})


if __name__ == '__main__':
    unittest.main()
