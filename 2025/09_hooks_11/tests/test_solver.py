import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from functions.analysis_workflow import create_analysis
from functions.constants import INITIAL_STATE_NAME, SOLVED_STATE_NAME, SOLVER_OPERATIONS
from functions.model import read, write, save_snapshot
from functions.solver import solve_named_puzzle, load_initial_puzzle
from pentomino_fixtures import example_puzzle, nine_cell_side_pentomino_puzzle
import solve_puzzle


class SolverTests(unittest.TestCase):
    def folder(self):
        folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(folder.cleanup)
        return Path(folder.name)

    def save_initial(self, root, puzzle):
        path = root/'saved states'/puzzle.data['name']/f'{INITIAL_STATE_NAME}.json'
        save_snapshot(path, puzzle, None)
        return path

    def test_runs_shared_steps_but_does_not_export_incomplete_single_candidate(self):
        root = self.folder()
        puzzle = nine_cell_side_pentomino_puzzle()
        source = self.save_initial(root,puzzle)
        initial_bytes = source.read_bytes()
        working = root/'grids'/f"{puzzle.data['name']}.json"
        write(working,puzzle.data)
        working_bytes = working.read_bytes()
        calls, messages = [], []

        def bounded_create(current, operation):
            calls.append(operation)
            search = create_analysis(current,operation)
            if operation == 'remaining pentominoes':
                search.candidate_limit = 1
            return search

        with patch('functions.solver.create_analysis',side_effect=bounded_create):
            result = solve_named_puzzle(root,puzzle.data['name'],report=messages.append)
        self.assertEqual(calls,list(SOLVER_OPERATIONS))
        self.assertEqual([stage['operation'] for stage in result.stages],list(SOLVER_OPERATIONS))
        self.assertEqual(result.status,'inconclusive')
        self.assertIsNone(result.snapshot)
        self.assertIsNone(result.png)
        self.assertIsNone(result.answer)
        self.assertFalse((root/f'{SOLVED_STATE_NAME}.png').exists())
        self.assertEqual(len(result.puzzle.data['pentomino_analysis']['extensions']),1)
        self.assertEqual(source.read_bytes(),initial_bytes)
        self.assertEqual(working.read_bytes(),working_bytes)
        self.assertTrue(any('incomplete' in message for message in messages))

    def test_no_candidates_preserves_existing_exports(self):
        root = self.folder()
        puzzle = example_puzzle()
        self.save_initial(root,puzzle)
        snapshot = root/'saved states'/puzzle.data['name']/f'{SOLVED_STATE_NAME}.json'
        png = root/f'{SOLVED_STATE_NAME}.png'
        snapshot.write_bytes(b'existing snapshot')
        png.write_bytes(b'existing image')
        result = solve_named_puzzle(root,puzzle.data['name'],report=lambda message:None)
        self.assertEqual(result.status,'inconclusive')
        self.assertEqual(len(result.stages),3)
        self.assertIsNone(result.snapshot)
        self.assertIsNone(result.png)
        self.assertEqual(snapshot.read_bytes(),b'existing snapshot')
        self.assertEqual(png.read_bytes(),b'existing image')

    def test_export_requires_exactly_one_candidate_from_complete_search(self):
        for count in (1,2):
            root = self.folder()
            puzzle = nine_cell_side_pentomino_puzzle()
            self.save_initial(root,puzzle)

            def fixture_search(current,operation):
                search = create_analysis(current,operation)
                if operation == 'remaining pentominoes':
                    search.candidate_limit = count
                    original_run = search.run

                    def run():
                        yield from original_run()
                        # Simulate an exhaustive final result with the requested
                        # cardinality to isolate the workflow's export decision.
                        search.outcome = 'complete'

                    search.run = run
                return search

            messages = []
            with patch('functions.solver.create_analysis',side_effect=fixture_search):
                result = solve_named_puzzle(root,puzzle.data['name'],report=messages.append)
            self.assertEqual(len(result.puzzle.data['pentomino_analysis']['extensions']),count)
            if count == 1:
                self.assertEqual(result.status,'complete')
                self.assertTrue(result.png.is_file())
                self.assertEqual(read(result.snapshot),result.puzzle.data)
                self.assertIsNone(result.answer)  # this fixture is only a partial grid
                self.assertTrue(any('Answer key unavailable' in message for message in messages))
            else:
                self.assertEqual(result.status,'inconclusive')
                self.assertIsNone(result.png)
                self.assertIsNone(result.snapshot)
                self.assertFalse((root/f'{SOLVED_STATE_NAME}.png').exists())
                self.assertTrue(any('Inconclusive result' in message for message in messages))

    def test_missing_initial_state_and_mismatched_identity_fail(self):
        root = self.folder()
        with self.assertRaises(FileNotFoundError):
            load_initial_puzzle(root,'Missing')
        puzzle = example_puzzle()
        write(root/'saved states'/'Other'/'initial_state.json',puzzle.data)
        with self.assertRaisesRegex(ValueError,'different named puzzle'):
            load_initial_puzzle(root,'Other')
        self.assertFalse((root/'solved_state.png').exists())

    def test_cli_dispatch_and_exit_codes(self):
        for status,code in [('complete',0),('inconclusive',2)]:
            with patch('solve_puzzle.solve_named_puzzle',return_value=SimpleNamespace(status=status)) as mocked:
                self.assertEqual(solve_puzzle.main(['Named puzzle']),code)
                self.assertEqual(mocked.call_args.args[1],'Named puzzle')
        with patch('solve_puzzle.solve_named_puzzle',side_effect=ValueError('Invalid state')):
            with redirect_stderr(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as stopped:
                    solve_puzzle.main(['Named puzzle'])
            self.assertEqual(stopped.exception.code,1)
            self.assertIn('Invalid state',output.getvalue())


if __name__ == '__main__':
    unittest.main()
