import unittest

from functions.state import Session, new_grid
from functions.tower_placements import TowerPlacementSearch, apply_tower_placements


def analyze(session):
    search = TowerPlacementSearch(session)
    while not search.done:
        search.advance()
    return search


class TowerPlacementTests(unittest.TestCase):
    def test_trials_consider_groups_together_and_apply_exclusions(self):
        s = Session(new_grid("tower trials", 1, 4))
        s.pending_paths = [
            [[[0, 0, 1, 1, 0], [0, 1, 2, 2, 0]],
             [[0, 0, 1, 1, 0], [0, 2, 2, 2, 0]]],
            [[[0, 1, 2, 2, 0], [0, 3, 3, 3, 0]],
             [[0, 2, 2, 2, 0], [0, 3, 3, 3, 0]]]]
        before = s.serialize()
        search = analyze(s)
        self.assertEqual(s.serialize(), before)
        self.assertEqual(set(search.possible), {(0, 1), (0, 2)})
        self.assertEqual(set(search.impossible), {(0, 0), (0, 3)})
        self.assertTrue(apply_tower_placements(s, search))
        self.assertIn([0, 0], s.grid["non_towers"])
        self.assertIn([0, 3], s.grid["non_towers"])
        self.assertFalse(s.grid["towers"])
        self.assertEqual(len(s.undo_stack), 1)
        s.history()
        self.assertEqual(s.serialize()["grid"], before["grid"])
        self.assertEqual(s.pending_paths, before["pending_paths"])

    def test_last_possible_placement_becomes_tower(self):
        s = Session(new_grid("tower trials", 1, 3))
        s.pending_paths = [[[[0, 0, 1, 1, 0]]], [[[0, 1, 2, 2, 0]]]]
        search = analyze(s)
        self.assertEqual(search.possible, [(0, 2)])
        apply_tower_placements(s, search)
        self.assertEqual(s.grid["towers"], [[0, 2]])
        self.assertEqual(s.grid["visits"][0][0], 1)
        self.assertEqual(s.grid["visits"][0][1], 2)
        self.assertFalse(s.pending_paths)

    def test_skip_occupied_regions_and_known_non_towers(self):
        s = Session(new_grid("tower trials", 2, 3))
        s.grid["borders"] = [[0, c, 1, c] for c in range(3)]
        s.mark_tower((0, 0))
        s.mark_tower((1, 0), False)
        search = analyze(s)
        self.assertEqual(set(search.cells), {(1, 1), (1, 2)})
        self.assertEqual(set(search.possible), {(1, 1), (1, 2)})
        self.assertFalse(apply_tower_placements(s, search))

    def test_invalid_baseline_is_reported_without_changes(self):
        s = Session(new_grid("tower trials", 1, 3))
        s.pending_paths = [[[[0, 0, 1, 1, 1]]], [[[0, 1, 2, 2, 1]]]]
        before = s.serialize()
        search = analyze(s)
        self.assertFalse(search.baseline_valid)
        with self.assertRaises(ValueError):
            apply_tower_placements(s, search)
        self.assertEqual(s.serialize(), before)

    def test_incomplete_and_stale_searches_do_not_apply(self):
        s = Session(new_grid("tower trials", 1, 3))
        search = TowerPlacementSearch(s)
        self.assertFalse(apply_tower_placements(s, search))
        while not search.done:
            search.advance()
        s.mark_tower((0, 0))
        with self.assertRaises(ValueError):
            apply_tower_placements(s, search)
