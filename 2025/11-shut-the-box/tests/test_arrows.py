import itertools
import tempfile
import unittest
from pathlib import Path
from functions.arrows import analyze_arrows
from functions.model import Puzzle
from functions.storage import Storage


class ArrowTests(unittest.TestCase):
    def test_clue_membership_and_no_manual_overwrite(self):
        p = Puzzle('test', 2, 3)
        p.edit(2, 'Digit Entering', digit='4')
        p.edit(0, 'Arrow Entering', direction='south')
        self.assertTrue(p.analysis.boxes[2])
        self.assertFalse(p.analysis.boxes[0])
        self.assertTrue(p.analysis.boxes[3])
        self.assertEqual(p.cells[3]['shading'], 0)
        self.assertEqual(p.display_cells()[3]['shading'], 2)

    def test_equal_distance_and_unmarked_ties(self):
        p = Puzzle('test', 5, 5)
        p.edit(12, 'Arrow Entering', direction='north')
        p.edit(12, 'Arrow Entering', direction='east')
        p.edit(2, 'Shading')  # no at distance 2 in a pointed direction
        self.assertTrue(p.analysis.boxes[7])
        self.assertTrue(p.analysis.boxes[13])
        self.assertFalse(p.analysis.boxes[11])
        self.assertFalse(p.analysis.boxes[17])
        self.assertEqual(p.analysis.distances[12], [1])
        self.assertIsNone(p.analysis.boxes[14])  # beyond the nearest distance

    def test_farther_distance_and_retraction(self):
        p = Puzzle('test', 1, 5)
        p.edit(1, 'Arrow Entering', direction='east')
        self.assertFalse(p.analysis.boxes[0])
        self.assertIsNone(p.analysis.boxes[2])
        p.edit(2, 'Shading')
        p.edit(3, 'Shading')
        self.assertTrue(p.analysis.boxes[4])
        p.undo()
        self.assertIsNone(p.analysis.boxes[4])
        p.redo()
        self.assertTrue(p.analysis.boxes[4])
        p.edit(3, 'Shading', action='clear')
        self.assertIsNone(p.analysis.boxes[4])

    def test_contradictions(self):
        p = Puzzle('test', 2, 2)
        p.edit(0, 'Arrow Entering', direction='north')
        self.assertTrue(p.analysis.conflicts)
        self.assertEqual(p.analysis.distances[0], [])
        p.edit(0, 'Arrow Entering', action='clear')
        self.assertFalse(p.analysis.conflicts)
        p.edit(0, 'Digit Entering', digit='2')
        p.edit(0, 'Shading')
        self.assertTrue(p.analysis.conflicts)
        self.assertFalse(p.analysis.boxes[0])  # preserve conflicting manual input

    def test_propagation_between_clues(self):
        p = Puzzle('test', 3, 4)
        p.edit(0, 'Arrow Entering', direction='east')
        p.edit(5, 'Arrow Entering', direction='north')
        self.assertTrue(p.analysis.boxes[1])
        self.assertEqual(p.analysis.distances[0], [1])
        self.assertFalse(p.analysis.boxes[4])
        self.assertFalse(p.analysis.boxes[8])

    def test_save_load_and_reset_recompute(self):
        p = Puzzle('test', 1, 4)
        p.edit(0, 'Arrow Entering', direction='east')
        p.edit(1, 'Shading')
        p.edit(2, 'Shading')
        self.assertTrue(p.analysis.boxes[3])
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            storage.save(p)
            loaded = storage.load(storage.working_path(p.name))
            self.assertEqual(loaded.analysis, p.analysis)
            loaded.reset(shading_only=True)
            self.assertIsNone(loaded.analysis.boxes[3])
            loaded.undo()
            self.assertTrue(loaded.analysis.boxes[3])

    def test_single_arrow_against_exhaustive_assignments(self):
        # Independent enumeration of complete box layouts, not the propagator's rays.
        for indicated in ({'east'}, {'north', 'east'}, {'north', 'east', 'south', 'west'}):
            p = Puzzle('test', 3, 3)
            p.cells[4]['arrows'] = list(indicated)
            positions = [index for index in range(9) if index != 4]
            for fixed in ({}, {1: False}, {5: True}, {1: True, 5: False}):
                for index in positions:
                    p.cells[index]['shading'] = 0 if index not in fixed else 2 if fixed[index] else 1
                result = analyze_arrows(p.cells, 3, 3)
                valid = []
                for values in itertools.product((False, True), repeat=8):
                    boxes = dict(zip(positions, values))
                    if any(boxes[index] != value for index, value in fixed.items()): continue
                    visible = []
                    for index, value in boxes.items():
                        if not value: continue
                        row, column = divmod(index, 3)
                        if row == 1:
                            visible.append((abs(column - 1), 'east' if column > 1 else 'west'))
                        elif column == 1:
                            visible.append((abs(row - 1), 'south' if row > 1 else 'north'))
                    if not visible: continue
                    distance = min(d for d, _ in visible)
                    nearest = {direction for d, direction in visible if d == distance}
                    if nearest == indicated: valid.append(boxes)
                self.assertEqual(bool(result.conflicts), not bool(valid))
                if valid:
                    for index in positions:
                        possible = {boxes[index] for boxes in valid}
                        expected = next(iter(possible)) if len(possible) == 1 else None
                        self.assertEqual(result.boxes[index], expected)


if __name__ == '__main__':
    unittest.main()
