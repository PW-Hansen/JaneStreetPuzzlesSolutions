import unittest

from functions.clue_analysis import choose_frontier_cell, frontier_priorities
from puzzle_gui import blank_grid


class FrontierPriorityTests(unittest.TestCase):
    def board(self):
        return {"rows": 5, "columns": 5, "cells": blank_grid(5, 5)}

    def test_right_of_clue_matches_three_categories(self):
        state = self.board()
        state["cells"][2][3]["number"] = 45
        state["cells"][1][4]["green"] = True
        state["cells"][3][4]["number"] = 288
        self.assertEqual(frontier_priorities(state)[(2, 4)], 3)

    def test_each_category_counts_once(self):
        state = self.board()
        state["cells"][0][1].update(green=True, number=9)
        state["cells"][1][0].update(green=True, number=9)
        self.assertEqual(frontier_priorities(state)[(0, 0)], 3)

    def test_diagonals_and_cell_itself_do_not_count_as_neighbors(self):
        state = self.board()
        state["cells"][1][1].update(green=True, number=9)
        state["cells"][2][2]["number"] = 45
        self.assertEqual(frontier_priorities(state)[(2, 2)], 0)

    def test_constraints_precede_priority(self):
        frontier = {(1, 1): {"N", "W"}, (2, 4): {"W"}}
        self.assertEqual(choose_frontier_cell(frontier, {(1, 1): 1, (2, 4): 4}), (1, 1))
        self.assertEqual(choose_frontier_cell(frontier, {(1, 1): 1, (2, 4): 1}), (1, 1))

    def test_existing_region_connection_bonus_changes_frontier_order(self):
        frontier = {(1, 1): {'N'}, (2, 4): {'N', 'W'}}
        priorities = {(1, 1): 1, (2, 4): 0}
        self.assertEqual(choose_frontier_cell(frontier, priorities), (2, 4))
        self.assertEqual(choose_frontier_cell(frontier, priorities, prioritize_connections=False), (2, 4))

    def test_connection_bonus_counts_each_neighbor(self):
        frontier = {(1, 1): {'N', 'W'}, (2, 4): {'N', 'W', 'S'}}
        priorities = {(1, 1): 1, (2, 4): 0}
        self.assertEqual(choose_frontier_cell(frontier, priorities, choice_counts={(1, 1): 1, (2, 4): 1}), (2, 4))
        self.assertEqual(choose_frontier_cell(frontier, priorities, prioritize_connections=False,
                                             choice_counts={(1, 1): 1, (2, 4): 1}), (1, 1))

    def test_legal_choice_count_precedes_priority_and_edge_count(self):
        frontier = {(1, 1): {'N', 'W'}, (2, 4): {'W'}}
        counts = {(1, 1): 3, (2, 4): 1}
        self.assertEqual(choose_frontier_cell(frontier, {(1, 1): 20, (2, 4): 0},
                                               choice_counts=counts), (2, 4))

    def test_priority_breaks_tie_between_equally_constrained_cells(self):
        frontier = {(1, 1): {'N'}, (2, 4): {'W'}}
        self.assertEqual(choose_frontier_cell(frontier, {(1, 1): 0, (2, 4): 3},
                                               choice_counts={(1, 1): 3, (2, 4): 3}), (2, 4))


if __name__ == "__main__":
    unittest.main()
