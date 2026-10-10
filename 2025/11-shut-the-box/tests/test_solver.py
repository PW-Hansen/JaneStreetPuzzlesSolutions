import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from functions.model import Puzzle
from functions.storage import Storage
from functions.solver import load_initial_puzzle, solve_named_puzzle


class SolverTests(unittest.TestCase):
    def test_explicit_initial_folder_precedes_standard_snapshot(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            puzzle = Puzzle('test', 2, 2)
            storage.save(puzzle, storage.snapshot_path('test', 'initial_state'))
            puzzle.edit(0, 'Digit Entering', digit='3')
            explicit = Path(directory) / 'saved_states_test' / 'initial_state.json'
            storage.save(puzzle, explicit)
            loaded, source = load_initial_puzzle(storage, 'test')
            self.assertEqual(source, explicit)
            self.assertEqual(loaded.cells[0]['digit'], '3')

    def test_missing_snapshot_uses_original_instead_of_current_edits(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            puzzle = Puzzle('test', 2, 2)
            puzzle.edit(0, 'Digit Entering', digit='3')
            storage.save(puzzle)
            loaded, source = load_initial_puzzle(storage, 'test')
            self.assertIsNone(source)
            self.assertIsNone(loaded.cells[0]['digit'])
            self.assertFalse(loaded.undo_stack)

    def test_no_fold_does_not_export_or_replace_working_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            puzzle = Puzzle('test', 2, 2)
            puzzle.selected = 0
            storage.save(puzzle)
            before = storage.working_path('test').read_bytes()
            with patch('functions.solver.folding_trials', return_value=iter([])):
                result = solve_named_puzzle(storage, 'test', report=lambda text: None)
            self.assertEqual(result.status, 'no fold')
            self.assertFalse(storage.snapshot_path('test', 'solved_state').exists())
            self.assertFalse((Path(directory) / 'solved_state.png').exists())
            self.assertEqual(storage.working_path('test').read_bytes(), before)

    def test_actual_initial_puzzle_pipeline_exports_matching_solution(self):
        project = Path(__file__).resolve().parents[1]
        source_storage = Storage(project)
        initial = source_storage.load(source_storage.snapshot_path('puzzle', 'initial_state'), 'puzzle')
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            storage.save(initial, storage.snapshot_path('puzzle', 'initial_state'))
            config = Path(directory) / 'configs'
            config.mkdir()
            (config / 'puzzle.json').write_text(json.dumps({'fold_anchor': [6, 9]}))
            messages = []
            result = solve_named_puzzle(storage, 'puzzle', report=messages.append)
            self.assertEqual(result.status, 'solved')
            self.assertEqual(result.survivors, 1)
            self.assertEqual(storage.load(result.snapshot, 'puzzle').cells, result.puzzle.cells)
            self.assertTrue(result.png.exists())
            self.assertEqual(result.png.name, 'solved_state.png')
            self.assertFalse(storage.working_path('puzzle').exists())
            self.assertTrue(any('Answer key:' in message for message in messages))
