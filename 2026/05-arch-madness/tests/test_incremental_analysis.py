import copy
import random
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from functions.clue_analysis import ClueAnalysis, analyze_clue, minimum_perimeter_pieces, compatible_factorizations
from functions.incremental_analysis import (analyze_clue_incremental, check_secondary_clue,
                                  simplified_choices, SimplifiedArc, concrete_completions)
from functions.incremental_analysis import (_Partial, partial_curve_feasible, SecondarySearchCache,
                                  secondary_clue_constrained)
from functions.incremental_analysis import enclosed_perimeter_capacity
from puzzle_gui import PuzzleEditor, blank_grid, ARC_CYCLE


def board(rows, columns):
    return {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}


class IncrementalAnalysisTests(unittest.TestCase):
    def compare(self, state, selected, **kwargs):
        before = copy.deepcopy(state)
        actual = analyze_clue_incremental(state, selected, check_other_clues=False,
                                          simplify_nonclue=False, **kwargs)
        expected = analyze_clue(state, selected, **kwargs)
        self.assertEqual(actual.accepted_states, expected.accepted_states)
        self.assertEqual((actual.cancelled, actual.limit_reached, actual.factorizations),
                         (expected.cancelled, expected.limit_reached, expected.factorizations))
        self.assertEqual(state, before)

    def test_tiny_board_parity(self):
        for green, fixed in ((False, None), (True, None), (False, "br")):
            state = board(2, 2)
            state["cells"][1][1].update(green=green, arc=fixed)
            for clue in range(1, 21):
                state["cells"][0][0]["number"] = clue
                self.compare(state, (0, 0), accepted_limit=10000)


    def test_green_propagation_and_domain_parity(self):
        state = board(3, 3)
        state["cells"][0][1]["number"] = 12
        state["cells"][1][1]["green"] = True
        state["cells"][2][1]["green"] = True
        state["arc_domains"] = [[list((None, "tl", "tr", "br", "bl")) for c in range(3)] for r in range(3)]
        state["arc_domains"][0][0] = [None]
        state["arc_domains"][1][0] = ["tr", "bl"]
        self.compare(state, (0, 1))

    def test_random_constrained_boards_and_conflicting_clues(self):
        rng = random.Random(314159)
        for _ in range(20):
            state = board(3, 3)
            for row in state["cells"]:
                for cell in row:
                    status = rng.choice((None, None, None, "tl", "tr", "br", "bl", "green"))
                    cell.update(green=status == "green", arc=None if status == "green" else status)
            state["cells"][1][1]["number"] = rng.choice((3, 4, 6, 9, 12))
            state["cells"][2][2]["number"] = rng.choice((3, 6, 9))
            self.compare(state, (1, 1))

    def test_cancellation_and_invalid_selection(self):
        state = board(2, 2)
        state["cells"][0][0]["number"] = 3
        event = threading.Event()
        event.set()
        self.compare(state, (0, 0), stop_event=event)
        with self.assertRaises(ValueError):
            analyze_clue_incremental(state, (5, 5))
        with self.assertRaises(ValueError):
            analyze_clue_incremental(state, (0, 1))

    def test_incremental_engine_does_not_reflood_from_clue(self):
        state = board(2, 2)
        state["cells"][0][0]["number"] = 3
        with patch("functions.clue_analysis.partial_region", side_effect=AssertionError("Full reflood used")):
            result = analyze_clue_incremental(state, (0, 0))
        self.assertEqual(len(result.accepted_states), 2)

    def test_both_engines_continue_beyond_100000_until_manually_aborted(self):
        state = board(5, 5)
        state["cells"][1][1]["number"] = 36
        for engine in (analyze_clue, analyze_clue_incremental):
            event = threading.Event()

            def progress(visited, accepted):
                if visited > 100000:
                    event.set()

            options = {'simplify_nonclue': False} if engine is analyze_clue_incremental else {}
            result = engine(state, (1, 1), stop_event=event, progress=progress,
                            accepted_limit=10000, **options)
            self.assertGreater(result.explored, 100000)
            self.assertTrue(result.cancelled)
            self.assertFalse(result.limit_reached)


class SimplifiedArcTests(unittest.TestCase):
    def test_confirmed_bend_bound_distinguishes_cusps_and_quarter_turns(self):
        self.assertEqual(minimum_perimeter_pieces(3, 3), 4)
        self.assertEqual(minimum_perimeter_pieces(3, 2), 3)
        self.assertFalse(compatible_factorizations(((1, 21), (3, 7), (7, 3), (21, 1)),
                                                   4, minimum_perimeter_pieces(3, 3)))

    def test_21_with_three_grid_bends_and_area_above_three_prunes_before_growth(self):
        state = board(2, 4)
        state['cells'][0][0]['number'] = 21
        state['arc_domains'] = [[[None] for _ in range(4)],
                                [[None], list(ARC_CYCLE), list(ARC_CYCLE), list(ARC_CYCLE)]]
        # The five forced whole cells touch three 90-degree grid corners.
        # Area 7 would require three pieces, but parity requires at least four.
        result = analyze_clue_incremental(state, (0, 0), check_other_clues=False)
        self.assertEqual(result.explored, 1)
        self.assertEqual(result.score_pruned, 1)
        self.assertEqual(result.factorization_pruned, 1)
        self.assertFalse(result.accepted_states)

    def test_enclosed_capacity_counts_arcs_and_distinct_grid_sides(self):
        state = board(3, 3)
        assigned = {(0, 0): None, (0, 1): None,
                    (1, 0): 'tl', (1, 1): SimplifiedArc('NW', ('tl', 'br'))}
        fragments = {(r, c, 0) for r, c in assigned}
        # Two arc cells, north edge once and west edge once.
        self.assertEqual(enclosed_perimeter_capacity(state, assigned, fragments), 4)
        # A corner cell's outside fragment touches south/east of the cell,
        # so it does not touch the north/west grid borders.
        self.assertEqual(enclosed_perimeter_capacity(state, {(0, 0): 'tl'}, {(0, 0, 1)}), 1)

    def test_enclosed_capacity_rejects_before_full_perimeter_validation(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 20
        state['arc_domains'] = [[[None] for _ in range(2)] for _ in range(2)]
        with patch('puzzle_gui.Region.determine_score', side_effect=AssertionError('Perimeter checked')):
            result = analyze_clue_incremental(state, (0, 0))
        self.assertEqual(result.perimeter_capacity_pruned, 1)
        self.assertEqual(result.area_pruned, 0)
        self.assertFalse(result.accepted_states)

    def test_partial_curve_choices_must_be_consistent_across_corners(self):
        partial = _Partial(reached={(0, 0)},
                           corners={(0, 1): (((0, -1), True),),
                                    (1, 0): (((0, 1), True),)})
        assigned = {(0, 0): SimplifiedArc('NW', ('tl', 'br'))}
        # Each corner can be smooth individually, but requires a different
        # orientation of the same cell. A one-piece perimeter is impossible.
        incident = lambda r, c: ((0, 0),)
        self.assertFalse(partial_curve_feasible(partial, assigned, incident, 1))
        self.assertFalse(partial_curve_feasible(partial, assigned, incident, 2))
        self.assertTrue(partial_curve_feasible(partial, assigned, incident, 3))

    def test_switch_to_regular_arcs_preserves_concrete_solutions(self):
        state = board(3, 3)
        state['cells'][0][0]['number'] = 9
        result = analyze_clue_incremental(state, (0, 0), check_other_clues=False,
                                          accepted_limit=10000)
        self.assertGreater(result.regular_switches, 0)
        self.assertEqual(len(result.accepted_states), 16)

    def test_three_piece_filter_does_not_switch_25_to_regular_arcs_at_area_two(self):
        state = board(5, 5)
        state['cells'][0][0]['number'] = 25
        state['arc_domains'] = [[list(ARC_CYCLE) for _ in range(5)] for _ in range(5)]
        state['arc_domains'][0][0] = [None]
        state['arc_domains'][0][1] = [None]
        with patch('functions.incremental_analysis.simplified_choices',
                   wraps=simplified_choices) as grouped:
            result = analyze_clue_incremental(state, (0, 0), check_other_clues=False,
                                              branch_limit=1)
        self.assertEqual(result.factorizations, ((1, 25), (5, 5)))
        self.assertGreater(grouped.call_count, 0)
        self.assertEqual(result.regular_switches, 0)

    def test_one_incoming_edge_has_three_topological_choices(self):
        for edge in 'NESW':
            choices = simplified_choices((None, 'tl', 'tr', 'br', 'bl'), {edge})
            self.assertEqual(len(choices), 3)
            self.assertIsNone(choices[0])
            for arc in choices[1:]:
                self.assertIn(edge, arc.edges)
                self.assertEqual(len(arc.options), 2)

    def test_multiple_entry_edges_and_master_domains_are_respected(self):
        choices = simplified_choices((None, 'tl', 'br'), {'N', 'W'})
        self.assertEqual(choices, [None, SimplifiedArc('NW', ('tl', 'br'))])
        self.assertEqual(simplified_choices(('tl',), {'N'}), [SimplifiedArc('NW', ('tl',))])
        self.assertEqual(simplified_choices(('tl', 'br'), {'N', 'S'}), [])

    def test_concrete_acceptances_match_exhaustive_search_with_fixed_arcs(self):
        for green, fixed in ((False, None), (True, None), (False, 'br')):
            state = board(2, 2)
            state['cells'][1][1].update(green=green, arc=fixed)
            for clue in range(1, 21):
                state['cells'][0][0]['number'] = clue
                before = copy.deepcopy(state)
                expected = analyze_clue(state, (0, 0), accepted_limit=10000)
                actual = analyze_clue_incremental(state, (0, 0), accepted_limit=10000,
                                                  check_other_clues=False)
                self.assertEqual(set(actual.accepted_states), set(expected.accepted_states))
                self.assertEqual(state, before)

    def test_switching_preserves_all_realizations(self):
        state = board(3, 3)
        state['cells'][0][0]['number'] = 9
        full = analyze_clue_incremental(state, (0, 0), simplify_nonclue=False,
                                         check_other_clues=False, accepted_limit=10000)
        simple = analyze_clue_incremental(state, (0, 0), check_other_clues=False,
                                           accepted_limit=10000)
        self.assertEqual(set(simple.accepted_states), set(full.accepted_states))
        self.assertTrue(simple.accepted_states)
        for signature in simple.accepted_states:
            self.assertTrue(all(arc in (None, 'tl', 'tr', 'br', 'bl') for _, _, arc in signature))

    def test_completion_requires_exact_balance_and_correct_smooth_pieces(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 3
        assigned = {(0, 0): 'tr', (0, 1): SimplifiedArc('NW', ('tl', 'br'))}
        fragments = {(0, 0, 0), (0, 1, 0)}
        self.assertEqual(list(concrete_completions(state, assigned, fragments, 3)),
                         [((0, 0, 'tr'), (0, 1, 'br'))])
        # The half-cell area is one, but no realization has four smooth pieces.
        self.assertEqual(list(concrete_completions(state, assigned, fragments, 4)), [])
        assigned[(0, 1)] = SimplifiedArc('NW', ('tl',))
        # Two insides would have noninteger area despite the half-cell estimate.
        self.assertEqual(list(concrete_completions(state, assigned, fragments, 3)), [])

    def test_secondary_check_preserves_simplified_domains(self):
        state = board(2, 2)
        state['cells'][1][1]['number'] = 9
        with patch('functions.incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine:
            check_secondary_clue(state, {(0, 0): SimplifiedArc('NW', ('tl', 'br'))}, (1, 1))
        context = engine.call_args.args[0]
        self.assertIsNone(context['cells'][0][0]['arc'])
        self.assertEqual(context['arc_domains'][0][0], ['tl', 'br'])


class SecondaryClueTests(unittest.TestCase):
    def test_45_green_reconnection_prioritizes_288_and_rejects_quickly(self):
        state = board(9, 9)
        state['cells'][6][7].update(number=45, arc='br')
        state['cells'][7][8]['number'] = 288
        for r, c in ((5, 7), (5, 8), (8, 8), (8, 6)):
            state['cells'][r][c]['green'] = True
        state['cells'][8][6]['number'] = 35
        before = copy.deepcopy(state)
        with patch('functions.incremental_analysis.check_secondary_clue', wraps=check_secondary_clue) as secondary:
            result = analyze_clue_incremental(state, (6, 7))
        self.assertFalse(result.accepted_states)
        self.assertFalse(result.limit_reached)
        self.assertFalse(result.cancelled)
        self.assertGreaterEqual(result.secondary_pruned, 2)
        self.assertLess(result.explored, 50)
        self.assertEqual(secondary.call_args_list[0].args[2], (7, 8))
        first_assigned = secondary.call_args_list[0].args[1]
        self.assertIn((6, 8), first_assigned)
        self.assertNotIn((6, 6), first_assigned)
        self.assertEqual(state, before)

    def test_green_growth_with_many_exits_skips_secondary_search(self):
        state = board(5, 5)
        state['cells'][2][2]['number'] = 25
        state['cells'][1][2]['green'] = True
        state['cells'][2][3]['green'] = True
        self.assertFalse(secondary_clue_constrained(state, {(2, 2): 'tr'}, (2, 2)))
        # Resolving those exits makes the same clue worth checking later.
        assigned = {(r, c): None for r in range(5) for c in range(5)}
        assigned[(2, 2)] = 'tr'
        self.assertTrue(secondary_clue_constrained(state, assigned, (2, 2)))

    def test_narrow_frontier_triggers_secondary_check(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 3
        self.assertTrue(secondary_clue_constrained(state, {(0, 0): 'tr'}, (0, 0)))

    def test_secondary_cache_reuses_identical_contradiction(self):
        cache = SecondarySearchCache(board(2, 2))
        with patch('functions.incremental_analysis.check_secondary_clue', return_value=ClueAnalysis()) as engine:
            self.assertFalse(cache.check({(0, 0): 'tl'}, (1, 1))[1])
            result, hit = cache.check({(0, 0): 'tl'}, (1, 1))
            self.assertTrue(hit)
            self.assertFalse(result.accepted_states)
            engine.assert_called_once()
            self.assertTrue(engine.call_args.kwargs['simplify_nonclue'])

    def test_secondary_cache_reuses_witness_only_when_compatible(self):
        cache = SecondarySearchCache(board(2, 2))
        witness = ((0, 0, 'tl'), (0, 1, 'br'))
        with patch('functions.incremental_analysis.check_secondary_clue',
                   return_value=ClueAnalysis(accepted_states=[witness])) as engine:
            cache.check({(0, 0): 'tl'}, (0, 0))
            result, hit = cache.check({(0, 0): SimplifiedArc('NW', ('tl', 'br')),
                                      (1, 1): None}, (0, 0))
            self.assertTrue(hit)
            self.assertEqual(result.accepted_states, [witness])
            engine.assert_called_once()
            self.assertFalse(cache.check({(0, 0): 'br'}, (0, 0))[1])
            self.assertEqual(engine.call_count, 2)

    def test_secondary_cache_keeps_cutoffs_inconclusive_and_does_not_cache_abort(self):
        cache = SecondarySearchCache(board(2, 2))
        with patch('functions.incremental_analysis.check_secondary_clue',
                   return_value=ClueAnalysis(worklist_limit_reached=True)) as engine:
            cache.check({}, (0, 0))
            result, hit = cache.check({}, (0, 0))
            self.assertTrue(hit)
            self.assertTrue(result.worklist_limit_reached)
            engine.assert_called_once()
        cache = SecondarySearchCache(board(2, 2))
        with patch('functions.incremental_analysis.check_secondary_clue',
                   return_value=ClueAnalysis(cancelled=True)) as engine:
            cache.check({}, (0, 0))
            self.assertFalse(cache.check({}, (0, 0))[1])
            self.assertEqual(engine.call_count, 2)

    def test_secondary_search_inherits_disabled_settings(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 3
        with patch('functions.incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine:
            check_secondary_clue(state, {}, (0, 0), simplify_nonclue=False,
                                 prioritize_frontier=False)
        self.assertFalse(engine.call_args.kwargs['simplify_nonclue'])
        self.assertFalse(engine.call_args.kwargs['prioritize_frontier'])

    def test_prioritization_can_be_disabled(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 3
        with patch('functions.incremental_analysis.frontier_priorities', side_effect=AssertionError('Priority used')):
            result = analyze_clue_incremental(state, (0, 0), prioritize_frontier=False)
        self.assertEqual(len(result.accepted_states), 2)

    def test_context_pins_arc_and_empty_decisions_without_mutation(self):
        state = board(2, 2)
        state["cells"][1][1]["number"] = 9
        before = copy.deepcopy(state)
        with patch("functions.incremental_analysis.analyze_clue_incremental", return_value=ClueAnalysis()) as engine:
            check_secondary_clue(state, {(0, 0): None, (1, 1): "tl"}, (1, 1))
        context = engine.call_args.args[0]
        self.assertEqual(context["arc_domains"][0][0], [None])
        self.assertEqual(context["arc_domains"][1][1], ["tl"])
        self.assertEqual(engine.call_args.kwargs["worklist_limit"], 25)
        self.assertFalse(engine.call_args.kwargs["check_other_clues"])
        self.assertEqual(engine.call_args.kwargs["accepted_limit"], 0)
        self.assertEqual(state, before)

    def test_worklist_cutoff_counts_pending_states_not_branches(self):
        state = board(2, 2)
        state["cells"][0][0]["number"] = 3
        result = analyze_clue_incremental(state, (0, 0), worklist_limit=4)
        self.assertTrue(result.worklist_limit_reached)
        self.assertEqual(result.explored, 0)
        result = analyze_clue_incremental(state, (0, 0), worklist_limit=25)
        self.assertFalse(result.worklist_limit_reached)
        self.assertTrue(result.accepted_states)

    def test_other_clue_contradiction_prunes_but_cutoff_does_not(self):
        state = board(3, 3)
        state["cells"][1][1]["number"] = 12
        state["cells"][2][2]["number"] = 9
        with patch("functions.incremental_analysis.check_secondary_clue", return_value=ClueAnalysis()):
            rejected = analyze_clue_incremental(state, (1, 1))
        self.assertGreater(rejected.secondary_pruned, 0)
        with patch("functions.incremental_analysis.check_secondary_clue",
                   return_value=ClueAnalysis(worklist_limit_reached=True)):
            inconclusive = analyze_clue_incremental(state, (1, 1))
        self.assertGreater(inconclusive.secondary_cutoffs, 0)
        self.assertEqual(inconclusive.secondary_pruned, 0)
        baseline = analyze_clue_incremental(state, (1, 1), check_other_clues=False)
        self.assertEqual(inconclusive.accepted_states, baseline.accepted_states)

    def test_real_secondary_search_rejects_noninteger_region(self):
        state = board(1, 1)
        state["cells"][0][0]["number"] = 4
        result = check_secondary_clue(state, {(0, 0): "tl"}, (0, 0))
        self.assertFalse(result.accepted_states)
        self.assertFalse(result.worklist_limit_reached)
        self.assertTrue(check_secondary_clue(state, {(0, 0): None}, (0, 0)).accepted_states)


class SearchTimingTests(unittest.TestCase):
    def make_editor(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = board(2, 2)
        editor.state["cells"][0][0]["number"] = 3
        editor.selected = (0, 0)
        editor.analysis_cancel = None
        editor.analysis_result = None
        editor.analysis_elapsed_seconds = None
        editor.simplify_arcs = SimpleNamespace(get=lambda: True)
        editor.prioritize_cells = SimpleNamespace(get=lambda: True)
        editor.check_other_clues = SimpleNamespace(get=lambda: True)
        editor.draw = lambda: None
        editor.save = lambda: True
        editor.undo_stack, editor.redo_stack = [], []
        editor.analysis_button = SimpleNamespace(configure=lambda **kwargs: None)
        times, statuses, callbacks = [], [], []
        editor.search_time_text = SimpleNamespace(set=times.append)
        editor.status = SimpleNamespace(set=statuses.append)
        editor.root = SimpleNamespace(after=lambda delay, callback: callbacks.append(callback))
        return editor, times, statuses, callbacks

    def test_analysis_button_uses_incremental_engine_and_records_time(self):
        class ImmediateThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        editor, times, statuses, callbacks = self.make_editor()
        with patch("functions.incremental_analysis.analyze_clue_incremental", return_value=ClueAnalysis(explored=7)) as engine, \
                patch("functions.clue_analysis.analyze_clue", side_effect=AssertionError("Old engine used")), \
                patch("puzzle_gui.threading.Thread", ImmediateThread), \
                patch("puzzle_gui.perf_counter", side_effect=[10.0, 11.0, 12.0, 13.0, 14.0]):
            editor.analyze_selected_clue()
            callbacks.pop(0)()
        engine.assert_called_once()
        self.assertTrue(engine.call_args.kwargs['simplify_nonclue'])
        self.assertTrue(engine.call_args.kwargs['prioritize_frontier'])
        self.assertTrue(engine.call_args.kwargs['check_other_clues'])
        self.assertEqual(editor.analysis_result.elapsed_seconds, 2.0)
        self.assertEqual(editor.analysis_result.main_search_seconds, 1.0)
        self.assertEqual(editor.analysis_result.sanity_check_seconds, 1.0)
        self.assertEqual(times[-1], "Search time: 2.00 s")
        self.assertIn("7 branches checked in 2.00 s", statuses[-1])

    def test_timer_updates_without_progress_and_abort_retains_elapsed_time(self):
        editor, times, statuses, callbacks = self.make_editor()
        dormant = SimpleNamespace(start=lambda: None)
        with patch("puzzle_gui.threading.Thread", return_value=dormant), \
                patch("puzzle_gui.perf_counter", side_effect=[10.0, 11.0, 12.0]):
            editor.analyze_selected_clue()
            callbacks.pop(0)()
            self.assertEqual(times[-1], "Search time: 1.00 s (running)")
            self.assertIn("1.00 s elapsed", statuses[-1])
            editor.abort_clue_analysis()
        self.assertEqual(times[-1], "Search time: 2.00 s (cancelled)")
        self.assertIn("aborted after 2.00 s", statuses[-1])
        self.assertIsNone(editor.analysis_cancel)

    def test_disabled_checkboxes_are_passed_to_worker(self):
        editor, times, statuses, callbacks = self.make_editor()
        editor.simplify_arcs = SimpleNamespace(get=lambda: False)
        editor.prioritize_cells = SimpleNamespace(get=lambda: False)
        editor.check_other_clues = SimpleNamespace(get=lambda: False)
        workers = []
        with patch('functions.incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine, \
                patch('puzzle_gui.threading.Thread',
                      side_effect=lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target))):
            editor.analyze_selected_clue()
            workers[0]()
        for option in ('simplify_nonclue', 'prioritize_frontier', 'check_other_clues'):
            self.assertFalse(engine.call_args.kwargs[option])


if __name__ == "__main__":
    unittest.main()
