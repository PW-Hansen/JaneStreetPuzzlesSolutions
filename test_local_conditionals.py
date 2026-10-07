import copy
import unittest

from arc_constraints import propagate_arc_domains
from local_conditionals import local_conflict, scan_local_conditionals, LocalLookahead
from puzzle_gui import blank_grid, validate_state


class LocalConditionalTests(unittest.TestCase):
    def board(self):
        state = {'rows': 4, 'columns': 4, 'cells': blank_grid(4, 4)}
        state['cells'][1][0]['number'] = 21
        state['cells'][2][1]['number'] = 27
        state['cells'][2][0]['green'] = True
        return state

    def test_shared_green_produces_user_example(self):
        state = self.board()
        before = copy.deepcopy(state)
        scanned, counts = scan_local_conditionals(state)
        expected = {'if': [1, 0, None], 'then': [2, 1, ['tr', 'br']]}
        self.assertIn(expected, scanned['arc_implications'])
        self.assertGreater(counts['implications'], 0)
        self.assertEqual(propagate_arc_domains(scanned, {(1, 0): None})[(2, 1)], ('tr', 'br'))
        self.assertEqual(state, before)
        validate_state(scanned)

    def test_same_value_clues_may_connect(self):
        state = self.board()
        state['cells'][2][1]['number'] = 21
        scanned, counts = scan_local_conditionals(state)
        self.assertIsNotNone(propagate_arc_domains(scanned, {(1, 0): None, (2, 1): None}))

    def test_three_step_limit_is_enforced(self):
        state = {'rows': 1, 'columns': 5, 'cells': blank_grid(1, 5)}
        state['cells'][0][0]['number'] = 21
        state['cells'][0][4]['number'] = 27
        for c in (1, 2, 3):
            state['cells'][0][c]['green'] = True
        domains = propagate_arc_domains(state, {(0, 0): None, (0, 4): None})
        self.assertFalse(local_conflict(state, (0, 0), domains, 3))
        self.assertTrue(local_conflict(state, (0, 0), domains, 4))

    def test_repeated_scan_preserves_or_strengthens_existing_rules(self):
        first, counts = scan_local_conditionals(self.board())
        second, repeated = scan_local_conditionals(first)
        old_rules = {(tuple(rule['if']), tuple(rule['then'][:2])): set(rule['then'][2])
                     for rule in first.get('arc_implications', [])}
        new_rules = {(tuple(rule['if']), tuple(rule['then'][:2])): set(rule['then'][2])
                     for rule in second.get('arc_implications', [])}
        for key, allowed in old_rules.items():
            self.assertTrue(new_rules[key] <= allowed)
        validate_state(second)

    def test_forced_path_can_exceed_three_steps_inside_radius(self):
        state = {'rows': 3, 'columns': 3, 'cells': blank_grid(3, 3)}
        state['cells'][1][1]['number'] = 21
        for r, c in ((1, 2), (2, 2), (2, 1), (2, 0), (1, 0), (0, 0)):
            state['cells'][r][c]['green'] = True
        domains = propagate_arc_domains(state, {(1, 1): 'tr'})
        self.assertTrue(local_conflict(state, (1, 1), domains, 3))

    def test_45_bottom_right_fails_all_local_288_continuations(self):
        state = {'rows': 9, 'columns': 9, 'cells': blank_grid(9, 9)}
        state['cells'][6][7]['number'] = 45
        state['cells'][7][8]['number'] = 288
        state['cells'][8][6]['number'] = 35
        for r, c in ((5, 7), (5, 8), (8, 8), (8, 6)):
            state['cells'][r][c]['green'] = True
        domains = propagate_arc_domains(state, {(6, 7): 'br'})
        self.assertFalse(local_conflict(state, (6, 7), domains, 3))
        self.assertIs(LocalLookahead(state, (6, 7)).feasible(domains), False)
        self.assertIsNone(LocalLookahead(state, (6, 7), max_decisions=0).feasible(domains))
        scanned, counts = scan_local_conditionals(state)
        self.assertNotIn('br', scanned['arc_domains'][6][7])
        self.assertGreater(counts['removed'], 0)

    def test_exhausted_budget_does_not_prove_a_contradiction(self):
        state = self.board()
        domains = propagate_arc_domains(state, {(1, 0): None})
        self.assertIsNone(LocalLookahead(state, (1, 0), budget=[0]).feasible(domains))

    def test_unknown_intermediate_cells_do_not_prove_a_connection(self):
        state = self.board()
        state['cells'][2][0]['green'] = False
        domains = propagate_arc_domains(state, {(1, 0): None, (2, 1): None})
        self.assertFalse(local_conflict(state, (1, 0), domains))


if __name__ == '__main__':
    unittest.main()
