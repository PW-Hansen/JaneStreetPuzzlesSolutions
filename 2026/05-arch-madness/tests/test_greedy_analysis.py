import copy
import unittest
from unittest.mock import patch

from functions.greedy_analysis import GreedyBoundary, analyze_clue_greedy
from functions.incremental_analysis import SimplifiedArc
from functions.clue_analysis import ClueAnalysis, incorporate_analysis
from puzzle_gui import blank_grid, allowed_arc_configurations, save_accepted_states, PuzzleEditor


def board(rows, columns):
    return {'rows': rows, 'columns': columns, 'cells': blank_grid(rows, columns)}


class GreedyAnalysisTests(unittest.TestCase):
    def test_clockwise_edges_and_corner_contact_count(self):
        state = board(2, 3)
        policy = GreedyBoundary(state)
        self.assertEqual(len(policy.edges), 10)
        self.assertEqual(policy.contacts({(0, 0): None}, {(0, 0, 0)}), {0, 9})
        self.assertEqual(policy.edges[3], (0, 2, 'E', (0, 3)))

    def test_plans_are_even_longest_first_and_group_terminal_arcs(self):
        state = board(3, 4)
        state['cells'][1][0]['number'] = 21
        policy = GreedyBoundary(state)
        domains = {(r, c): allowed_arc_configurations(state, r, c)
                   for r in range(3) for c in range(4)}
        assigned = {(1, 0): 'tl'}
        plans = policy.plans(assigned, {(1, 0, 0)}, domains, True)
        self.assertTrue(plans)
        lengths = [len(interval) for _, interval in plans]
        self.assertEqual(lengths, sorted(lengths, reverse=True))
        self.assertTrue(all(length % 2 == 0 for length in lengths))
        self.assertTrue(any(isinstance(value, SimplifiedArc) and len(value.options) == 2
                            for updates, _ in plans for value in updates.values()))
        self.assertTrue(any(None in updates.values() for updates, _ in plans))

    def test_green_cells_and_master_domains_constrain_endpoints(self):
        state = board(3, 4)
        state['cells'][0][1]['green'] = True
        state['arc_domains'] = [[list(allowed_arc_configurations(state, r, c))
                                for c in range(4)] for r in range(3)]
        state['arc_domains'][0][2] = ['tl', 'br']
        policy = GreedyBoundary(state)
        domains = {(r, c): allowed_arc_configurations(state, r, c)
                   for r in range(3) for c in range(4)}
        for updates, _ in policy.plans({(1, 0): 'tl'}, {(1, 0, 0)}, domains, True):
            self.assertIsNone(updates.get((0, 1)))
            if (0, 2) in updates:
                value = updates[(0, 2)]
                options = value.options if isinstance(value, SimplifiedArc) else (value,)
                self.assertTrue(set(options) <= {'tl', 'br'})

    def test_example_skips_eight_edges_and_tries_six_before_four(self):
        state = board(9, 9)
        state['cells'][1][0]['number'] = 21
        for c in (0, 3):
            state['cells'][0][c]['green'] = True
        domains = {(r, c): allowed_arc_configurations(state, r, c)
                   for r in range(9) for c in range(9)}
        domains[(0, 5)] = (None,)
        domains[(0, 6)] = ('tl', 'br')
        policy = GreedyBoundary(state)
        plans = policy.plans({(1, 0): 'tl', (0, 0): None},
                             {(1, 0, 0), (0, 0, 0)}, domains, True)
        self.assertTrue(plans)
        self.assertEqual(len(plans[0][1]), 6)
        self.assertNotIn(8, [len(interval) for _, interval in plans])
        terminal = plans[0][0][(0, 4)]
        self.assertIsInstance(terminal, SimplifiedArc)
        self.assertEqual(set(terminal.options), {'tr', 'bl'})
        self.assertIn(4, [len(interval) for _, interval in plans])

    def test_full_boundary_no_arc_cells_add_whole_area(self):
        state = board(2, 3)
        state['cells'][0][0]['number'] = 24
        before = copy.deepcopy(state)
        result = analyze_clue_greedy(state, (0, 0), check_other_clues=False)
        self.assertTrue(result.heuristic)
        self.assertIn(tuple((r, c, None) for r in range(2) for c in range(3)), result.accepted_states)
        self.assertEqual(state, before)

    def test_heuristic_previews_do_not_apply_or_save_regular_deductions(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 9
        before = copy.deepcopy(state)
        result = ClueAnalysis(accepted_states=[((0, 0, 'tl'),)], heuristic=True)
        self.assertEqual(incorporate_analysis(state, result), {'removed': 0, 'applied': False})
        self.assertFalse(save_accepted_states(state, (0, 0), result))
        self.assertEqual(state, before)

    def test_gui_button_calls_shared_analysis_with_greedy_mode(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        with patch.object(editor, 'analyze_selected_clue') as analyze:
            editor.analyze_selected_clue_greedy()
            analyze.assert_called_once_with(greedy=True)

    def test_greedy_25_area_above_five_rejects_without_perimeter_search(self):
        state = board(2, 4)
        state['cells'][0][0]['number'] = 25
        state['arc_domains'] = [[[None] for _ in range(4)],
                                [[None], [None], [None, 'tl', 'tr', 'br', 'bl'],
                                 [None, 'tl', 'tr', 'br', 'bl']]]
        result = analyze_clue_greedy(state, (0, 0), check_other_clues=False)
        self.assertFalse(result.accepted_states)
        self.assertEqual(result.explored, 1)
        self.assertEqual(result.area_pruned, 1)
        self.assertTrue(all(pieces >= 3 for _, pieces in result.factorizations))
        self.assertNotIn((25, 1), result.factorizations)

    def test_minimum_three_pieces_applies_to_both_searches(self):
        from functions.incremental_analysis import analyze_clue_incremental
        state = board(5, 5)
        state['cells'][2][2]['number'] = 25
        regular = analyze_clue_incremental(state, (2, 2), check_other_clues=False, branch_limit=0)
        greedy = analyze_clue_greedy(state, (2, 2), check_other_clues=False, branch_limit=0)
        self.assertTrue(all(pieces >= 3 for _, pieces in regular.factorizations))
        self.assertEqual(regular.factorizations, greedy.factorizations)
        self.assertTrue(all(pieces >= 3 for _, pieces in greedy.factorizations))
