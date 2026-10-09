import unittest

from functions.path_completion import CompletionSearch
from functions.path_combinations import CombinationSearch
from functions.state import Session, new_grid


def complete(grid):
    search = CompletionSearch(grid)
    while not search.done:
        search.advance()
    return search.possible


class CompletionTests(unittest.TestCase):
    def test_remaining_tower_must_be_reachable(self):
        s = Session(new_grid("completion", 1, 3))
        s.grid["scores"][0][0] = 2
        s.grid["visits"][0][0] = 0
        s.mark_tower((0, 2))
        self.assertTrue(complete(s.grid))
        s.grid["visits"][0][0] = None
        s.grid["visits"][0][1] = 0
        s.grid["scores"][0][1] = 2
        self.assertFalse(complete(s.grid))

    def test_cannot_revisit_a_cell_to_reach_remaining_tower(self):
        s = Session(new_grid("completion", 1, 5))
        s.grid["borders"] = [[0, 1, 0, 2]]
        s.mark_tower((0, 0))
        s.mark_tower((0, 4))
        s.grid["visits"][0] = [0, None, 1, 2, None]
        s.grid["scores"][0] = [2, None, 2, 4, None]
        self.assertFalse(complete(s.grid))

    def test_all_towers_already_visited_is_valid(self):
        s = Session(new_grid("completion", 1, 3))
        s.mark_tower((0, 0))
        s.grid["scores"][0][0] = 0
        s.grid["visits"][0][0] = 0
        self.assertTrue(complete(s.grid))

    def test_disconnected_fragments_are_not_treated_as_a_finished_prefix(self):
        s = Session(new_grid("completion", 1, 3))
        s.mark_tower((0, 2))
        s.grid["visits"][0][1] = 9
        s.grid["scores"][0][1] = 23
        self.assertTrue(complete(s.grid))

    def test_combinations_reject_a_trapped_prefix_and_keep_a_completable_one(self):
        s = Session(new_grid("completion", 1, 3))
        s.pending_paths = [[[[0, 0, 2, 0, 0], [0, 2, 3, 1, 0]],
                            [[0, 0, 2, 0, 0], [0, 2, 2, 1, 1]]]]
        search = CombinationSearch(s)
        while not search.done:
            search.advance()
        self.assertEqual(len(search.combinations), 1)
        self.assertIn([0, 2, 2, 1, 1], search.combinations[0])
