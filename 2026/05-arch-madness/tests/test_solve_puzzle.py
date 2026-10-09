import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from puzzle_gui import blank_grid, validate_state
import solve_puzzle as solver


class CommandLineSolverTests(unittest.TestCase):
    def setUp(self):
        self.state = {'rows': 1, 'columns': 1, 'cells': blank_grid(1, 1)}
        self.state['cells'][0][0]['number'] = 4

    def test_initial_snapshot_required_and_loaded(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            with self.assertRaisesRegex(ValueError, 'Initial state not found'):
                solver.load_initial_state('tiny', folder)
            path = Path(folder) / 'tiny' / 'initial_state.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'puzzle_name': 'tiny', 'state': self.state}))
            self.assertEqual(solver.load_initial_state('tiny', folder)['cells'], self.state['cells'])
            with self.assertRaisesRegex(ValueError, 'different puzzle'):
                path.write_text(json.dumps({'puzzle_name': 'other', 'state': self.state}))
                solver.load_initial_state('tiny', folder)

    def test_named_order_and_missing_entry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'orders.json'
            self.assertIsNone(solver.configured_order(self.state, 'tiny', path))
            path.write_text(json.dumps({'tiny': [{'row': 1, 'column': 1, 'clue': 4}]}))
            self.assertEqual(solver.configured_order(self.state, 'tiny', path), [(0, 0)])
            self.assertIsNone(solver.configured_order(self.state, 'other', path))

    def test_default_cli_uses_dynamic_order_without_prompt(self):
        with patch.object(solver, 'load_initial_state', return_value=self.state), \
                patch.object(solver, 'configured_order') as order, \
                patch.object(solver, 'prompt_weights') as prompt, \
                patch.object(solver, 'solve') as solve, patch('builtins.print'):
            self.assertEqual(solver.main(['tiny']), 0)
            order.assert_not_called()
            prompt.assert_not_called()
            self.assertIsNone(solve.call_args.args[3])
            self.assertEqual(solve.call_args.args[4], (.8, .5, .75))

    def test_custom_weights_and_cancellation(self):
        with patch.object(solver, 'load_initial_state', return_value=self.state), \
                patch.object(solver, 'prompt_weights', return_value=(.7, .4, .6)) as prompt, \
                patch.object(solver, 'solve') as solve, patch('builtins.print'):
            self.assertEqual(solver.main(['tiny', '--custom-weights']), 0)
            prompt.assert_called_once_with()
            self.assertEqual(solve.call_args.args[4], (.7, .4, .6))
            solve.reset_mock()
            prompt.return_value = None
            self.assertEqual(solver.main(['tiny', '--custom-weights']), 0)
            solve.assert_not_called()

    def test_missing_set_order_is_an_error(self):
        with patch.object(solver, 'load_initial_state', return_value=self.state), \
                patch.object(solver, 'configured_order', return_value=None), \
                patch.object(solver, 'solve') as solve, patch('sys.stderr'):
            with self.assertRaises(SystemExit) as error:
                solver.main(['tiny', '--set'])
            self.assertEqual(error.exception.code, 1)
            solve.assert_not_called()

    def test_real_search_writes_loadable_result_without_changing_input(self):
        before = copy.deepcopy(self.state)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            output = Path(folder) / 'solved_state.json'
            messages = []
            result = solver.solve(self.state, 'tiny', output, log=messages.append)
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot['puzzle_name'], 'tiny')
            self.assertEqual(validate_state(snapshot['state'])['cells'], result['cells'])
            self.assertTrue(any('Puzzle verified complete' in text for text in messages))
            self.assertTrue(any('Answer key: 32' in text for text in messages))
            self.assertEqual(self.state, before)

    def test_configured_cli_order_skips_weight_prompt(self):
        with patch.object(solver, 'load_initial_state', return_value=self.state), \
                patch.object(solver, 'configured_order', return_value=[(0, 0)]), \
                patch.object(solver, 'prompt_weights') as prompt, \
                patch.object(solver, 'solve') as solve, patch('builtins.print'):
            self.assertEqual(solver.main(['tiny', '--set']), 0)
            prompt.assert_not_called()
            self.assertEqual(solve.call_args.args[3], [(0, 0)])

    def test_stalled_invalid_grid_only_saves_checkpoint(self):
        self.state['cells'][0][0]['number'] = 3
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            output = Path(folder) / 'solved_state.json'
            with patch.object(solver, 'scan_local_conditionals',
                              return_value=(copy.deepcopy(self.state), {'removed': 0})):
                solver.solve(self.state, 'tiny', output, order=[], log=lambda _: None)
            self.assertFalse(output.exists())
            checkpoint = json.loads((Path(folder) / 'checkpoint_state.json').read_text())
            self.assertEqual(checkpoint['state']['cells'][0][0]['number'], 3)

    def test_crash_preserves_checkpoint_and_existing_solution(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            output = Path(folder) / 'solved_state.json'
            output.write_text('previous verified solution')
            with patch.object(solver, 'analyze_clue_with_sanity', side_effect=AttributeError('crash')):
                with self.assertRaisesRegex(AttributeError, 'crash'):
                    solver.solve(self.state, 'tiny', output, log=lambda _: None)
            self.assertEqual(output.read_text(), 'previous verified solution')
            checkpoint = json.loads((Path(folder) / 'checkpoint_state.json').read_text())
            self.assertEqual(checkpoint['state']['cells'], self.state['cells'])


if __name__ == '__main__':
    unittest.main()
