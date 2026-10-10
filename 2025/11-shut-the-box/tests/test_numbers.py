import itertools
import tempfile
import unittest
from pathlib import Path
from functions.model import Puzzle
from functions.numbers import number_neighborhood
from functions.numbers import propagate_numbers
from functions.arrows import analyze_arrows
from functions.storage import Storage


class NumberTests(unittest.TestCase):
    def test_nine_includes_center_and_all_eight_neighbors(self):
        p = Puzzle('test', 3, 3)
        p.edit(4, 'Digit Entering', digit='9')
        self.assertEqual(p.analysis.boxes, [True] * 9)
        self.assertEqual(p.analysis.numbers[4].yes, 9)
        self.assertTrue(all(cell['shading'] == 0 for cell in p.cells))

    def test_diagonal_edit_forces_remaining_neighbors_and_undo_retracts(self):
        p = Puzzle('test', 3, 3)
        p.edit(4, 'Digit Entering', digit='3')
        p.edit(1, 'Shading')
        p.edit(1, 'Shading')  # connector between the center and diagonal cell
        p.edit(0, 'Shading')
        p.edit(0, 'Shading')  # diagonal neighbor becomes yes
        self.assertEqual(p.analysis.boxes, [True, True, False, False, True, False, False, False, False])
        p.undo()
        self.assertIsNone(p.analysis.boxes[2])
        p.redo()
        self.assertFalse(p.analysis.boxes[2])
        p.edit(0, 'Shading', action='clear')
        self.assertIsNone(p.analysis.boxes[2])

    def test_orthogonal_no_edits_force_remaining_cell(self):
        p = Puzzle('test', 1, 3)
        p.edit(1, 'Digit Entering', digit='2')
        p.edit(0, 'Shading')
        self.assertTrue(p.analysis.boxes[2])
        self.assertEqual(p.analysis.sources[2], 'number rules')

    def test_corner_neighborhood_stays_in_bounds(self):
        p = Puzzle('test', 3, 3)
        p.edit(0, 'Digit Entering', digit='4')
        self.assertEqual(number_neighborhood(0, 3, 3), [0, 1, 3, 4])
        for index in (0, 1, 3, 4): self.assertTrue(p.analysis.boxes[index])
        for index in (2, 5, 6, 7, 8): self.assertIsNone(p.analysis.boxes[index])

    def test_changing_or_removing_number_recomputes(self):
        p = Puzzle('test', 3, 3)
        p.edit(4, 'Digit Entering', digit='1')
        self.assertFalse(p.analysis.boxes[0])
        p.edit(4, 'Digit Entering', digit='2')
        self.assertIsNone(p.analysis.boxes[0])
        p.undo()
        self.assertFalse(p.analysis.boxes[0])
        p.edit(4, 'Digit Entering', action='clear')
        self.assertEqual(p.analysis.boxes, [None] * 9)

    def test_too_many_and_unreachable_counts(self):
        p = Puzzle('test', 3, 3)
        p.edit(4, 'Digit Entering', digit='1')
        p.edit(0, 'Shading')
        p.edit(0, 'Shading')
        self.assertTrue(p.analysis.conflicts)
        self.assertTrue(p.analysis.boxes[0])  # preserve manual yes
        self.assertIsNone(p.analysis.boxes[1])  # withhold deductions
        p = Puzzle('test', 2, 2)
        p.edit(0, 'Digit Entering', digit='5')
        self.assertTrue(p.analysis.conflicts)
        p.edit(0, 'Digit Entering', digit='0')
        self.assertTrue(p.analysis.conflicts)  # numbered cell itself is yes

    def test_number_and_arrow_deductions_feed_each_other(self):
        p = Puzzle('test', 2, 3)
        p.edit(0, 'Arrow Entering', direction='east')
        p.edit(4, 'Digit Entering', digit='4')
        self.assertFalse(p.analysis.conflicts)
        self.assertTrue(p.analysis.boxes[1])
        self.assertEqual(p.analysis.distances[0], [1])
        self.assertEqual(p.analysis.boxes, [False, True, True, False, True, True])
        p = Puzzle('test', 2, 3)
        p.edit(2, 'Digit Entering', digit='3')
        p.edit(0, 'Arrow Entering', direction='south')
        self.assertFalse(p.analysis.conflicts)
        self.assertTrue(p.analysis.boxes[3])
        self.assertTrue(p.analysis.boxes[4])
        self.assertTrue(p.analysis.boxes[5])

    def test_snapshot_and_reset_restore_analysis(self):
        p = Puzzle('test', 3, 3)
        p.edit(4, 'Digit Entering', digit='2')
        p.edit(0, 'Shading')
        p.edit(0, 'Shading')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            snapshot = storage.snapshot_path('test', 'number state')
            storage.save(p, snapshot)
            loaded = storage.load(snapshot)
            self.assertEqual(loaded.analysis, p.analysis)
            loaded.reset(shading_only=True)
            self.assertIsNone(loaded.analysis.boxes[0])
            loaded.undo()
            self.assertTrue(loaded.analysis.boxes[0])

    def test_number_deductions_against_exhaustive_assignments(self):
        for target in range(1, 10):
            for fixed in ({}, {0: False}, {0: True}, {0: True, 1: False}):
                p = Puzzle('test', 3, 3)
                p.cells[4]['digit'] = str(target)
                for index, value in fixed.items(): p.cells[index]['shading'] = 2 if value else 1
                # This oracle tests number rules alone, without connectivity.
                def numbers(boxes, sources, conflicts):
                    return propagate_numbers(p.cells, boxes, sources, 3, 3, conflicts)
                p.analysis = analyze_arrows(p.cells, 3, 3, extra_rules=(numbers,))
                positions = [i for i in range(9) if i != 4]
                valid = []
                for values in itertools.product((False, True), repeat=8):
                    layout = dict(zip(positions, values))
                    if all(layout[i] == value for i, value in fixed.items()) and sum(values) + 1 == target:
                        valid.append(layout)
                self.assertEqual(bool(p.analysis.conflicts), not bool(valid))
                if valid:
                    for index in positions:
                        possible = {layout[index] for layout in valid}
                        expected = next(iter(possible)) if len(possible) == 1 else None
                        self.assertEqual(p.analysis.boxes[index], expected)


if __name__ == '__main__':
    unittest.main()
