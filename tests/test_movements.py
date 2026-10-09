import unittest

from functions.movements import MovementSearch


def results(score, visit, moves=3):
    search = MovementSearch(score, visit, moves)
    found = {}
    while search.worklist:
        result = search.advance()
        if result is not None:
            found[result[2]] = result[0]
    return found


class MovementTests(unittest.TestCase):
    def test_first_move_uses_one_and_retains_all_sequences(self):
        self.assertEqual(results(0, 0, 1), {"+": 1, "*": 0, "/": 0})

    def test_exact_depth_and_operations(self):
        found = results(0, 0)
        self.assertEqual(found["+++"], 6)
        self.assertEqual(found["/*/"], 0)
        self.assertTrue(all(len(operations) == 3 for operations in found))
        self.assertNotIn("+*/", found)  # 1 * 2 / 3 is fractional.

    def test_addition_does_not_reset_multiply_or_divide(self):
        found = results(0, 0)
        for operations in ("**+", "*+*", "//*", "/+/"):
            self.assertNotIn(operations, found)
        self.assertIn("*/*", found)
        self.assertIn("/*/", found)

    def test_offset_visit_and_integer_division(self):
        self.assertEqual(results(8, 3, 1), {"+": 12, "*": 32, "/": 2})
        self.assertEqual(results(7, 3, 1), {"+": 11, "*": 28})

    def test_zero_lookahead_and_invalid_inputs(self):
        self.assertEqual(results(5, 9, 0), {"": 5})
        for args in ((None, 0), (0, None), (0, -1), (0, 0, -1), (0, 0, 1.5)):
            with self.assertRaises(ValueError):
                MovementSearch(*args)
