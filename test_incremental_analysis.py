import copy
import random
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from clue_analysis import ClueAnalysis, analyze_clue
from incremental_analysis import analyze_clue_incremental
from puzzle_gui import PuzzleEditor, blank_grid


def board(rows, columns):
    return {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}


class IncrementalAnalysisTests(unittest.TestCase):
    def compare(self, state, selected, **kwargs):
        before = copy.deepcopy(state)
        self.assertEqual(analyze_clue_incremental(state, selected, **kwargs),
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

            result = engine(state, (1, 1), stop_event=event, progress=progress)
            self.assertGreater(result.explored, 100000)
            self.assertTrue(result.cancelled)
            self.assertFalse(result.limit_reached)


class SearchTimingTests(unittest.TestCase):
    def make_editor(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = board(2, 2)
        editor.state["cells"][0][0]["number"] = 3
        editor.selected = (0, 0)
        editor.analysis_cancel = None
        editor.analysis_result = None
        editor.analysis_elapsed_seconds = None
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


if __name__ == "__main__":
    unittest.main()
