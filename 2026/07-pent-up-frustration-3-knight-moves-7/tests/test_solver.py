from copy import deepcopy
import unittest
from unittest.mock import patch

from functions.solver import interval_limit, solve
from functions.state import Session, new_grid


class SolverTests(unittest.TestCase):
    def test_interval_bound_counts_starting_cell(self):
        self.assertEqual(interval_limit(new_grid("bound", 8, 8), 18, 5), 9)
        self.assertEqual(interval_limit(new_grid("bound", 8, 8), 18, 0), 0)

    def test_real_continuation_solves_small_puzzle_without_modifying_input(self):
        s = Session(new_grid("solver", 1, 3))
        s.grid["scores"][0][0] = 0
        s.grid["scores"][0][2] = 0
        s.mark_tower((0, 0), False)
        before = s.serialize()
        result = solve(s, early_end=0, first_interval=1)
        self.assertEqual(result.status, "solved")
        self.assertEqual(result.interval, 1)
        self.assertEqual(result.session.grid["visits"][0][2], 1)
        self.assertEqual(result.session.grid["towers"], [[0, 2]])
        self.assertEqual(s.serialize(), before)

    def test_no_remaining_clues_searches_for_final_tower(self):
        s = Session(new_grid("solver", 1, 3))
        s.grid["scores"][0][0] = 0
        s.mark_tower((0, 0), False)
        result = solve(s, early_end=0)
        self.assertEqual(result.status, "solved")
        self.assertIsNone(result.interval)
        self.assertEqual(result.session.grid["visits"][0][2], 1)
        self.assertEqual(result.session.grid["towers"], [[0, 2]])

    def test_retry_keeps_interval_fixed_and_restores_checkpoint_baseline(self):
        s = Session(new_grid("solver", 1, 7))
        s.grid["scores"][0][0] = 0
        s.grid["scores"][0][1] = 5
        s.grid["scores"][0][2] = 9
        before = s.serialize()
        calls = []
        def checkpoint(trial, visit, moves, report):
            calls.append((visit, moves))
            if visit == 0:
                self.assertIsNone(trial.grid["visits"][0][1])
                trial.grid["visits"][0][1] = moves
                return (0, 1)
            if moves == 1:
                return None
            trial.grid["visits"][0][2] = visit + moves
            return (0, 2)
        completed = [[[0, 0, 0, 0, 0], [0, 3, 1, 1, 0], [0, 1, 5, 2, 0],
                      [0, 4, 7, 3, 0], [0, 2, 9, 4, 0], [0, 6, 10, 5, 1]]]
        with patch("functions.solver.continue_checkpoint", side_effect=checkpoint), \
                patch("functions.solver.final_solutions", return_value=completed):
            result = solve(s, early_end=0, first_interval=1)
        self.assertEqual(calls, [(0, 1), (1, 1), (0, 2), (2, 2)])
        self.assertEqual(result.interval, 2)
        self.assertEqual(result.status, "solved")
        self.assertEqual(s.serialize(), before)

    def test_bound_prevents_trials_that_cannot_fit_remaining_clues(self):
        s = Session(new_grid("solver", 1, 3))
        s.grid["scores"][0] = [0, 5, 9]
        with patch("functions.solver.continue_checkpoint") as checkpoint:
            result = solve(s, early_end=0, first_interval=2)
        checkpoint.assert_not_called()
        self.assertEqual(result.status, "failed")
        self.assertIn("through 1", result.message)

    def test_early_failure_stops_before_later_interval_trials(self):
        s = Session(new_grid("solver", 2, 3))
        s.grid["scores"][1][0] = 0
        result = solve(s, early_end=3)
        self.assertEqual(result.status, "failed")
        self.assertIn("visit 3", result.message)

    def test_invalid_start_or_schedule_is_rejected(self):
        s = Session(new_grid("solver", 8, 8))
        with self.assertRaises(ValueError):
            solve(s)
        s.grid["scores"][7][0] = 0
        with self.assertRaises(ValueError):
            solve(s, early_end=17)
