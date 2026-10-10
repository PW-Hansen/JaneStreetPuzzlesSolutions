import itertools
import tempfile
import unittest
from pathlib import Path
from functions.regions import propagate_regions, orthogonal_neighbors
from functions.model import Puzzle
from functions.storage import Storage


def deduce(boxes, rows, columns):
    result = boxes.copy()
    sources = ['manual shading' if value is not None else 'unknown' for value in boxes]
    conflicts = []
    propagate_regions(result, sources, rows, columns, conflicts)
    return result, conflicts


def connected(indices, rows, columns):
    if not indices: return True
    seen = {next(iter(indices))}
    pending = list(seen)
    while pending:
        for neighbor in orthogonal_neighbors(pending.pop(), rows, columns):
            if neighbor in indices and neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return seen == indices


class RegionTests(unittest.TestCase):
    def test_single_cell_corridor(self):
        result, conflicts = deduce([True, None, None, None, True], 1, 5)
        self.assertFalse(conflicts)
        self.assertEqual(result, [True] * 5)

    def test_dead_end_does_not_count_as_an_escape(self):
        # An unknown pocket branches off the only corridor connecting the greens.
        cells = [False, None, False, False, True, None, None, True, False, None, False, False]
        result, conflicts = deduce(cells, 3, 4)
        self.assertFalse(conflicts)
        self.assertTrue(result[5])
        self.assertTrue(result[6])
        self.assertIsNone(result[1])
        self.assertIsNone(result[9])

    def test_sequential_exits_connect_multiple_regions(self):
        # A lone green must grow upward into a group, then that group upward.
        cells = [False, True, False, False,
                 False, None, False, False,
                 False, True, True, False,
                 False, None, False, False,
                 False, True, False, False]
        result, conflicts = deduce(cells, 5, 4)
        self.assertFalse(conflicts)
        self.assertTrue(result[5])
        self.assertTrue(result[13])

    def test_two_routes_do_not_force_a_chosen_route(self):
        result, conflicts = deduce([True, None, None, True], 2, 2)
        self.assertFalse(conflicts)
        self.assertIsNone(result[1])
        self.assertIsNone(result[2])

    def test_disconnected_regions_and_diagonal_contact(self):
        result, conflicts = deduce([True, False, False, True], 2, 2)
        self.assertTrue(conflicts)
        self.assertEqual(result, [True, False, False, True])
        result, conflicts = deduce([True, None, False, None, True], 1, 5)
        self.assertTrue(conflicts)
        self.assertIsNone(result[1])

    def test_one_connected_region_does_not_grow_without_need(self):
        for cells in ([True, None, None], [True, True, None], [None, None, None]):
            result, conflicts = deduce(list(cells), 1, 3)
            self.assertFalse(conflicts)
            self.assertEqual(result, list(cells))

    def test_edit_retraction_history_and_snapshot(self):
        p = Puzzle('test', 2, 2)
        for index in (0, 3):
            p.edit(index, 'Shading')
            p.edit(index, 'Shading')
        p.edit(1, 'Shading')
        self.assertTrue(p.analysis.boxes[2])
        self.assertEqual(p.analysis.sources[2], 'region rules')
        self.assertEqual(p.cells[2]['shading'], 0)
        p.undo()
        self.assertIsNone(p.analysis.boxes[2])
        p.redo()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            storage.save(p)
            loaded = storage.load(storage.working_path('test'))
            self.assertEqual(loaded.analysis, p.analysis)
            loaded.edit(1, 'Shading', action='clear')
            self.assertIsNone(loaded.analysis.boxes[2])

    def test_large_corridor_does_not_use_python_recursion(self):
        cells = [None] * 2000
        cells[0] = cells[-1] = True
        result, conflicts = deduce(cells, 1, 2000)
        self.assertFalse(conflicts)
        self.assertTrue(all(result))

    def test_surrounded_unknown_pocket_is_no(self):
        cells = [True, False, False, False,
                 False, None, None, False,
                 False, None, None, False,
                 False, False, False, False]
        result, conflicts = deduce(cells, 4, 4)
        self.assertFalse(conflicts)
        for index in (5, 6, 9, 10): self.assertFalse(result[index])

    def test_boundary_and_diagonal_only_pockets_are_no(self):
        result, conflicts = deduce([True, False, None, False, None, None], 2, 3)
        self.assertFalse(conflicts)
        self.assertEqual(result, [True, False, False, False, False, False])

    def test_unknown_pocket_with_possible_exit_stays_unknown(self):
        cells = [True, None, None, False, None, None]
        result, conflicts = deduce(cells, 2, 3)
        self.assertFalse(conflicts)
        self.assertEqual(result, cells)

    def test_pocket_deduction_retracts_when_wall_is_cleared(self):
        p = Puzzle('test', 1, 3)
        p.edit(0, 'Shading')
        p.edit(0, 'Shading')
        p.edit(1, 'Shading')
        self.assertFalse(p.analysis.boxes[2])
        self.assertEqual(p.analysis.sources[2], 'region rules')
        self.assertEqual(p.cells[2]['shading'], 0)
        p.edit(1, 'Shading', action='clear')
        self.assertIsNone(p.analysis.boxes[2])
        p.undo()
        self.assertFalse(p.analysis.boxes[2])
        p.redo()
        self.assertIsNone(p.analysis.boxes[2])

    def test_region_deductions_against_all_small_connected_layouts(self):
        for cells in itertools.product((None, False, True), repeat=6):
            greens = {i for i, value in enumerate(cells) if value is True}
            if not greens: continue
            unknown = [i for i, value in enumerate(cells) if value is None]
            valid = []
            for included in itertools.product((False, True), repeat=len(unknown)):
                layout = greens | {i for i, value in zip(unknown, included) if value}
                if connected(layout, 2, 3): valid.append(layout)
            result, conflicts = deduce(list(cells), 2, 3)
            self.assertEqual(bool(conflicts), not bool(valid))
            if valid:
                for index in unknown:
                    forced_yes = all(index in layout for layout in valid)
                    self.assertEqual(result[index] is True, forced_yes)
                    forced_no = all(index not in layout for layout in valid)
                    self.assertEqual(result[index] is False, forced_no)


if __name__ == '__main__':
    unittest.main()
