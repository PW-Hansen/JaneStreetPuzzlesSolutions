import unittest

from functions.clue_analysis import compatible_factorizations, minimum_perimeter_pieces
from functions.incremental_analysis import analyze_clue_incremental
from puzzle_gui import blank_grid, clue_factorizations


class FactorizationAnalysisTests(unittest.TestCase):
    def board(self, rows, columns, clue):
        state = {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}
        state["cells"][0][0]["number"] = clue
        return state

    def test_25_rejects_area_above_five_with_a_confirmed_sharp_join(self):
        pairs = tuple(clue_factorizations(self.board(6, 6, 25), (0, 0)))
        self.assertEqual(pairs, ((1, 25), (5, 5), (25, 1)))
        self.assertEqual(compatible_factorizations(pairs, 6, minimum_perimeter_pieces(0)), ((25, 1),))
        self.assertEqual(compatible_factorizations(pairs, 6, minimum_perimeter_pieces(1)), ())
        self.assertEqual(compatible_factorizations(pairs, 5, minimum_perimeter_pieces(1)), ((5, 5),))

    def test_area_and_perimeter_bounds_must_fit_the_same_pair(self):
        self.assertEqual(compatible_factorizations(((1, 25), (5, 5), (25, 1)), 6, 3), ())
        self.assertEqual(compatible_factorizations(((1, 25), (5, 5), (25, 1)), 3, 6), ())
        self.assertEqual(minimum_perimeter_pieces(4), 4)

    def test_search_records_pairs_and_reports_pruning(self):
        state = self.board(4, 4, 9)
        result = analyze_clue_incremental(state, (0, 0))
        self.assertEqual(result.factorizations, ((1, 9), (3, 3), (9, 1)))
        self.assertGreater(result.factorization_pruned, 0)
        self.assertTrue(all(isinstance(area, int) and isinstance(pieces, int)
                            for area, pieces in result.factorizations))


if __name__ == "__main__":
    unittest.main()
