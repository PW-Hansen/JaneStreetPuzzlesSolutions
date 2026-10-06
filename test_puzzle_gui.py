import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from puzzle_gui import (GridCanvas, PuzzleApp, format_candidates,
                        read_state, valid_combinations, write_state,
                        can_connect_region, check_grid_connectivity, connectivity_candidates)


class VariableSearchTests(unittest.TestCase):
    def test_connectivity_filters_lists_without_losing_valid_partner(self):
        # a=1 is invalid with b=1, but remains valid with b=2 or b=3.
        count, values, first = connectivity_candidates(
            [['a', 'b', ''], ['', '', ''], ['', '', '']],
            {'a': (1, 3), 'b': (1, 3)})
        self.assertEqual(count, 8)
        self.assertEqual(values, {'a': {1, 2, 3}, 'b': {1, 2, 3}})
        self.assertEqual(first, {'a': 1, 'b': 2})

    def test_connectivity_removes_values_with_no_surviving_combination(self):
        count, values, _ = connectivity_candidates(
            [['a', '', 'a'], ['', '', ''], ['', '', '']], {'a': (1, 3)})
        self.assertEqual(count, 1)
        self.assertEqual(values, {'a': {3}})
        count, values, _ = connectivity_candidates([['a', 'a'], ['', '']], {'a': (1, 1)})
        self.assertEqual(count, 0)
        self.assertEqual(values, {'a': set()})
    def test_connectivity_counts_reject_before_search(self):
        with patch('puzzle_gui.can_connect_region') as search:
            passed, message = check_grid_connectivity([['1', '1'], ['', '']], {})
            self.assertFalse(passed)
            self.assertIn('at most 1', message)
            search.assert_not_called()

    def test_connectivity_blank_bridge_and_obstacle(self):
        self.assertTrue(check_grid_connectivity(
            [['3', '', '3'], ['', '', ''], ['', '', '']], {})[0])
        self.assertFalse(check_grid_connectivity(
            [['3', '1', '3'], ['', '', ''], ['', '', '']], {})[0])

    def test_connectivity_checks_total_region_size(self):
        self.assertFalse(can_connect_region(3, {0: 3, 2: 3, 6: 3}, 3, [0, 2, 6]))
        self.assertTrue(can_connect_region(3, {1: 4, 3: 4, 5: 4}, 4, [1, 3, 5]))

    def test_connectivity_candidate_evaluation_and_boundaries(self):
        grid = [['a', 'a'], ['', '']]
        self.assertTrue(check_grid_connectivity(grid, {'a': 2})[0])
        for candidate in (0, -1, '1/2', 3):
            self.assertFalse(check_grid_connectivity(grid, {'a': candidate})[0])

    def test_coupled_variables_reject_fraction_zero_and_negative(self):
        solutions = [value for value in valid_combinations(
            ["b/a", "a-1", "b-a", "a^3-b"], {"a": (1, 3), "b": (1, 6)}, 6)
            if value is not None]
        self.assertEqual(solutions, [{"a": 2, "b": 4}, {"a": 2, "b": 6}])

    def test_region_limit_is_inclusive_and_applies_to_results(self):
        self.assertEqual(list(valid_combinations(["a^2"], {"a": (2, 3)}, 6)),
                         [{"a": 2}, None])
        self.assertEqual(list(valid_combinations(["a-10"], {"a": (16, 17)}, 6)),
                         [{"a": 16}, None])

    def test_zero_denominator_does_not_stop_search(self):
        self.assertEqual(list(valid_combinations(["1/a"], {"a": (-1, 1)}, 6)),
                         [None, None, {"a": 1}])

    def test_constant_grids_and_unused_variables(self):
        self.assertEqual(list(valid_combinations(["2"], {}, 6)), [{}])
        self.assertEqual(list(valid_combinations(["1/2"], {}, 6)), [None])
        self.assertEqual(list(valid_combinations([], {"a": (-1, 1)}, 6)),
                         [{"a": -1}, {"a": 0}, {"a": 1}])

    def test_candidate_range_format(self):
        self.assertEqual(format_candidates({1, 2, 3, 5, 7, 8}), "1–3, 5, 7–8")
        self.assertEqual(format_candidates(set()), "None")

    def test_bounds_are_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid.json"
            state = {"size": 1, "expressions": [["a"]], "variables": {"a": "2"},
                     "bounds": {"a": {"min": "-2", "max": "12"}}}
            write_state(path, state)
            self.assertEqual(read_state(path), state)

    def test_grid_hit_testing_with_left_alignment(self):
        canvas = GridCanvas.__new__(GridCanvas)
        canvas.size = 5
        canvas.bounds = (4, 30, 250)
        selected = []
        canvas.select_cell = lambda x, y: selected.append((x, y))
        canvas.click(SimpleNamespace(x=253, y=279))
        canvas.click(SimpleNamespace(x=400, y=100))
        self.assertEqual(selected, [(4, 4)])

    def test_batched_search_finishes_and_stale_job_is_ignored(self):
        app = PuzzleApp.__new__(PuzzleApp)
        messages, displayed = [], []
        app.compute_button = SimpleNamespace(configure=lambda **kw: None)
        app.search_message = SimpleNamespace(set=messages.append)
        app.valid_values = {"a": SimpleNamespace(set=displayed.append)}
        app.root = SimpleNamespace(after=lambda delay, callback: callback())
        job = {"iterator": valid_combinations(["a-1"], {"a": (1, 150)}, 6),
               "total": 150, "checked": 0, "count": 0,
               "values": {"a": set()}, "first": None}
        app.search_job = job
        app.search_step(job)
        self.assertEqual(job["count"], 6)
        self.assertEqual(displayed, ["2–7"])
        self.assertIsNone(app.search_job)
        app.search_step(job)
        self.assertEqual(displayed, ["2–7"])


if __name__ == "__main__":
    unittest.main()
