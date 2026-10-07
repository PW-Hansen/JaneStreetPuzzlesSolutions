import copy
import random
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from clue_analysis import ClueAnalysis, analyze_clue
from incremental_analysis import (analyze_clue_incremental, check_secondary_clue,
                                  simplified_choices, SimplifiedArc, concrete_completions)
from puzzle_gui import PuzzleEditor, blank_grid


def board(rows, columns):
    return {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}


class IncrementalAnalysisTests(unittest.TestCase):
    def compare(self, state, selected, **kwargs):
        before = copy.deepcopy(state)
        self.assertEqual(analyze_clue_incremental(state, selected, check_other_clues=False,
                                                simplify_nonclue=False, **kwargs),
                         analyze_clue(state, selected, **kwargs))
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
        with patch("clue_analysis.partial_region", side_effect=AssertionError("Full reflood used")):
            result = analyze_clue_incremental(state, (0, 0))
        self.assertEqual(len(result.accepted_states), 2)

    def test_both_engines_continue_beyond_100000_until_manually_aborted(self):
        state = board(4, 4)
        state["cells"][1][1]["number"] = 12
        for engine in (analyze_clue, analyze_clue_incremental):
            event = threading.Event()

            def progress(visited, accepted):
                if visited > 100000:
                    event.set()

            options = {'simplify_nonclue': False} if engine is analyze_clue_incremental else {}
            result = engine(state, (1, 1), stop_event=event, progress=progress, **options)
            self.assertGreater(result.explored, 100000)
            self.assertTrue(result.cancelled)
            self.assertFalse(result.limit_reached)


class SimplifiedArcTests(unittest.TestCase):
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

    def test_simplification_reduces_expansion_without_losing_realizations(self):
        state = board(3, 3)
        state['cells'][0][0]['number'] = 9
        full = analyze_clue_incremental(state, (0, 0), simplify_nonclue=False,
                                         check_other_clues=False, accepted_limit=10000)
        simple = analyze_clue_incremental(state, (0, 0), check_other_clues=False,
                                           accepted_limit=10000)
        self.assertEqual(set(simple.accepted_states), set(full.accepted_states))
        self.assertLess(simple.explored, full.explored)
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
        with patch('incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine:
            check_secondary_clue(state, {(0, 0): SimplifiedArc('NW', ('tl', 'br'))}, (1, 1))
        context = engine.call_args.args[0]
        self.assertIsNone(context['cells'][0][0]['arc'])
        self.assertEqual(context['arc_domains'][0][0], ['tl', 'br'])


class SecondaryClueTests(unittest.TestCase):
    def test_secondary_search_inherits_disabled_settings(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 3
        with patch('incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine:
            check_secondary_clue(state, {}, (0, 0), simplify_nonclue=False,
                                 prioritize_frontier=False)
        self.assertFalse(engine.call_args.kwargs['simplify_nonclue'])
        self.assertFalse(engine.call_args.kwargs['prioritize_frontier'])

    def test_prioritization_can_be_disabled(self):
        state = board(2, 2)
        state['cells'][0][0]['number'] = 3
        with patch('incremental_analysis.frontier_priorities', side_effect=AssertionError('Priority used')):
            result = analyze_clue_incremental(state, (0, 0), prioritize_frontier=False)
        self.assertEqual(len(result.accepted_states), 2)

    def test_context_pins_arc_and_empty_decisions_without_mutation(self):
        state = board(2, 2)
        state["cells"][1][1]["number"] = 9
        before = copy.deepcopy(state)
        with patch("incremental_analysis.analyze_clue_incremental", return_value=ClueAnalysis()) as engine:
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
        with patch("incremental_analysis.check_secondary_clue", return_value=ClueAnalysis()):
            rejected = analyze_clue_incremental(state, (1, 1))
        self.assertGreater(rejected.secondary_pruned, 0)
        with patch("incremental_analysis.check_secondary_clue",
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
        with patch("incremental_analysis.analyze_clue_incremental", return_value=ClueAnalysis(explored=7)) as engine, \
                patch("clue_analysis.analyze_clue", side_effect=AssertionError("Old engine used")), \
                patch("puzzle_gui.threading.Thread", ImmediateThread), \
                patch("puzzle_gui.perf_counter", side_effect=[10.0, 11.0, 13.0, 14.0]):
            editor.analyze_selected_clue()
            callbacks.pop(0)()
        engine.assert_called_once()
        self.assertTrue(engine.call_args.kwargs['simplify_nonclue'])
        self.assertTrue(engine.call_args.kwargs['prioritize_frontier'])
        self.assertTrue(engine.call_args.kwargs['check_other_clues'])
        self.assertEqual(editor.analysis_result.elapsed_seconds, 2.0)
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
        with patch('incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine, \
                patch('puzzle_gui.threading.Thread',
                      side_effect=lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target))):
            editor.analyze_selected_clue()
            workers[0]()
        for option in ('simplify_nonclue', 'prioritize_frontier', 'check_other_clues'):
            self.assertFalse(engine.call_args.kwargs[option])


if __name__ == "__main__":
    unittest.main()
