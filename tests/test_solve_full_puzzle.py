import unittest
from fractions import Fraction
from unittest.mock import patch

from solve_full_puzzle import solve
from functions.solve_functions import is_solution, region_complete_in_all


class FullPuzzleRunnerTests(unittest.TestCase):
    def test_skip_requires_complete_regions_in_every_candidate(self):
        states = [{'cells': {8}, 'assumptions': {0: 2, 1: 2}},
                  {'cells': {9}, 'assumptions': {0: 2, 1: 2}}]
        self.assertTrue(region_complete_in_all(2, states, {}, 3))
        states[1]['assumptions'] = {0: 2, 2: 2}
        self.assertTrue(region_complete_in_all(2, states, {}, 3))
        states[1]['assumptions'] = {0: 2}
        self.assertFalse(region_complete_in_all(2, states, {}, 3))
        self.assertFalse(region_complete_in_all(2, [], {}, None))

    def test_runner_calls_requested_operations_in_order_and_skips_completed_regions(self):
        calls = []
        candidate = {'cells': frozenset(), 'assumptions': {0: 1}}
        def first(expressions, variables, progress, region):
            calls.append(region)
            return region, {0: 1}, [candidate], 1
        def next_region(size, base, current, states, progress, region):
            calls.append(region)
            return region, [candidate], 1
        def compare(*args):
            calls.append('compare')
            return [candidate]
        def complete(*args):
            calls.append('complete')
            return [candidate]
        with patch('functions.solve_functions.analyze_clues', return_value=([{'a': Fraction(1)}], [])), \
             patch('functions.solve_functions.find_region_overlays', side_effect=first), \
             patch('functions.solve_functions.continue_region_overlays', side_effect=next_region), \
             patch('functions.solve_functions.compare_incomplete_regions', side_effect=compare), \
             patch('functions.solve_functions.attempt_region_completions', side_effect=complete):
            saved, solutions = solve({'size': 1, 'expressions': [['a']], 'variables': {'a': '0'}}, log=lambda _: None)
        self.assertEqual(calls, [12, 13, 14, 15, 16, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 'compare', 'complete'])
        self.assertEqual(solutions, 1)
        self.assertEqual(saved['variables'], {'a': '1'})

    def test_solution_check_rejects_wrong_counts_and_disconnected_shapes(self):
        self.assertTrue(is_solution(3, {0: 1, 3: 2, 4: 2}, {0: 1}))
        self.assertFalse(is_solution(3, {0: 1, 3: 2, 8: 2}, {0: 1}))
        self.assertFalse(is_solution(3, {0: 1, 3: 2}, {0: 1}))
        self.assertFalse(is_solution(3, {0: 1, 3: 2, 4: 2}, {0: 2}))

    def test_solution_check_rejects_invalid_values_and_cell_positions(self):
        for board in ({0: 0}, {0: -1}, {0: True}, {0: 1.0},
                      {0: 1, 1: 0}, {-1: 1}, {9: 1}, {'0': 1}):
            with self.subTest(board=board):
                self.assertFalse(is_solution(3, board, {}))


if __name__ == '__main__':
    unittest.main()
