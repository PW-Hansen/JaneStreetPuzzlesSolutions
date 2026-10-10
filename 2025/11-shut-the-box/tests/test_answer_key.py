import unittest
from types import SimpleNamespace
from functions.answer_key import compute_answer_key
from functions.constants import FACE_COLORS
from functions.model import blank_cell


class AnswerKeyTests(unittest.TestCase):
    def fixture(self):
        cells = []
        for face, digit in zip(FACE_COLORS, '123456'):
            cell = blank_cell()
            cell.update(shading=2, face=face, digit=digit)
            cells.append(cell)
        return SimpleNamespace(cells=cells, analysis=SimpleNamespace(conflicts=[]))

    def test_sums_and_product_include_each_number_once(self):
        puzzle = self.fixture()
        extra = blank_cell()
        extra.update(shading=2, face='+X', digit='7', shape='circle')
        puzzle.cells.append(extra)
        result = compute_answer_key(puzzle)
        self.assertEqual(result.face_sums['+X'], 8)
        self.assertEqual(result.value, 5760)
        self.assertIn('Answer key:', result.report())
        self.assertIn('= 5760', result.report())

    def test_face_without_numbers_has_zero_sum(self):
        puzzle = self.fixture()
        puzzle.cells[0]['digit'] = None
        result = compute_answer_key(puzzle)
        self.assertEqual(result.face_sums['+X'], 0)
        self.assertEqual(result.value, 0)

    def test_outside_and_blank_face_cells_add_nothing(self):
        puzzle = self.fixture()
        outside = blank_cell()
        outside['shading'] = 1
        blank = blank_cell()
        blank.update(shading=2, face='+X')
        puzzle.cells.extend([outside, blank])
        self.assertEqual(compute_answer_key(puzzle).value, 720)

    def test_incomplete_or_conflicting_states_rejected(self):
        for kind in ('unknown', 'face', 'missing', 'conflict'):
            with self.subTest(kind=kind):
                puzzle = self.fixture()
                if kind == 'unknown': puzzle.cells.append(blank_cell())
                elif kind == 'face': puzzle.cells[0].pop('face')
                elif kind == 'missing': puzzle.cells.pop()
                else: puzzle.analysis.conflicts.append('contradiction')
                with self.assertRaises(ValueError): compute_answer_key(puzzle)
