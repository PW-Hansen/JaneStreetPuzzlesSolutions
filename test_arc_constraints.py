import copy
import json
import unittest
import random

from arc_constraints import (propagate_arc_domains, make_arc_domain_propagator,
                             apply_arc_deductions, describe_arc_implications)
from clue_analysis import ClueAnalysis, incorporate_analysis
from incremental_analysis import analyze_clue_incremental, SimplifiedArc
from puzzle_gui import blank_grid, validate_state, ARC_CYCLE


class ArcConstraintTests(unittest.TestCase):
    def test_optional_source_hypotheses_respect_existing_conditional_context(self):
        state = self.board(1, 3)
        state['cells'][0][0]['number'] = 3
        state['arc_implications'] = [{'if': [0, 2, 'tl'], 'then': [0, 1, ['br']]}]
        # The first local region omits the source, but cannot coexist with
        # source=tl: its target=tl would violate the existing conditional.
        result = ClueAnalysis(accepted_states=[((0, 0, None), (0, 1, 'tl')),
                                              ((0, 0, 'br'), (0, 1, 'br'), (0, 2, 'tr'))],
                              source_clue=(0, 0))
        incorporate_analysis(state, result)
        propagated = propagate_arc_domains(state, {(0, 2): 'tl'})
        self.assertTrue(propagated is None or propagated[(0, 1)] == ('br',))
        validate_state(json.loads(json.dumps(state)))

    def test_grouped_triggers_propagate_from_a_multi_option_domain(self):
        state = self.board(1, 3)
        state['arc_implications'] = [
            {'if': [0, 0, arc], 'then': [0, 1, ['br']]}
            for arc in ARC_CYCLE[1:]]
        state['arc_implications'].append({'if': [0, 1, 'br'], 'then': [0, 2, ['tl']]})
        domains = {(0, 0): ('tl', 'tr'), (0, 1): ARC_CYCLE, (0, 2): ARC_CYCLE}
        propagated = propagate_arc_domains(state, domains=domains)
        self.assertEqual(propagated[(0, 1)], ('br',))
        self.assertEqual(propagated[(0, 2)], ('tl',))
        # The inverse of the grouped condition excludes every arc trigger.
        reverse = propagate_arc_domains(state, {(0, 1): 'tl'})
        self.assertEqual(reverse[(0, 0)], (None,))

    def test_root_rule_filter_preserves_descendant_cascades(self):
        state = self.board(1, 3)
        state['arc_implications'] = [{'if': [0, 0, 'tl'], 'then': [0, 1, ['br']]},
                                     {'if': [0, 1, 'br'], 'then': [0, 2, ['tl', 'tr']]}]
        root = propagate_arc_domains(state, domains={(0, 0): ARC_CYCLE,
                (0, 1): ARC_CYCLE, (0, 2): ('tl', 'tr')})
        propagate = make_arc_domain_propagator(state)
        propagate.restrict(root)
        for arc in ARC_CYCLE:
            actual, _ = propagate.extend(root, (0, 0), arc)
            self.assertEqual(actual, propagate_arc_domains(state, {(0, 0): arc}, root))

    def test_incremental_domains_match_full_propagation_and_preserve_parent(self):
        rng = random.Random(456)
        state = self.board(2, 2)
        cells = [(r, c) for r in range(2) for c in range(2)]
        for _ in range(100):
            state['arc_implications'] = [
                {'if': [*rng.choice(cells), rng.choice(ARC_CYCLE)],
                 'then': [*rng.choice(cells), rng.sample(list(ARC_CYCLE), rng.randint(1, 5))]}
                for _ in range(8)]
            propagate = make_arc_domain_propagator(state)
            domains = propagate(state)
            for cell in rng.sample(cells, len(cells)):
                if domains is None:
                    break
                parent = copy.deepcopy(domains)
                arc = rng.choice(domains[cell])
                expected = propagate(state, {cell: arc}, domains)
                actual, changes = propagate.extend(domains, cell, arc)
                self.assertEqual(actual, expected)
                self.assertEqual(domains, parent)
                if actual is not None:
                    self.assertEqual(set(changes), {key for key in domains if actual[key] != domains[key]})
                domains = actual

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

    def test_optional_cells_are_wildcards_and_partial_searches_do_not_learn(self):
        state = self.board()
        states = [((1, 5, 'tl'), (0, 6, 'br')), ((1, 5, 'br'),)]
        incorporate_analysis(state, ClueAnalysis(accepted_states=states))
        # The state omitting the target permits every target configuration.
        self.assertEqual(set(propagate_arc_domains(state, {(1, 5): 'br'})[(0, 6)]), set(ARC_CYCLE))
        self.assertEqual(propagate_arc_domains(state, {(0, 6): 'tl'})[(1, 5)], ('br',))
        for flag in ('limit_reached', 'cancelled', 'worklist_limit_reached'):
            state = self.board()
            incorporate_analysis(state, ClueAnalysis(accepted_states=states, **{flag: True}))
            self.assertNotIn('arc_implications', state)

    def test_three_21_states_learn_optional_cell_and_apply_remaining_shared_arcs(self):
        accepted = [
            ((0, 0, None), (0, 1, None), (0, 2, 'bl'), (1, 0, None), (1, 1, None),
             (1, 2, 'tl'), (2, 0, None), (2, 1, 'br'), (3, 0, 'br')),
            ((1, 0, 'bl'), (2, 0, None), (2, 1, 'tr'), (2, 2, 'tl'), (2, 3, 'bl'),
             (3, 0, 'tr'), (3, 1, None), (3, 2, None), (3, 3, 'tl'), (4, 1, 'bl'), (4, 2, 'br')),
            ((1, 0, 'bl'), (2, 0, None), (2, 1, 'tr'), (3, 0, 'tr'), (3, 1, None),
             (3, 2, 'bl'), (4, 1, 'bl'), (4, 2, None), (4, 3, 'tr'), (5, 2, 'tr'), (5, 3, 'br'))]
        state = self.board(9, 9)
        incorporate_analysis(state, ClueAnalysis(accepted_states=accepted, source_clue=(1, 0)))
        descriptions = describe_arc_implications(state, (3, 1))
        self.assertIn('anything other than no arc, r2c1 must be no arc', descriptions)
        self.assertLessEqual(len(descriptions.splitlines()), 2)
        saved = validate_state(json.loads(json.dumps(state)))
        # Merely excluding empty at r4c2 selects the first region, even though
        # that region does not contain r4c2 and says nothing about its arc.
        nonempty = copy.deepcopy(saved)
        nonempty['arc_domains'][3][1].remove(None)
        apply_arc_deductions(nonempty)
        for r, c, arc in accepted[0]:
            self.assertEqual(nonempty['arc_domains'][r][c], [arc])
            self.assertEqual(nonempty['cells'][r][c]['arc'], arc)
        for arc, remaining in [('br', accepted[:1]), ('tr', accepted[1:])]:
            branch = copy.deepcopy(saved)
            branch['cells'][2][1]['arc'] = arc
            apply_arc_deductions(branch)
            shared = set(remaining[0]).intersection(*(set(values) for values in remaining[1:]))
            for r, c, forced in shared:
                self.assertEqual(branch['arc_domains'][r][c], [forced])
                self.assertEqual(branch['cells'][r][c]['arc'], forced)
            if arc == 'tr':
                self.assertEqual(branch['arc_domains'][3][2], [None, 'bl'])
                self.assertEqual(branch['cells'][3][2]['arc'], None)

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
