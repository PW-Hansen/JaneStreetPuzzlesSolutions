import copy
import json
import unittest
import random

from arc_constraints import propagate_arc_domains
from clue_analysis import ClueAnalysis, incorporate_analysis
from incremental_analysis import analyze_clue_incremental, SimplifiedArc
from puzzle_gui import blank_grid, validate_state, ARC_CYCLE


class ArcConstraintTests(unittest.TestCase):
    def test_queued_propagation_matches_full_pass_reference(self):
        rng = random.Random(123)
        state = self.board(2, 2)
        cells = [(r, c) for r in range(2) for c in range(2)]
        for _ in range(200):
            state['arc_implications'] = [
                {'if': [*rng.choice(cells), rng.choice(ARC_CYCLE)],
                 'then': [*rng.choice(cells), rng.sample(list(ARC_CYCLE), rng.randint(1, 5))]}
                for _ in range(8)]
            domains = {cell: rng.sample(list(ARC_CYCLE), rng.randint(1, 5)) for cell in cells}
            reference = {cell: set(values) for cell, values in domains.items()}
            changed = True
            while changed and all(reference.values()):
                before = {cell: set(values) for cell, values in reference.items()}
                for rule in state['arc_implications']:
                    r, c, trigger = rule['if']
                    nr, nc, allowed = rule['then']
                    source, target = reference[(r, c)], reference[(nr, nc)]
                    if trigger in source and not target.intersection(allowed):
                        source.remove(trigger)
                    if source == {trigger}:
                        reference[(nr, nc)] = target.intersection(allowed)
                changed = reference != before
            expected = ({cell: tuple(arc for arc in ARC_CYCLE if arc in values)
                         for cell, values in reference.items()} if all(reference.values()) else None)
            self.assertEqual(propagate_arc_domains(state, domains=domains), expected)

    def test_conditional_frontier_growth_matches_reference_solver(self):
        from clue_analysis import analyze_clue
        for trigger in ARC_CYCLE:
            state = self.board(2, 2)
            state['cells'][0][0]['number'] = 3
            state['arc_implications'] = [{'if': [0, 0, trigger], 'then': [1, 1, ['tl', 'br']]},
                                         {'if': [1, 1, 'tl'], 'then': [0, 1, ['br']]}]
            expected = analyze_clue(state, (0, 0), accepted_limit=1000)
            actual = analyze_clue_incremental(state, (0, 0), accepted_limit=1000,
                                             check_other_clues=False, simplify_nonclue=False)
            normalize = lambda result: {frozenset(values) for values in result.accepted_states}
            self.assertEqual(normalize(actual), normalize(expected))

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
