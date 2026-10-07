import copy
import json
import unittest

from arc_constraints import propagate_arc_domains
from clue_analysis import ClueAnalysis, incorporate_analysis
from incremental_analysis import analyze_clue_incremental, SimplifiedArc
from puzzle_gui import blank_grid, validate_state


class ArcConstraintTests(unittest.TestCase):
    def board(self, rows=2, columns=7):
        return {'rows': rows, 'columns': columns, 'cells': blank_grid(rows, columns)}

    def test_learns_user_example_and_persists_relationships(self):
        state = self.board()
        result = ClueAnalysis(accepted_states=[((1, 5, 'tl'), (0, 6, 'br')),
                                               ((1, 5, 'br'), (0, 6, 'tl'))])
        changes = incorporate_analysis(state, result)
        self.assertGreater(changes['implications'], 0)
        self.assertIn({'if': [1, 5, 'tl'], 'then': [0, 6, ['br']]}, state['arc_implications'])
        saved = validate_state(json.loads(json.dumps(state)))
        self.assertEqual(saved, state)
        self.assertEqual(propagate_arc_domains(saved, {(1, 5): 'tl'})[(0, 6)], ('br',))
        self.assertIsNone(propagate_arc_domains(saved, {(1, 5): 'tl', (0, 6): 'tl'}))

    def test_optional_cells_and_partial_searches_do_not_learn(self):
        state = self.board()
        states = [((1, 5, 'tl'), (0, 6, 'br')), ((1, 5, 'br'),)]
        incorporate_analysis(state, ClueAnalysis(accepted_states=states))
        self.assertNotIn('arc_implications', state)
        for flag in ('limit_reached', 'cancelled', 'worklist_limit_reached'):
            state = self.board()
            incorporate_analysis(state, ClueAnalysis(accepted_states=states, **{flag: True}))
            self.assertNotIn('arc_implications', state)

    def test_chain_propagation_and_reverse_elimination(self):
        state = self.board()
        state['arc_implications'] = [{'if': [0, 0, 'tl'], 'then': [0, 1, ['br']]},
                                     {'if': [0, 1, 'br'], 'then': [0, 2, [None]]}]
        self.assertEqual(propagate_arc_domains(state, {(0, 0): 'tl'})[(0, 2)], (None,))
        self.assertNotIn('tl', propagate_arc_domains(state, {(0, 1): 'tr'})[(0, 0)])
        self.assertIsNone(propagate_arc_domains(state, {(0, 0): 'tl', (0, 2): 'tr'}))

    def test_regular_analysis_respects_conditional_configuration(self):
        state = self.board(2, 2)
        state['cells'][0][0]['number'] = 3
        state['cells'][0][1]['arc'] = 'br'
        state['arc_implications'] = [{'if': [0, 0, 'bl'], 'then': [0, 1, ['tl']]}]
        before = copy.deepcopy(state)
        result = analyze_clue_incremental(state, (0, 0))
        self.assertEqual(len(result.accepted_states), 1)
        self.assertEqual(result.accepted_states[0][0], (0, 0, 'tr'))
        self.assertEqual(state, before)

    def test_simplified_domains_are_filtered_without_picking_a_curve_prematurely(self):
        state = self.board(2, 2)
        state['arc_implications'] = [{'if': [0, 0, 'tl'], 'then': [0, 1, ['br']]}]
        grouped = SimplifiedArc('NW', ('tl', 'br'))
        propagated = propagate_arc_domains(state, {(0, 0): grouped, (0, 1): 'tr'})
        self.assertEqual(propagated[(0, 0)], ('br',))


if __name__ == '__main__':
    unittest.main()
