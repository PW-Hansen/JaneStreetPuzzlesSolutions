import copy
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from functions.model import read, write, save_snapshot, load_snapshot
from functions.pentominoes import (RemainingPentominoSearch, PentominoSearch, HookContext,
                                  Placement, visible_placement, translated_placements, preview_record)
from pentomino_fixtures import example_puzzle, nine_cell_side_pentomino_puzzle, finish


class RemainingPentominoTests(unittest.TestCase):
    def test_requires_clued_pentomino_combinations(self):
        with self.assertRaisesRegex(ValueError, 'Draw pentominoes first'):
            RemainingPentominoSearch(example_puzzle().data)
        self.assertEqual(list(translated_placements('P', 9, 9)), [])

    def test_three_distinct_unused_shapes_extend_same_base_and_hook_layout(self):
        puzzle = nine_cell_side_pentomino_puzzle()
        search = RemainingPentominoSearch(puzzle.data, candidate_limit=1)
        list(search.run())
        self.assertEqual(search.outcome, 'limit')
        self.assertEqual(len(search.candidates), 1)
        record = search.candidates[0]
        base = puzzle.data['pentomino_analysis']['candidates'][record['base_index']]
        self.assertEqual(record['pieces'][:len(base['pieces'])], base['pieces'])
        self.assertEqual(record['hook_index'], base['hook_index'])
        self.assertEqual(len(record['pieces']), len(base['pieces'])+3)
        names = [piece['shape'] for piece in record['pieces']]
        self.assertEqual(len(set(names)), len(names))
        self.assertNotIn('P', names)
        context = HookContext(puzzle.data, puzzle.data['analysis']['candidates'][record['hook_index']])
        pieces = []
        for piece in record['pieces']:
            cells = frozenset(tuple(map(int,key.split(','))) for key in piece['cells'])
            if piece['shape'] in search.clues:
                pieces.append(visible_placement(piece['shape'], cells, search.clues, context.filled))
            else:
                pieces.append(Placement(piece['shape'], cells, frozenset()))
            self.assertEqual(sum(int(record['entries'][key]) for key in piece['cells']) % 5, 0)
        self.assertIsNotNone(finish(search.witness(context, pieces)))
        occupied = set(context.filled).union(*(piece.cells for piece in pieces))
        counts = Counter(context.owner[cell] for cell in occupied)
        self.assertTrue(all(count <= record['hook_digits'][index] for index,count in counts.items()))

    def test_impossible_extensions_discard_base_and_unsupported_hook(self):
        puzzle = example_puzzle()
        initial = PentominoSearch(puzzle.data)
        list(initial.run())
        puzzle.set_pentomino_analysis(initial, 0.01)
        original = copy.deepcopy(puzzle.data)
        search = RemainingPentominoSearch(puzzle.data)
        list(search.run())
        self.assertEqual(search.outcome, 'complete')
        self.assertEqual(search.rejected_combinations, {0})
        puzzle.set_remaining_pentomino_analysis(search, 0.01)
        self.assertEqual(puzzle.data['pentomino_analysis']['candidates'], [])
        self.assertEqual(puzzle.data['analysis']['candidates'], [])
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], {})
        puzzle.undo()
        self.assertEqual(puzzle.data, original)
        puzzle.redo()
        self.assertEqual(puzzle.data['pentomino_analysis']['extensions'], [])

    def test_incomplete_base_search_does_not_discard_unsupported_hooks(self):
        puzzle = example_puzzle()
        initial = PentominoSearch(puzzle.data)
        list(initial.run())
        puzzle.set_pentomino_analysis(initial, 0.01)
        puzzle.data['pentomino_analysis']['outcome'] = 'limit'
        hooks = copy.deepcopy(puzzle.data['analysis'])
        search = RemainingPentominoSearch(puzzle.data)
        list(search.run())
        self.assertEqual(search.rejected_combinations, {0})
        puzzle.set_remaining_pentomino_analysis(search, 0.01)
        self.assertEqual(puzzle.data['analysis'], hooks)

    def test_limits_and_abort_keep_unproven_combinations(self):
        puzzle = nine_cell_side_pentomino_puzzle()
        original = copy.deepcopy(puzzle.data)
        for limits in ({'node_limit':1}, {'placement_limit':0}):
            search = RemainingPentominoSearch(puzzle.data, **limits)
            list(search.run())
            self.assertEqual(search.outcome, 'limit')
            self.assertFalse(search.rejected_combinations)
        search = RemainingPentominoSearch(puzzle.data)
        steps = search.run()
        next(steps)
        search.cancelled = True
        list(steps)
        self.assertEqual(search.outcome, 'cancelled')
        puzzle.set_remaining_pentomino_analysis(search, 0.01)
        self.assertEqual(puzzle.data['pentomino_analysis']['candidates'], original['pentomino_analysis']['candidates'])
        self.assertEqual(puzzle.data['analysis']['candidates'], original['analysis']['candidates'])

    def test_extension_preview_persistence_history_and_invalidation(self):
        puzzle = nine_cell_side_pentomino_puzzle()
        original = copy.deepcopy(puzzle.data)
        search = RemainingPentominoSearch(puzzle.data, candidate_limit=1)
        list(search.run())
        puzzle.set_remaining_pentomino_analysis(search, 0.02)
        analyzed = copy.deepcopy(puzzle.data)
        self.assertEqual(puzzle.data['entries'], original['entries'])
        self.assertEqual(puzzle.data['pentomino_analysis']['view'], 'extensions')
        self.assertEqual(len(preview_record(puzzle.data)['pieces']), 4)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path, snapshot = Path(folder)/'working.json', Path(folder)/'snapshot.json'
            write(path, puzzle.data)
            self.assertEqual(read(path), analyzed)
            save_snapshot(snapshot, puzzle, None)
            puzzle.change('entries','8,8','9')
            self.assertNotIn('pentomino_analysis', puzzle.data)
            load_snapshot(snapshot, puzzle)
            self.assertEqual(puzzle.data, analyzed)
        puzzle.undo_stack = [original]
        puzzle.undo()
        self.assertEqual(puzzle.data, original)
        puzzle.redo()
        self.assertEqual(puzzle.data, analyzed)


if __name__ == '__main__':
    unittest.main()
