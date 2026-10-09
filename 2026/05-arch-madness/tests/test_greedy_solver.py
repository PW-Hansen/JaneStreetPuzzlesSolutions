import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from functions.clue_analysis import ClueAnalysis
from functions.solver_analysis import GreedySolveSession
from puzzle_gui import blank_grid
import solve_puzzle


class GreedySolverTests(unittest.TestCase):
    def fixture(self, count):
        state = {'rows': 1, 'columns': count, 'cells': blank_grid(1, count), 'deductions': []}
        for c in range(count):
            state['cells'][0][c]['number'] = c + 1
        return state

    def apply(self, state, result):
        self.assertFalse(result.heuristic)
        r, c, arc = result.accepted_states[0][0]
        state['cells'][r][c]['arc'] = arc
        state['deductions'].append((c, arc))
        state['arc_domains'] = [[[cell['arc']] if cell['arc'] else [None, 'tl', 'tr']
                                for cell in state['cells'][0]]]
        state.setdefault('saved_analyses', {})[str(c)] = arc

    def result(self, selected, greedy, failed=False):
        return ClueAnalysis(source_clue=selected, heuristic=greedy,
            accepted_states=[] if failed else [((*selected, 'tl' if greedy else 'tr'),)])

    def session(self, state, order):
        logs, checkpoints = [], []
        session = GreedySolveSession(state, order, (.8, 1, 1), {}, logs.append,
                                    lambda value: checkpoints.append(copy.deepcopy(value)))
        return session, logs, checkpoints

    def test_failed_d_retries_normally_then_cascades_c_and_b(self):
        state = self.fixture(4)
        before = copy.deepcopy(state)
        calls = []
        def greedy(current, selected, **kwargs):
            calls.append(('greedy', selected[1]))
            return self.result(selected, True, selected[1] == 3)
        def normal(current, selected, **kwargs):
            calls.append(('normal', selected[1]))
            fail = (selected[1] == 3 and current['cells'][0][2]['arc'] == 'tl'
                    or selected[1] == 2 and current['cells'][0][1]['arc'] == 'tl')
            return self.result(selected, False, fail)
        session, logs, checkpoints = self.session(state, [(0, c) for c in range(4)])
        with patch('functions.solver_analysis.analyze_clue_greedy', side_effect=greedy), \
                patch('functions.solver_analysis.analyze_clue_with_sanity', side_effect=normal), \
                patch('functions.solver_analysis.incorporate_analysis', side_effect=self.apply), \
                patch('functions.solver_analysis.save_accepted_states'), \
                patch('functions.solver_analysis.prune_saved_states'), \
                patch('functions.solver_analysis.determined_grid', return_value=False), \
                patch('functions.solver_analysis.verified_grid',
                      side_effect=lambda value: value['deductions'] == [(0, 'tl'), (1, 'tr'), (2, 'tr'), (3, 'tr')]):
            result = session.run()
        self.assertEqual(calls, [('greedy', 0), ('greedy', 1), ('greedy', 2), ('greedy', 3),
                                 ('normal', 3), ('normal', 2), ('normal', 1), ('normal', 2), ('normal', 3)])
        self.assertEqual(result['deductions'], [(0, 'tl'), (1, 'tr'), (2, 'tr'), (3, 'tr')])
        self.assertEqual(result['saved_analyses'], {'0': 'tl', '1': 'tr', '2': 'tr', '3': 'tr'})
        self.assertEqual(result['arc_domains'][0], [['tl'], ['tr'], ['tr'], ['tr']])
        self.assertEqual(state, before)
        self.assertTrue(any('Restoring' in message for message in logs))
        self.assertTrue(any(value['deductions'] == [(0, 'tl')] for value in checkpoints))

    def test_invalid_completed_grid_cascades_until_greedy_assumptions_are_removed(self):
        state = self.fixture(2)
        calls = []
        def engine(greedy):
            def run(current, selected, **kwargs):
                calls.append(('greedy' if greedy else 'normal', selected[1]))
                return self.result(selected, greedy)
            return run
        session, _, _ = self.session(state, [(0, 0), (0, 1)])
        with patch('functions.solver_analysis.analyze_clue_greedy', side_effect=engine(True)), \
                patch('functions.solver_analysis.analyze_clue_with_sanity', side_effect=engine(False)), \
                patch('functions.solver_analysis.incorporate_analysis', side_effect=self.apply), \
                patch('functions.solver_analysis.save_accepted_states'), \
                patch('functions.solver_analysis.prune_saved_states'), \
                patch('functions.solver_analysis.determined_grid',
                      side_effect=lambda value: all(cell['arc'] for cell in value['cells'][0])), \
                patch('functions.solver_analysis.verified_grid',
                      side_effect=lambda value: all(cell['arc'] == 'tr' for cell in value['cells'][0])):
            result = session.run()
        self.assertEqual(calls, [('greedy', 0), ('greedy', 1), ('normal', 1), ('normal', 0), ('normal', 1)])
        self.assertEqual(result['deductions'], [(0, 'tr'), (1, 'tr')])

    def test_real_greedy_solver_writes_verified_solution(self):
        state = {'rows': 2, 'columns': 3, 'cells': blank_grid(2, 3)}
        state['cells'][0][0]['number'] = 24
        before = copy.deepcopy(state)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            output = Path(folder) / 'solved_state.json'
            solve_puzzle.solve(state, 'tiny', output, greedy=True, log=lambda _: None)
            self.assertTrue(output.exists())
            self.assertEqual(state, before)

    def test_keyword_enables_greedy_solver(self):
        with patch.object(solve_puzzle, 'load_initial_state', return_value=self.fixture(1)), \
                patch.object(solve_puzzle, 'configured_order', return_value=[(0, 0)]), \
                patch.object(solve_puzzle, 'solve') as solve, patch('builtins.print'):
            self.assertEqual(solve_puzzle.main(['tiny', '-greedy']), 0)
            self.assertTrue(solve.call_args.kwargs['greedy'])

    def test_exhausted_fallback_only_writes_checkpoint(self):
        state = {'rows': 1, 'columns': 1, 'cells': blank_grid(1, 1)}
        state['cells'][0][0]['number'] = 4
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            output = Path(folder) / 'solved_state.json'
            with patch('functions.solver_analysis.analyze_clue_greedy', return_value=ClueAnalysis()), \
                    patch('functions.solver_analysis.analyze_clue_with_sanity', return_value=ClueAnalysis()):
                with self.assertRaisesRegex(ValueError, 'No greedy deductions remain'):
                    solve_puzzle.solve(state, 'tiny', output, greedy=True, log=lambda _: None)
            self.assertFalse(output.exists())
            self.assertTrue((Path(folder) / 'checkpoint_state.json').exists())


if __name__ == '__main__':
    unittest.main()
