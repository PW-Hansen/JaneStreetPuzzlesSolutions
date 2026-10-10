from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path
from functions.model import Puzzle
from functions.placements import attempt_placements
from functions.storage import Storage


class PlacementTests(unittest.TestCase):
    def test_real_rules_force_only_unavoidable_choices(self):
        p = Puzzle('test', 3, 3)
        p.cells[4]['digit'] = '3'
        p.cells[0]['shading'] = 2
        p.update_analysis()
        before = deepcopy(p.cells)
        self.assertFalse(p.analysis.conflicts)
        result = attempt_placements(p.cells, 3, 3)
        self.assertEqual(result.status, 'stable')
        self.assertEqual(result.forced, 4)
        for index in (2, 5, 6, 7): self.assertEqual(result.cells[index]['shading'], 1)
        for index in (1, 3): self.assertEqual(result.cells[index]['shading'], 0)
        self.assertEqual(p.cells, before)
        p.apply_placements(result.cells)
        for index in (2, 5, 6, 7, 8): self.assertFalse(p.analysis.boxes[index])
        self.assertEqual(len(p.undo_stack), 1)
        self.assertFalse(p.analysis.conflicts)
        p.undo()
        self.assertEqual(p.cells, before)
        p.redo()
        self.assertEqual(p.cells, result.cells)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            storage.save(p)
            loaded = storage.load(storage.working_path('test'))
            self.assertEqual(loaded.cells, result.cells)
            loaded.undo()
            self.assertEqual(loaded.cells, before)

    def test_both_valid_stays_unknown_and_stops_after_one_pass(self):
        p = Puzzle('test', 2, 2)
        result = attempt_placements(p.cells, 2, 2)
        self.assertEqual(result.status, 'stable')
        self.assertEqual(result.forced, 0)
        self.assertEqual(result.passes, 1)
        self.assertEqual(result.tested, 4)
        self.assertEqual(result.cells, p.cells)

    def test_retests_early_cells_in_later_passes(self):
        # A deliberately weak analyzer for two constraints: y=yes and y=>x=no.
        # It checks complete clauses, leaving x undecided until y is committed.
        def analyze(cells, rows, columns):
            x, y = (None if c['shading'] == 0 else c['shading'] == 2 for c in cells)
            conflicts = []
            if y is False: conflicts.append('y must be yes')
            if y is True and x is True: conflicts.append('y implies x is no')
            return SimpleNamespace(boxes=[x, y], conflicts=conflicts)
        p = Puzzle('test', 1, 2)
        with patch('functions.placements.analyze_grid', side_effect=analyze):
            result = attempt_placements(p.cells, 1, 2)
        self.assertEqual(result.status, 'stable')
        self.assertEqual(result.passes, 3)
        self.assertEqual(result.forced, 2)
        self.assertEqual([c['shading'] for c in result.cells], [1, 2])

    def test_both_invalid_reports_cell_without_committing_a_branch(self):
        def analyze(cells, rows, columns):
            box = None if cells[0]['shading'] == 0 else cells[0]['shading'] == 2
            return SimpleNamespace(boxes=[box], conflicts=[] if box is None else ['test contradiction'])
        p = Puzzle('test', 1, 1)
        with patch('functions.placements.analyze_grid', side_effect=analyze):
            result = attempt_placements(p.cells, 1, 1)
        self.assertEqual(result.status, 'contradiction')
        self.assertEqual(result.failed_cell, 0)
        self.assertEqual(result.cells, p.cells)
        self.assertEqual(len(result.conflicts), 2)

    def test_initial_contradiction_is_reported_separately(self):
        p = Puzzle('test', 1, 1)
        p.edit(0, 'Digit Entering', digit='2')
        result = attempt_placements(p.cells, 1, 1)
        self.assertEqual(result.status, 'invalid')
        self.assertEqual(result.tested, 0)
        self.assertTrue(result.conflicts)

    def test_cancel_between_branches_does_not_commit_speculation(self):
        p = Puzzle('test', 2, 2)
        stop = [False]
        def progress(item): stop[0] = True
        result = attempt_placements(p.cells, 2, 2, cancelled=lambda: stop[0], progress=progress)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(result.cells, p.cells)
        self.assertEqual(result.tested, 0)

    def test_cancel_retains_earlier_forced_placements(self):
        p = Puzzle('test', 3, 3)
        p.cells[4]['digit'] = '3'
        p.cells[0]['shading'] = 2
        stop = [False]
        def progress(item):
            if item.assignment is None: stop[0] = True
        result = attempt_placements(p.cells, 3, 3, cancelled=lambda: stop[0], progress=progress)
        self.assertEqual(result.status, 'cancelled')
        self.assertEqual(result.forced, 1)
        self.assertEqual(result.cells[2]['shading'], 1)
        self.assertEqual(p.cells[2]['shading'], 0)


if __name__ == '__main__':
    unittest.main()
