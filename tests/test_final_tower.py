import unittest

from functions.final_tower import FinalTowerSearch, apply_final_tower
from functions.state import Session, new_grid


def board(columns, start, tower=None):
    s = Session(new_grid("final tower", 1, columns))
    s.grid["scores"][0][start] = 2
    s.grid["visits"][0][start] = 0
    s.mark_tower((0, start), False)
    if tower is not None:
        s.mark_tower((0, tower))
    return s


def analyze(s):
    search = FinalTowerSearch(s)
    while not search.done:
        search.advance()
    return search


class FinalTowerTests(unittest.TestCase):
    def test_confirmed_and_unknown_final_tower_apply_unique_path(self):
        for tower in (None, 2):
            with self.subTest(tower=tower):
                s = board(3, 0, tower)
                before = s.grid.copy()
                search = analyze(s)
                self.assertEqual(search.paths, [[[0, 0, 2, 0, 0], [0, 2, 2, 1, 1]]])
                self.assertTrue(apply_final_tower(s, search))
                self.assertEqual(s.grid["visits"][0][2], 1)
                self.assertIn([0, 2], s.grid["towers"])
                s.history()
                self.assertEqual(s.grid, before)

    def test_multiple_paths_retained_and_can_resolve_later(self):
        s = board(5, 2)
        search = analyze(s)
        self.assertEqual(len(search.paths), 2)
        self.assertTrue(apply_final_tower(s, search))
        self.assertEqual(len(s.pending_paths[0]), 2)
        self.assertIsNone(s.grid["visits"][0][0])
        s.mark_tower((0, 0), False)
        self.assertEqual(s.grid["visits"][0][4], 1)
        self.assertIn([0, 4], s.grid["towers"])

    def test_unreachable_final_tower_leaves_grid_unchanged(self):
        s = board(3, 1, 2)
        before = s.serialize()
        search = analyze(s)
        self.assertFalse(search.paths)
        self.assertFalse(apply_final_tower(s, search))
        self.assertEqual(s.serialize(), before)

    def test_final_paths_respect_retained_path_constraints(self):
        s = board(5, 2)
        s.pending_paths = [[[[0, 0, 2, 1, 1]]]]
        search = analyze(s)
        self.assertEqual(len(search.paths), 1)
        self.assertEqual(search.paths[0][-1], [0, 0, 2, 1, 1])

    def test_requires_continuous_visits_and_one_remaining_region(self):
        s = board(3, 0)
        s.grid["visits"][0][0] = 3
        with self.assertRaises(ValueError):
            FinalTowerSearch(s)
        s.grid["visits"][0][0] = 0
        s.grid["borders"] = [[0, 1, 0, 2]]
        with self.assertRaises(ValueError):
            FinalTowerSearch(s)

    def test_stale_and_incomplete_results_do_not_apply(self):
        s = board(3, 0)
        search = FinalTowerSearch(s)
        self.assertFalse(apply_final_tower(s, search))
        while not search.done:
            search.advance()
        s.mark_tower((0, 2))
        with self.assertRaises(ValueError):
            apply_final_tower(s, search)
