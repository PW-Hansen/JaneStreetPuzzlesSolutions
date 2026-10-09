import unittest

from functions.path_combinations import CombinationSearch, apply_combinations
from functions.state import Session, new_grid


def search(session):
    result = CombinationSearch(session)
    while not result.done:
        result.advance()
    return result


class CombinationTests(unittest.TestCase):
    def test_cell_conflict_and_later_elimination_preserve_combinations(self):
        s = Session(new_grid("combinations", 2, 3))
        s.pending_paths = [
            [[[0, 0, 10, 1, 0]], [[0, 1, 10, 1, 0]]],
            [[[0, 0, 20, 2, 0]], [[1, 2, 20, 2, 0]]]]
        result = search(s)
        self.assertEqual(len(result.combinations), 3)
        self.assertTrue(apply_combinations(s, result))
        self.assertEqual(len(s.pending_paths), 1)
        self.assertEqual(len(s.pending_paths[0]), 3)
        s.select((0, 1))
        s.mode = "Score"
        s.set_value(99)
        self.assertEqual(s.grid["visits"][0][0], 1)
        self.assertEqual(s.grid["visits"][1][2], 2)
        self.assertFalse(s.pending_paths)
        s.history()
        self.assertEqual(len(s.pending_paths[0]), 3)
        s.history()
        self.assertEqual(len(s.pending_paths), 2)

    def test_two_towers_in_one_region_rejected(self):
        s = Session(new_grid("combinations", 2, 3))
        s.pending_paths = [[[[0, 0, 10, 1, 1]]], [[[1, 2, 20, 2, 1]]]]
        before = s.serialize()
        result = search(s)
        self.assertFalse(result.combinations)
        self.assertFalse(apply_combinations(s, result))
        self.assertEqual(s.serialize(), before)

    def test_region_with_all_non_towers_rejected(self):
        s = Session(new_grid("combinations", 1, 3))
        s.pending_paths = [[[[0, 0, 10, 1, 0]]],
                           [[[0, 1, 20, 2, 0], [0, 2, 30, 3, 0]]]]
        self.assertFalse(search(s).combinations)

    def test_unique_combination_applies_and_infers_remaining_tower(self):
        s = Session(new_grid("combinations", 2, 3))
        s.pending_paths = [
            [[[0, 0, 10, 1, 1]], [[0, 1, 10, 1, 0]]],
            [[[1, 2, 20, 2, 1]]]]
        result = search(s)
        self.assertEqual(len(result.combinations), 1)
        self.assertTrue(apply_combinations(s, result))
        self.assertEqual(s.grid["visits"][0][1], 1)
        self.assertEqual(s.grid["visits"][1][2], 2)
        self.assertIn([1, 2], s.grid["towers"])
        self.assertFalse(s.pending_paths)
        self.assertEqual(len(s.undo_stack), 1)

    def test_shared_endpoint_is_not_a_revisit(self):
        s = Session(new_grid("combinations", 2, 3))
        s.pending_paths = [[[[0, 0, 10, 1, 0], [0, 1, 20, 2, 0]]],
                           [[[0, 1, 20, 2, 0], [1, 2, 30, 3, 0]]]]
        result = search(s)
        self.assertEqual(len(result.combinations), 1)
        self.assertEqual(len(result.combinations[0]), 3)

    def test_incomplete_and_stale_search_cannot_apply(self):
        s = Session(new_grid("combinations", 2, 3))
        s.pending_paths = [[[[0, 0, 10, 1, 0]]]]
        result = CombinationSearch(s)
        self.assertFalse(apply_combinations(s, result))
        while not result.done:
            result.advance()
        s.pending_paths = []
        with self.assertRaises(ValueError):
            apply_combinations(s, result)
