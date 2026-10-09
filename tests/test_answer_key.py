import unittest

from functions.answer_key import compute_answer_key
from functions.state import new_grid


class AnswerKeyTests(unittest.TestCase):
    def test_neighbor_sums_use_visits_not_presence_of_scores(self):
        grid = new_grid("answer", 2, 3)
        grid["scores"] = [[5, 99, 7], [4, 3, None]]
        grid["visits"] = [[0, None, 1], [None, 2, None]]
        grid["borders"] = [[0, 0, 0, 1]]
        self.assertEqual(compute_answer_key(grid), 33)

    def test_each_unvisited_neighbor_counts_the_score_separately(self):
        grid = new_grid("answer", 1, 3)
        grid["scores"][0] = [None, 7, None]
        grid["visits"][0] = [None, 0, None]
        self.assertEqual(compute_answer_key(grid), 14)

    def test_diagonal_neighbors_are_excluded(self):
        grid = new_grid("answer", 2, 2)
        grid["scores"][0][0] = 10
        grid["visits"][0][0] = 0
        self.assertEqual(compute_answer_key(grid), 20)

    def test_missing_visited_score_is_rejected(self):
        grid = new_grid("answer", 1, 2)
        grid["visits"][0][0] = 0
        with self.assertRaises(ValueError):
            compute_answer_key(grid)

    def test_no_unvisited_cells_produces_zero(self):
        grid = new_grid("answer", 1, 2)
        grid["scores"][0] = [0, 1]
        grid["visits"][0] = [0, 1]
        self.assertEqual(compute_answer_key(grid), 0)
