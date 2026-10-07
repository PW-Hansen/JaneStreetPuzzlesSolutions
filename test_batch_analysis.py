import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from clue_analysis import ClueAnalysis
from puzzle_gui import PuzzleEditor, blank_grid, ordered_clues


class ImmediateThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class BatchAnalysisTests(unittest.TestCase):
    def test_order_uses_each_green_neighbor_and_edge_once(self):
        state = {'rows': 4, 'columns': 5, 'cells': blank_grid(4, 5)}
        for r, c, number in [(0, 0, 9), (2, 3, 15), (2, 2, 21), (0, 4, 17)]:
            state['cells'][r][c]['number'] = number
        for r, c in [(0, 1), (1, 0), (3, 3)]:
            state['cells'][r][c]['green'] = True
        # Adjusted scores: 2.53125, 8.5, 11.25, 21. Corners get one edge factor.
        self.assertEqual(ordered_clues(state), [(0, 0), (0, 4), (2, 3), (2, 2)])

    def editor(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = {'rows': 1, 'columns': 2, 'cells': blank_grid(1, 2)}
        editor.state['cells'][0][0]['number'] = 4
        editor.state['cells'][0][1]['number'] = 8
        editor.analysis_cancel = None
        editor.analysis_started_at = None
        editor.analysis_elapsed_seconds = None
        editor.selected = None
        editor.undo_stack, editor.redo_stack = [], []
        editor.simplify_arcs = SimpleNamespace(get=lambda: True)
        editor.prioritize_cells = SimpleNamespace(get=lambda: False)
        editor.check_other_clues = SimpleNamespace(get=lambda: False)
        editor.analysis_button = SimpleNamespace(configure=lambda **kwargs: None)
        editor.analyze_all_button = SimpleNamespace(configure=lambda **kwargs: None)
        editor.status = SimpleNamespace(set=lambda value: None)
        callbacks = []
        editor.root = SimpleNamespace(after=lambda delay, callback: callbacks.append(callback))
        editor.draw = lambda: None
        editor.save = lambda: True
        editor.scan_local_conditionals = lambda: True
        return editor, callbacks

    def test_batch_applies_and_saves_each_result_before_starting_next(self):
        editor, callbacks = self.editor()
        inputs = []
        scans = []
        def scan():
            scans.append(True)
            editor.state['arc_domains'] = [[['tl'], [None, 'tl', 'tr', 'br', 'bl']]]
            return True
        editor.scan_local_conditionals = scan
        def engine(state, selected, **kwargs):
            self.assertEqual(scans, [True])
            inputs.append((copy.deepcopy(state), selected))
            return ClueAnalysis(accepted_states=[((*selected, 'tl' if selected == (0, 0) else 'tr'),)],
                                source_clue=selected)
        with patch('puzzle_gui.threading.Thread', ImmediateThread), \
                patch('incremental_analysis.analyze_clue_incremental', side_effect=engine):
            editor.analyze_all_clues()
            while callbacks:
                callbacks.pop(0)()
        self.assertEqual([selected for _, selected in inputs], [(0, 0), (0, 1), (0, 0), (0, 1)])
        self.assertEqual(inputs[0][0]['arc_domains'][0][0], ['tl'])
        self.assertEqual(inputs[1][0]['cells'][0][0]['arc'], 'tl')
        self.assertIn('0,0', inputs[1][0]['saved_analyses'])
        self.assertEqual(set(editor.state['saved_analyses']), {'0,0', '0,1'})
        self.assertIsNone(editor.batch_token)
        self.assertEqual(len(editor.undo_stack), 2)
        self.assertEqual(editor.batch_pass, 2)

    def test_complete_grid_stops_without_another_pass(self):
        editor, callbacks = self.editor()
        editor.state['cells'][0][0]['number'] = 8
        editor.state['cells'][0][1]['number'] = 8
        with patch('puzzle_gui.threading.Thread', ImmediateThread), \
                patch('incremental_analysis.analyze_clue_incremental', return_value=ClueAnalysis()) as engine:
            editor.analyze_all_clues()
            while callbacks:
                callbacks.pop(0)()
        self.assertEqual(engine.call_count, 2)
        self.assertEqual(editor.batch_pass, 1)
        self.assertIsNone(editor.batch_token)

    def test_failed_scan_does_not_start_batch(self):
        editor, callbacks = self.editor()
        editor.scan_local_conditionals = lambda: False
        with patch('puzzle_gui.threading.Thread') as worker:
            editor.analyze_all_clues()
        worker.assert_not_called()
        self.assertIsNone(editor.batch_token)
        self.assertEqual(callbacks, [])

    def test_abort_stops_current_worker_and_prevents_next_clue(self):
        editor, callbacks = self.editor()
        with patch('puzzle_gui.threading.Thread', return_value=SimpleNamespace(start=lambda: None)):
            editor.analyze_all_clues()
            event = editor.analysis_cancel
            token = editor.batch_token
            editor.abort_clue_analysis()
            self.assertTrue(event.is_set())
            self.assertIsNone(editor.batch_token)
            for callback in callbacks:
                callback()
            editor.next_batch_clue(token)
            self.assertEqual(editor.selected, (0, 0))
            self.assertEqual(editor.batch_clues, [])

    def test_total_timer_freezes_when_batch_terminates(self):
        editor, callbacks = self.editor()
        displayed = []
        editor.batch_time_text = SimpleNamespace(set=displayed.append)
        editor.batch_token = token = object()
        editor.batch_started_at = 10.0
        with patch('puzzle_gui.perf_counter', side_effect=[12.0, 15.0]):
            editor.poll_batch_time(token)
            editor.stop_batch_analysis()
        self.assertEqual(editor.batch_elapsed_seconds, 5.0)
        self.assertEqual(displayed[-1], 'Total analysis time: 5.00 s')
        callbacks.pop(0)()
        editor.stop_batch_analysis()
        self.assertEqual(displayed[-1], 'Total analysis time: 5.00 s')


if __name__ == '__main__':
    unittest.main()
