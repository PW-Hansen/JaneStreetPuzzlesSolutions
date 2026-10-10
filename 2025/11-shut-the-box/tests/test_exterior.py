import itertools
import unittest
from functions.regions import propagate_exterior, orthogonal_neighbors


def deduce_exterior(boxes, rows, columns):
    result = boxes.copy()
    sources = ['unknown' if value is None else 'manual shading' for value in boxes]
    conflicts = []
    propagate_exterior(result, sources, rows, columns, conflicts)
    return result, conflicts


def reaches_edge(nonbox, rows, columns):
    # Independent flood from real boundary cells; no padded graph or cut-vertex logic.
    reached = {index for index in nonbox if index // columns in (0, rows - 1)
               or index % columns in (0, columns - 1)}
    pending = list(reached)
    while pending:
        for neighbor in orthogonal_neighbors(pending.pop(), rows, columns):
            if neighbor in nonbox and neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    return reached == nonbox


class ExteriorTests(unittest.TestCase):
    def test_only_escape_is_claimed_as_nonbox(self):
        cells = [True, None, True, True, False, True, True, True, True]
        result, conflicts = deduce_exterior(cells, 3, 3)
        self.assertFalse(conflicts)
        self.assertFalse(result[1])

    def test_region_claims_successive_cells_to_reach_boundary(self):
        cells = [True] * 25
        cells[12] = cells[13] = False
        cells[8] = cells[3] = None
        result, conflicts = deduce_exterior(cells, 5, 5)
        self.assertFalse(conflicts)
        self.assertFalse(result[8])
        self.assertFalse(result[3])

    def test_alternative_escapes_remain_unknown(self):
        cells = [True, None, True, True, False, True, True, None, True]
        result, conflicts = deduce_exterior(cells, 3, 3)
        self.assertFalse(conflicts)
        self.assertIsNone(result[1])
        self.assertIsNone(result[7])

    def test_separate_nonbox_regions_need_not_connect_inside_grid(self):
        cells = [False, None, True, None, False,
                 True, False, True, False, True,
                 True, True, True, True, True]
        result, conflicts = deduce_exterior(cells, 3, 5)
        self.assertFalse(conflicts)
        self.assertFalse(result[1])
        self.assertFalse(result[3])

    def test_trapped_nonbox_and_diagonal_escape_report_conflict(self):
        for corner in (True, False):
            cells = [corner, True, True, True, False, True, True, True, True]
            result, conflicts = deduce_exterior(cells, 3, 3)
            self.assertTrue(conflicts)
            self.assertEqual(result, cells)

    def test_unknown_pocket_without_any_escape_is_box(self):
        cells = [True] * 9
        cells[4] = None
        result, conflicts = deduce_exterior(cells, 3, 3)
        self.assertFalse(conflicts)
        self.assertTrue(result[4])

    def test_all_boundary_cells_can_be_nonbox(self):
        cells = [None] * 9
        result, conflicts = deduce_exterior(cells, 3, 3)
        self.assertFalse(conflicts)
        self.assertEqual(result, cells)

    def test_exterior_deductions_against_exhaustive_small_layouts(self):
        # Every partial 3x3 board; enumerate every completion independently.
        for cells in itertools.product((None, False, True), repeat=9):
            fixed_no = {i for i, value in enumerate(cells) if value is False}
            unknown = [i for i, value in enumerate(cells) if value is None]
            valid = []
            for included in itertools.product((False, True), repeat=len(unknown)):
                nonbox = fixed_no | {i for i, value in zip(unknown, included) if value}
                if reaches_edge(nonbox, 3, 3): valid.append(nonbox)
            result, conflicts = deduce_exterior(list(cells), 3, 3)
            self.assertEqual(bool(conflicts), not bool(valid))
            if valid:
                for index in unknown:
                    self.assertEqual(result[index] is False, all(index in layout for layout in valid))
                    self.assertEqual(result[index] is True, all(index not in layout for layout in valid))


if __name__ == '__main__':
    unittest.main()
