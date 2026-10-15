import unittest

from functions.hooks import hook_cells, partition_borders
from functions.model import Puzzle
from functions.pentominoes import HookContext, Placement, PentominoSearch
from pentomino_fixtures import example_puzzle, finish


def numeric_context(clue='3,-1'):
    puzzle = Puzzle('Numeric visibility',9,9)
    puzzle.data['entries'] = {f'{r},0':str(r+1) for r in range(9) if r != 3}
    puzzle.data['entries']['0,3'] = '4'
    puzzle.data['entries'][clue] = '6'
    hooks = [[(0,0)]]+[hook_cells((0,0,size-1),(0,0,size)) for size in range(2,10)]
    return HookContext(puzzle.data, partition_borders(hooks,9,9))


class NumericVisibilityTests(unittest.TestCase):
    def test_first_filled_four_cannot_satisfy_outside_six(self):
        context = numeric_context()
        self.assertIsNotNone(context.constraints([]))
        piece = Placement('I', frozenset((r,0) for r in range(3,8)), frozenset())
        self.assertIsNone(context.constraints([piece]))
        self.assertIsNone(finish(PentominoSearch(example_puzzle().data).witness(context,[piece])))

    def test_empty_prefix_can_later_receive_matching_digit(self):
        context = numeric_context()
        # A later 7 does not obstruct a possible 6 in an earlier blank cell.
        later = Placement('I',frozenset({(3,6)}),frozenset())
        self.assertIsNotNone(context.constraints([later]))
        matching = Placement('I',frozenset({(3,5)}),frozenset())
        self.assertIsNotNone(context.constraints([matching]))
        blocked = Placement('I',frozenset({(3,5)}),frozenset({(3,4)}))
        self.assertIsNotNone(context.constraints([blocked]))
        no_matching_room = Placement('I',frozenset({(3,6)}),frozenset({(3,5)}))
        self.assertIsNone(context.constraints([no_matching_room]))

    def test_numeric_sightlines_from_each_side(self):
        for clue, edge in [('3,-1',(3,0)), ('3,9',(3,8)), ('9,3',(8,3))]:
            context = numeric_context(clue)
            self.assertIsNotNone(context.constraints([]), clue)
            self.assertIsNone(context.constraints([Placement('I',frozenset({edge}),frozenset())]), clue)
        context = numeric_context('-1,3')
        # Top-side clue immediately sees the confirmed 4.
        self.assertIsNone(context.constraints([]))


if __name__ == '__main__':
    unittest.main()
