import unittest
from fractions import Fraction
from unittest.mock import patch

from functions.solve_functions import (
    BackgroundRegionOperation, candidate_labels, completed_regions, elapsed_text,
    included_expressions, overlay_board,
)


class SharedSolveTests(unittest.TestCase):
    def test_gui_and_runner_completion_rules_remain_distinct(self):
        states = [{'cells': {5}, 'assumptions': {0: 2, 1: 2}},
                  {'cells': {5}, 'assumptions': {0: 2, 2: 2}}]
        self.assertEqual(completed_regions(states, {}, 1), {1, 2})
        self.assertEqual(completed_regions(states, {}, 1, identical=True), {1})
        self.assertEqual(overlay_board(states[0], {}, 1), {0: 2, 1: 2, 5: 1})

    def test_included_equations_do_not_modify_original_grid(self):
        grid = [['a', 'b'], ['c', 'd']]
        self.assertEqual(included_expressions(grid, {1, 2}), [['a', ''], ['', 'd']])
        self.assertEqual(grid, [['a', 'b'], ['c', 'd']])

    def test_candidate_labels_handle_unknown_and_fractional_values(self):
        assignments = [{'a': Fraction(1, 2), 'b': None}, {'a': Fraction(3, 2), 'b': Fraction(1)}]
        self.assertEqual(candidate_labels(assignments, ['a', 'b']), {'a': '1/2, 3/2', 'b': 'Unknown'})

    def test_worker_delivers_progress_and_result(self):
        def work(progress):
            progress(1, 2)
            return 'result'
        task = BackgroundRegionOperation(work)
        task.thread.join(timeout=2)
        self.assertFalse(task.thread.is_alive())
        self.assertEqual(task.poll(), ([(1, 2)], ('result', 'result')))

    def test_worker_discards_result_if_cancelled_before_poll(self):
        task = BackgroundRegionOperation(lambda progress: 'result')
        task.thread.join(timeout=2)
        task.cancel.set()
        updates, final = task.poll()
        self.assertEqual(updates, [])
        self.assertEqual(final, ('error', 'Operation aborted. Previous overlays retained.'))

    def test_worker_reports_errors_and_elapsed_time(self):
        def work(progress):
            raise ValueError('bad region')
        task = BackgroundRegionOperation(work)
        task.thread.join(timeout=2)
        self.assertEqual(task.poll(), ([], ('error', 'bad region')))
        with patch('functions.solve_functions.perf_counter', return_value=12.5):
            self.assertEqual(elapsed_text(10), 'Time: 2.50 seconds')


if __name__ == '__main__':
    unittest.main()
