import copy
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from clue_analysis import ClueAnalysis
from puzzle_gui import PuzzleEditor, blank_grid, ordered_clues, fixed_clue_order


class ImmediateThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class BatchAnalysisTests(unittest.TestCase):
    def test_file_order_uses_one_based_coordinates_and_named_puzzle(self):
        editor, _ = self.editor()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'solution_clue_analysis_order.json'
            path.write_text(json.dumps({'example': [
                {'row': 1, 'column': 2, 'clue': 8}, {'row': 1, 'column': 1, 'clue': 4}]}), encoding='utf-8')
            self.assertEqual(fixed_clue_order(editor.state, 'example', path), [(0, 1), (0, 0)])
            with self.assertRaisesRegex(ValueError, 'No set order'):
                fixed_clue_order(editor.state, 'missing', path)
            for entries in ([{'row': 0, 'column': 1, 'clue': 4}],
                            [{'row': 1, 'column': 1, 'clue': 99}],
                            [{'row': 1, 'column': 1, 'clue': 4}] * 2,
                            [{'row': True, 'column': 1, 'clue': 4}]):
                path.write_text(json.dumps({'example': entries}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    fixed_clue_order(editor.state, 'example', path)

    def setUp(self):
        sanity = patch('incremental_analysis.sanity_check_accepted_states', side_effect=lambda state, result, *args, **kwargs: result)
        sanity.start()
        self.addCleanup(sanity.stop)
    def test_dynamic_weights_change_the_order_and_prompt_can_be_cancelled(self):
        state = {'rows': 3, 'columns': 3, 'cells': blank_grid(3, 3)}
        state['cells'][0][0]['number'] = 9
        state['cells'][0][1]['green'] = True
        state['cells'][1][1]['number'] = 8
        self.assertEqual(ordered_clues(state), [(1, 1), (0, 0)])
        self.assertEqual(ordered_clues(state, (1, .5, .75)), [(0, 0), (1, 1)])
        editor, _ = self.editor()
        editor.analyze_all_clues = run = unittest.mock.Mock()
        with patch('puzzle_gui.AnalysisWeightsDialog', return_value=SimpleNamespace(result=None)):
            editor.analyze_all_dynamic()
        run.assert_not_called()
        with patch('puzzle_gui.AnalysisWeightsDialog', return_value=SimpleNamespace(result=(.8, .5, .75))):
            editor.analyze_all_dynamic()
        run.assert_called_once_with(weights=(.8, .5, .75))

    def test_set_order_requires_full_puzzle_and_follows_exact_sequence(self):
        editor, callbacks = self.editor()
        editor.path = Path('example.json')
        editor.puzzle_name = 'example'
        with patch('puzzle_gui.messagebox.showerror') as error:
            editor.analyze_all_set()
        error.assert_called_once()
        self.assertEqual(callbacks, [])
        editor.path = Path('full_puzzle.json')
        editor.puzzle_name = 'full_puzzle'
        editor.state = {'rows': 9, 'columns': 9, 'cells': blank_grid(9, 9)}
        sequence = [(2, 8, 9), (4, 8, 9), (6, 0, 9), (7, 4, 9),
                    (1, 7, 25), (2, 5, 15), (1, 0, 21), (0, 2, 21), (2, 1, 27),
                    (4, 0, 25), (7, 1, 63), (8, 6, 35), (6, 7, 45), (7, 8, 288)]
        for r, c, number in sequence + [(4, 3, 27)]:
            editor.state['cells'][r][c]['number'] = number
        expected = [(r, c) for r, c, _ in sequence]
        self.assertEqual(fixed_clue_order(editor.state, editor.puzzle_name), expected)
        seen = []
        def engine(state, selected, **kwargs):
            seen.append(selected)
            return ClueAnalysis(source_clue=selected)
        with patch('puzzle_gui.threading.Thread', ImmediateThread), \
                patch('incremental_analysis.analyze_clue_incremental', side_effect=engine), \
                patch('builtins.print') as output:
            editor.analyze_all_set()
            while callbacks:
                callbacks.pop(0)()
        self.assertEqual(seen, expected)
        messages = [call.args[0] for call in output.call_args_list]
        self.assertTrue(any(message.startswith('Set-order pass 1 complete:') for message in messages))
        self.assertTrue(any(message.startswith('Set-order analysis finished after 1 passes:') for message in messages))

    def test_order_uses_nearby_grouped_conditionals_instead_of_green_and_edges(self):
        state = {'rows': 4, 'columns': 5, 'cells': blank_grid(4, 5)}
        for r, c, number in [(0, 0, 9), (2, 3, 15), (2, 2, 21), (0, 4, 17)]:
            state['cells'][r][c]['number'] = number
        for r, c in [(0, 1), (1, 0), (3, 3)]:
            state['cells'][r][c]['green'] = True
        self.assertEqual(ordered_clues(state), [(0, 0), (2, 3), (0, 4), (2, 2)])
        state['arc_implications'] = [{'if': [2, 2, arc], 'then': [3, 2, ['tl']]}
                                     for arc in ('tl', 'tr', 'br', 'bl')]
        # Four equivalent triggers form one conditional, and endpoints in
        # the same neighborhood count once: 21 * .8 = 16.8.
        self.assertEqual(ordered_clues(state), [(0, 0), (2, 3), (2, 2), (0, 4)])
        state['arc_implications'].append({'if': [3, 2, 'br'], 'then': [3, 1, ['tl']]})
        state['arc_implications'].append({'if': [1, 2, 'br'], 'then': [0, 2, ['tl']]})
        self.assertEqual(ordered_clues(state), [(0, 0), (2, 2), (2, 3), (0, 4)])

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

    def test_remaining_clues_are_reranked_after_each_result(self):
        editor, callbacks = self.editor()
        editor.state = {'rows': 1, 'columns': 7, 'cells': blank_grid(1, 7)}
        for c, number in [(0, 1), (3, 10), (6, 11)]:
            editor.state['cells'][0][c]['number'] = number
        seen = []
        def engine(state, selected, **kwargs):
            seen.append(selected)
            return ClueAnalysis(source_clue=selected)
        def incorporate(state, result):
            if result.source_clue == (0, 0):
                state['arc_implications'] = [{'if': [0, 6, 'tl'], 'then': [0, 5, ['tr']]}]
            return {'removed': 0, 'applied': False}
        with patch('puzzle_gui.threading.Thread', ImmediateThread), \
                patch('incremental_analysis.analyze_clue_incremental', side_effect=engine), \
                patch('clue_analysis.incorporate_analysis', side_effect=incorporate):
            editor.analyze_all_clues()
            while callbacks:
                callbacks.pop(0)()
        self.assertEqual(seen, [(0, 0), (0, 6), (0, 3)])

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
