import unittest
from functions.model import Puzzle
from functions.folding import cuboid_surface, fold_region
from functions.fold_application import apply_unique_fold
from functions.constants import FACE_COLORS


class FoldApplicationTests(unittest.TestCase):
    def fixture(self):
        puzzle = Puzzle('fold-test', 6, 8)
        blocks = {(0, 1), (1, 0), (1, 1), (1, 2), (1, 3), (2, 1)}
        net = {r*8+c for r in range(6) for c in range(8) if (r//2, c//2) in blocks}
        boxes = [i in net for i in range(48)]
        for surface in cuboid_surface((2, 2, 2)):
            trial = fold_region(net, boxes, 6, 8, 18, (2, 2, 2), surface, 0)
            if trial.reason is None:
                return puzzle, trial
        self.fail('No cube net placement')

    def test_unique_fold_applies_membership_and_six_faces(self):
        puzzle, trial = self.fixture()
        self.assertTrue(apply_unique_fold(puzzle, [trial]))
        self.assertEqual(len(puzzle.undo_stack), 1)
        self.assertEqual({cell.get('face') for cell in puzzle.cells if cell['shading'] == 2}, set(FACE_COLORS))
        for index, cell in enumerate(puzzle.cells):
            self.assertEqual(cell['shading'], 2 if index in trial.mapping else 1)
            self.assertEqual('face' in cell, index in trial.mapping)
        self.assertFalse(puzzle.analysis.conflicts)
        self.assertFalse(apply_unique_fold(puzzle, [trial]))
        self.assertEqual(len(puzzle.undo_stack), 1)

    def test_cancelled_multiple_and_empty_results_do_not_apply(self):
        puzzle, trial = self.fixture()
        before = puzzle.to_dict()
        for survivors, complete in (([], True), ([trial, trial], True), ([trial], False)):
            self.assertFalse(apply_unique_fold(puzzle, survivors, complete))
            self.assertEqual(puzzle.to_dict(), before)

    def test_history_and_serialization_preserve_faces(self):
        puzzle, trial = self.fixture()
        puzzle.apply_fold(trial)
        applied = puzzle.cells.copy()
        restored = Puzzle.from_dict(puzzle.to_dict())
        self.assertEqual(restored.cells, applied)
        self.assertTrue(restored.undo())
        self.assertTrue(all(cell['shading'] == 0 and 'face' not in cell for cell in restored.cells))
        self.assertTrue(restored.redo())
        self.assertEqual(restored.cells, applied)
        self.assertTrue(restored.edit(18, 'Digit Entering', digit='4'))
        self.assertTrue(all('face' not in cell for cell in restored.cells))
        restored.undo()
        self.assertEqual(restored.cells, applied)

    def test_incomplete_or_conflicting_fold_cannot_apply(self):
        puzzle, trial = self.fixture()
        original = trial.mapping.copy()
        trial.mapping.pop(18)
        with self.assertRaises(ValueError): puzzle.apply_fold(trial)
        self.assertFalse(puzzle.undo_stack)
        trial.mapping = original
        puzzle.cells[18]['shading'] = 1
        puzzle.update_analysis()
        with self.assertRaises(ValueError): puzzle.apply_fold(trial)

    def test_invalid_face_metadata_rejected(self):
        puzzle, trial = self.fixture()
        puzzle.apply_fold(trial)
        data = puzzle.to_dict()
        data['cells'][18]['face'] = 'invalid'
        with self.assertRaises(ValueError): Puzzle.from_dict(data)
