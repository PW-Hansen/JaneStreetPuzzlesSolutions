import copy
import tempfile
import unittest
from pathlib import Path

from functions.hooks import hook_cells, partition_borders
from functions.model import Puzzle, read, write
from functions.pentominoes import HookContext, PentominoSearch, Placement, has_filled_square
from functions.rendering import draw
from pentomino_fixtures import example_puzzle, finish


def propagation_context(remove=()):
    squares = [(3,3,1),(2,2,2),(1,1,3),(0,0,4),(0,0,5),(0,0,6),(0,0,7)]
    hooks = [[(3,3)]] + [hook_cells(inner, outer) for inner,outer in zip(squares,squares[1:])]
    puzzle = Puzzle('Propagation', 7, 7)
    filled = {(3,3):1, (2,2):2, (1,1):3, (1,3):3,
              (0,2):4, (0,3):4, (1,0):4, (2,0):4,
              (1,4):5, (2,4):5, (4,1):5, (4,2):5}
    for cell in remove:
        filled.pop(cell, None)
    puzzle.data['entries'] = {f'{r},{c}':str(digit) for (r,c),digit in filled.items()}
    return HookContext(puzzle.data, partition_borders(hooks, 7, 7))


class HookPropagationTests(unittest.TestCase):
    def search(self):
        return PentominoSearch(example_puzzle().data)

    def test_forced_two_reveals_impossible_remaining_three(self):
        context = propagation_context()
        search = self.search()
        self.assertIsNotNone(context.constraints([]))
        self.assertTrue(has_filled_square(set(context.filled) | {(2,3)}))
        self.assertFalse(has_filled_square(set(context.filled) | {(3,2)}))
        occupied = set(context.filled) | {(3,2)}
        self.assertTrue(all(has_filled_square(occupied | {cell}) for cell in context.hooks[2]-occupied))
        self.assertIsNone(finish(search.propagate_hooks(context, [], tuple(range(1,8)))))
        self.assertIsNone(finish(search.witness(context, [], propagate=True)))

    def test_completes_two_then_three_and_stops_at_next_ambiguous_hook(self):
        context = propagation_context(remove=((4,2),))
        forced = finish(self.search().propagate_hooks(context, [], tuple(range(1,8))))
        self.assertEqual(forced, {(3,2):2, (3,1):3})
        self.assertEqual(len(context.hooks[1] & (set(context.filled) | set(forced))), 2)
        self.assertEqual(len(context.hooks[2] & (set(context.filled) | set(forced))), 3)

    def test_does_not_guess_or_move_past_smallest_unfinished_hook(self):
        context = propagation_context(remove=((1,4),(2,4)))
        self.assertEqual(finish(self.search().propagate_hooks(context, [], tuple(range(1,8)))), {})

    def test_multiple_added_digits_are_checked_together(self):
        context = propagation_context()
        context.digits = {(3,3):1, (1,2):3, (1,3):3}
        context.filled = frozenset(context.digits)
        reserved = Placement('I', frozenset(), frozenset({(3,2)}))
        self.assertFalse(has_filled_square(set(context.filled) | {(2,2)}))
        self.assertFalse(has_filled_square(set(context.filled) | {(2,3)}))
        self.assertIsNone(finish(self.search().propagate_hooks(context, [reserved], tuple(range(1,8)))))

    def test_forced_digits_are_speculative_and_roundtrip_with_preview(self):
        context = propagation_context(remove=((4,2),))
        search = self.search()
        forced = finish(search.propagate_hooks(context, [], tuple(range(1,8))))
        piece = Placement('I', frozenset((r,6) for r in range(5)), frozenset())
        record = search.record(context, 0, [piece], tuple(range(1,8)), forced)
        self.assertEqual(record['forced_entries'], {'3,1':'3', '3,2':'2'})
        # Use a valid five-cell I footprint to exercise persistence and rendering
        # without modifying confirmed entries in the working puzzle.
        puzzle = Puzzle('Propagation preview', 7, 7)
        puzzle.data = copy.deepcopy(context.data)
        puzzle.data['analysis'] = dict(source_entries=copy.deepcopy(puzzle.data['entries']),
            candidates=[context.borders], canonical_borders=context.borders, preview=0,
            outcome='complete', elapsed=0.0, nodes=1)
        from functions.pentominoes import hook_digest
        puzzle.data['pentomino_analysis'] = dict(source_entries=copy.deepcopy(puzzle.data['entries']),
            source_borders={}, source_hook_digest=hook_digest(puzzle.data), candidates=[record], placements=[],
            view='combinations', preview=0, outcome='complete', elapsed=0.0, nodes=1)
        original_entries = dict(puzzle.data['entries'])
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder)/'forced.json'
            write(path, puzzle.data)
            restored = read(path)
        self.assertEqual(restored['pentomino_analysis']['candidates'][0]['forced_entries'], record['forced_entries'])
        texts = {}
        draw(restored, lambda *args: None, lambda *args: None,
             lambda pos,value,color: texts.update({pos:(value,color)}))
        self.assertEqual(texts[(210,270)], ('2','black'))
        self.assertEqual(puzzle.data['entries'], original_entries)


if __name__ == '__main__':
    unittest.main()
