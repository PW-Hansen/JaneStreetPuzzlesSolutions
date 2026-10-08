import copy
import threading
import unittest
from unittest.mock import patch

from functions.clue_analysis import ClueAnalysis
from functions.incremental_analysis import sanity_check_accepted_states, analyze_clue_incremental
from puzzle_gui import blank_grid


class SanityChecksTests(unittest.TestCase):
    def state(self):
        state = {'rows': 3, 'columns': 3, 'cells': blank_grid(3, 3)}
        for r, c, number in [(1, 1, 9), (0, 1, 15), (1, 0, 21), (1, 2, 27), (0, 0, 35)]:
            state['cells'][r][c]['number'] = number
        return state

    def test_each_neighbor_has_independent_cutoff_and_diagonal_is_not_checked(self):
        state = self.state()
        before = copy.deepcopy(state)
        accepted = ((1, 1, 'tl'),)
        alternatives = [accepted, ((1, 1, 'br'),)]
        result = ClueAnalysis(accepted_states=list(alternatives))
        with patch('functions.incremental_analysis.check_secondary_clue',
                   side_effect=lambda *args, **kwargs: ClueAnalysis(explored=25001, branch_limit_reached=True)) as check:
            sanity_check_accepted_states(state, result, (1, 1))
        self.assertEqual([call.args[2] for call in check.call_args_list], [(0, 1), (1, 0), (1, 2)] * 2)
        for index, call in enumerate(check.call_args_list):
            self.assertEqual(call.kwargs['branch_limit'], 25000)
            self.assertIsNone(call.kwargs['worklist_limit'])
            self.assertEqual(call.args[1], {(1, 1): 'tl' if index < 3 else 'br'})
        self.assertEqual(result.accepted_states, alternatives)
        self.assertEqual(result.sanity_cutoffs, 6)
        self.assertEqual(result.sanity_branches, 150006)
        self.assertEqual(state, before)

    def test_exhaustive_failure_rejects_only_that_state_and_cancellation_applies_nothing(self):
        state = self.state()
        accepted = [((1, 1, 'tl'),), ((1, 1, 'br'),)]
        result = ClueAnalysis(accepted_states=list(accepted))
        def probe(state, assigned, selected, *args, **kwargs):
            if assigned[(1, 1)] == 'tl':
                return ClueAnalysis()
            return ClueAnalysis(accepted_states=[((0, 1, 'tr'),)], limit_reached=True)
        with patch('functions.incremental_analysis.check_secondary_clue', side_effect=probe):
            sanity_check_accepted_states(state, result, (1, 1))
        self.assertEqual(result.accepted_states, accepted[1:])
        self.assertEqual(result.sanity_pruned, 1)
        event = threading.Event()
        event.set()
        cancelled = ClueAnalysis(accepted_states=list(accepted))
        sanity_check_accepted_states(state, cancelled, (1, 1), event)
        self.assertTrue(cancelled.cancelled)
        self.assertEqual(cancelled.accepted_states, accepted)

    def test_incomplete_primary_results_do_not_run_sanity_searches(self):
        for flag in ('cancelled', 'limit_reached', 'worklist_limit_reached', 'branch_limit_reached'):
            with patch('functions.incremental_analysis.check_secondary_clue') as check:
                result = ClueAnalysis(accepted_states=[((1, 1, 'tl'),), ((1, 1, 'br'),)], **{flag: True})
                sanity_check_accepted_states(self.state(), result, (1, 1))
                check.assert_not_called()

    def test_single_accepted_state_skips_sanity_checks(self):
        accepted = [((1, 1, 'tl'),)]
        result = ClueAnalysis(accepted_states=list(accepted))
        with patch('functions.incremental_analysis.check_secondary_clue') as check:
            self.assertIs(sanity_check_accepted_states(self.state(), result, (1, 1)), result)
            check.assert_not_called()
        self.assertEqual(result.accepted_states, accepted)
        self.assertEqual(result.sanity_checks, 0)

    def test_branch_cap_is_optional_and_uses_explored_branches(self):
        state = {'rows': 2, 'columns': 2, 'cells': blank_grid(2, 2)}
        state['cells'][0][0]['number'] = 9
        limited = analyze_clue_incremental(state, (0, 0), check_other_clues=False, branch_limit=0)
        self.assertTrue(limited.branch_limit_reached)
        self.assertEqual(limited.explored, 1)
        complete = analyze_clue_incremental(state, (0, 0), check_other_clues=False)
        self.assertFalse(complete.branch_limit_reached)


if __name__ == '__main__':
    unittest.main()
