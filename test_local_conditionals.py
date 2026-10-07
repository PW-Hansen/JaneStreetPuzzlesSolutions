import copy
import unittest

from arc_constraints import propagate_arc_domains
from local_conditionals import local_conflict, scan_local_conditionals
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
        self.assertNotIn('arc_implications', scanned)
        self.assertEqual(counts['implications'], 0)

    def test_three_step_limit_is_enforced(self):
        state = {'rows': 1, 'columns': 5, 'cells': blank_grid(1, 5)}
        state['cells'][0][0]['number'] = 21
        state['cells'][0][4]['number'] = 27
        for c in (1, 2, 3):
            state['cells'][0][c]['green'] = True
        domains = propagate_arc_domains(state, {(0, 0): None, (0, 4): None})
        self.assertFalse(local_conflict(state, (0, 0), domains, 3))
        self.assertTrue(local_conflict(state, (0, 0), domains, 4))

    def test_scan_is_idempotent_and_does_not_replace_existing_rules(self):
        first, counts = scan_local_conditionals(self.board())
        second, repeated = scan_local_conditionals(first)
        self.assertEqual(first, second)
        self.assertEqual(repeated['implications'], 0)

    def test_unknown_intermediate_cells_do_not_prove_a_connection(self):
        state = self.board()
        state['cells'][2][0]['green'] = False
        domains = propagate_arc_domains(state, {(1, 0): None, (2, 1): None})
        self.assertFalse(local_conflict(state, (1, 0), domains))


if __name__ == '__main__':
    unittest.main()
