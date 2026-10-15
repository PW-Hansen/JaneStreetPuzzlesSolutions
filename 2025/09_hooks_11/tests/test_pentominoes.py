import copy
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from functions.constants import PENTOMINO_SHAPES
from functions.model import Puzzle, read, write, save_snapshot, load_snapshot
from functions.pentominoes import (PentominoSearch, HookContext, Placement, orientations,
                                  clue_rays, visible_placement, has_filled_square, preview_record)
from functions.rendering import draw
from functions.hooks import HookSearch, canonical_borders
from pentomino_fixtures import example_puzzle, nested_context_data, finish


class PentominoTests(unittest.TestCase):
    def test_filling_cannot_block_outside_two_view_of_three_cell_hook(self):
        data, borders = nested_context_data()
        data['entries']['5,1'] = '2'
        context = HookContext(data, borders)
        self.assertIsNotNone(context.constraints([]))
        blocker = Placement('I', frozenset({(4,1)}), frozenset())
        self.assertIsNone(context.constraints([blocker]))
        data['entries']['5,1'] = '3'
        context = HookContext(data, borders)
        self.assertIsNotNone(context.constraints([blocker]))

    def test_prunes_incompatible_hook_layout_and_confirms_sole_survivor(self):
        puzzle = example_puzzle()
        original = copy.deepcopy(puzzle.data)
        search = PentominoSearch(puzzle.data)
        list(search.run())
        self.assertEqual(search.rejected_layouts, {0})
        self.assertTrue(any(record['hook_index'] == 0 for record in search.placements))
        puzzle.set_pentomino_analysis(search, 0.25)
        hooks = puzzle.data['analysis']
        self.assertEqual(hooks['candidates'], [original['analysis']['candidates'][1]])
        self.assertEqual(hooks['canonical_borders'], hooks['candidates'][0])
        self.assertEqual(hooks['preview'], 0)
        self.assertEqual(puzzle.data['pentomino_analysis']['discarded_hook_layouts'], 1)
        for record in puzzle.data['pentomino_analysis']['candidates'] + puzzle.data['pentomino_analysis']['placements']:
            self.assertEqual(record['hook_index'], 0)
        pruned = copy.deepcopy(puzzle.data)
        puzzle.undo()
        self.assertEqual(puzzle.data, original)
        puzzle.redo()
        self.assertEqual(puzzle.data, pruned)

    def test_unfinished_layouts_survive_but_proven_rejections_do_not(self):
        puzzle = example_puzzle()
        original = copy.deepcopy(puzzle.data)
        limited = PentominoSearch(puzzle.data, node_limit=3)
        list(limited.run())
        self.assertEqual(limited.rejected_layouts, set())
        puzzle.set_pentomino_analysis(limited, 0.01)
        self.assertEqual(puzzle.data['analysis']['candidates'], original['analysis']['candidates'])
        puzzle = example_puzzle()
        search = PentominoSearch(puzzle.data)
        steps = search.run()
        while not search.rejected_layouts:
            next(steps)
        search.cancelled = True
        list(steps)
        self.assertEqual(search.outcome, 'cancelled')
        self.assertEqual(search.candidates, [])
        puzzle.set_pentomino_analysis(search, 0.01)
        self.assertEqual(puzzle.data['analysis']['candidates'], [original['analysis']['candidates'][1]])

    def test_all_rejected_layouts_leave_no_canonical_borders(self):
        data, _ = nested_context_data()
        puzzle = Puzzle(data['name'], data['rows'], data['cols'])
        puzzle.data = data
        puzzle.change('entries', '0,-1', 'X')
        hooks = HookSearch(puzzle.data)
        list(hooks.run())
        puzzle.set_hook_analysis(hooks, 0.01)
        search = PentominoSearch(puzzle.data)
        list(search.run())
        self.assertEqual(search.outcome, 'complete')
        self.assertEqual(search.rejected_layouts, {0})
        puzzle.set_pentomino_analysis(search, 0.01)
        self.assertEqual(puzzle.data['analysis']['candidates'], [])
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], {})
        self.assertEqual(puzzle.data['analysis']['preview'], -1)
        self.assertEqual(puzzle.data['pentomino_analysis']['preview'], -1)

    def test_multiple_survivors_confirm_only_shared_borders(self):
        puzzle = Puzzle('Shared', 3, 3)
        puzzle.change('entries', '1,1', '1')
        hooks = HookSearch(puzzle.data)
        list(hooks.run())
        puzzle.set_hook_analysis(hooks, 0.01)
        remaining = copy.deepcopy(puzzle.data['analysis']['candidates'][1:])
        partial = SimpleNamespace(rejected_layouts={0}, candidates=[], placements=[],
                                  outcome='cancelled', nodes=1, source_incomplete=False)
        puzzle.set_pentomino_analysis(partial, 0.01)
        self.assertEqual(puzzle.data['analysis']['candidates'], remaining)
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], canonical_borders(remaining, 'complete'))
        self.assertNotEqual(puzzle.data['analysis']['canonical_borders'], remaining[0])

    def test_all_free_pentomino_orientations(self):
        expected = dict(F=8, I=2, L=8, N=8, P=8, T=4, U=4, V=4, W=4, X=1, Y=8, Z=4)
        all_variants = set()
        for name, shape in PENTOMINO_SHAPES.items():
            variants = orientations(shape)
            self.assertEqual(len(variants), expected[name], name)
            self.assertFalse(all_variants.intersection(variants), name)
            all_variants.update(variants)
            for variant in variants:
                self.assertEqual(len(set(variant)), 5)
                connected, pending = {variant[0]}, [variant[0]]
                while pending:
                    r,c = pending.pop()
                    for cell in variant:
                        if cell not in connected and abs(cell[0]-r)+abs(cell[1]-c) == 1:
                            connected.add(cell)
                            pending.append(cell)
                self.assertEqual(len(connected), 5, name)
        self.assertEqual(len(all_variants), 63)

    def test_four_clue_directions_and_repeated_letter(self):
        puzzle = Puzzle('Rays', 5, 5)
        puzzle.data['entries'] = {'-1,2':'U','5,2':'U','2,-1':'U','2,5':'U'}
        rays = clue_rays(puzzle.data)['U']
        self.assertEqual([ray[0] for ray in rays], [(0,2),(4,2),(2,0),(2,4)])
        cells = {(0,2),(0,4),(1,2),(1,3),(1,4)}
        clues = {'U': (tuple((0,c) for c in range(5)), tuple((1,c) for c in reversed(range(5))))}
        self.assertIsNotNone(visible_placement('U', cells, clues, set()))
        self.assertIsNone(visible_placement('U', cells, clues, {(0,1)}))
        self.assertIsNone(visible_placement('U', {(2,2),(2,4),(3,2),(3,3),(3,4)}, clues, set()))

    def test_requires_hooks_and_outside_clues(self):
        puzzle = Puzzle('Missing', 5, 5)
        with self.assertRaisesRegex(ValueError, 'Draw hooks first'):
            PentominoSearch(puzzle.data)
        puzzle = example_puzzle()
        puzzle.data['entries'] = {key:value for key,value in puzzle.data['entries'].items() if value.isdecimal()}
        with self.assertRaisesRegex(ValueError, 'outside'):
            PentominoSearch(puzzle.data)

    def test_union_quotas_overlap_and_two_by_two(self):
        data, borders = nested_context_data()
        context = HookContext(data, borders)
        # Isolate occupancy constraints using partial footprints.
        first = Placement('I', frozenset({(0,4),(1,4),(2,4)}), frozenset())
        second = Placement('L', frozenset({(3,4),(4,4)}), frozenset())
        self.assertIsNotNone(context.constraints([first]))
        self.assertIsNotNone(context.constraints([second]))
        self.assertIsNone(context.constraints([first, second]))  # six 5s including the given
        self.assertIsNone(context.constraints([first, first]))
        includes_given = Placement('I', frozenset({(4,0),(0,4),(1,4),(2,4),(3,4)}), frozenset())
        self.assertIsNotNone(context.constraints([includes_given]))  # five, not six
        upper = Placement('I', frozenset({(2,2),(2,3)}), frozenset())
        lower = Placement('L', frozenset({(3,2),(3,3)}), frozenset())
        self.assertIsNotNone(context.constraints([upper]))
        self.assertIsNotNone(context.constraints([lower]))
        self.assertIsNone(context.constraints([upper, lower]))

    def test_compatible_visibility_forbids_earlier_other_pentomino(self):
        data, borders = nested_context_data()
        context = HookContext(data, borders)
        target = Placement('U', frozenset({(1,4)}), frozenset({(0,4)}))
        blocker = Placement('F', frozenset({(0,4)}), frozenset())
        self.assertIsNotNone(context.constraints([target]))
        self.assertIsNotNone(context.constraints([blocker]))
        self.assertIsNone(context.constraints([target, blocker]))

    def test_piece_sum_and_unknown_hook_assignments(self):
        puzzle = example_puzzle()
        search = PentominoSearch(puzzle.data)
        data, borders = nested_context_data()
        context = HookContext(data, borders)
        good = Placement('I', frozenset((r,0) for r in range(5)), frozenset())
        self.assertIsNotNone(finish(search.witness(context, [good])))  # 1+2+3+4+5 = 15
        bad = Placement('U', frozenset({(0,0),(0,1),(0,2),(1,0),(1,2)}), frozenset())
        self.assertIsNotNone(context.constraints([bad]))
        self.assertIsNone(finish(search.witness(context, [bad])))  # not a multiple of five
        unknown_data, unknown_borders = nested_context_data(known=False)
        unknown_context = HookContext(unknown_data, unknown_borders)
        assignment = finish(search.witness(unknown_context, [good]))
        self.assertIsNotNone(assignment)
        self.assertEqual(set(assignment), {1,2,3,4,5})
        self.assertEqual(sum(assignment[unknown_context.owner[cell]] for cell in good.cells) % 5, 0)

    def test_joint_unknown_digits_must_share_one_assignment(self):
        data, borders = nested_context_data(known=False)
        context = HookContext(data, borders)
        search = PentominoSearch(example_puzzle().data)
        first = Placement('U', frozenset({(0,0),(0,1),(0,2),(1,0),(1,2)}), frozenset())
        second = Placement('F', frozenset({(2,2),(2,3),(3,3),(3,4),(4,3)}), frozenset())
        self.assertIsNotNone(finish(search.witness(context, [first])))
        self.assertIsNotNone(finish(search.witness(context, [second])))
        self.assertIsNotNone(context.constraints([first, second]))
        self.assertIsNone(finish(search.witness(context, [first, second])))

    def test_full_example_individuals_and_compatible_combinations(self):
        puzzle = example_puzzle()
        search = PentominoSearch(puzzle.data)
        list(search.run())
        self.assertEqual(search.outcome, 'complete')
        self.assertEqual(Counter(record['pieces'][0]['shape'] for record in search.placements), {'F':7, 'U':2, 'Y':4})
        self.assertEqual(len(search.candidates), 1)
        record = search.candidates[0]
        self.assertEqual({piece['shape'] for piece in record['pieces']}, {'F','U','Y'})
        context = HookContext(puzzle.data, puzzle.data['analysis']['candidates'][record['hook_index']])
        pieces = [visible_placement(piece['shape'], {tuple(map(int,key.split(','))) for key in piece['cells']}, search.clues, context.filled) for piece in record['pieces']]
        self.assertTrue(all(pieces))
        self.assertIsNotNone(context.constraints(pieces))
        filled = set(context.filled)
        for piece in record['pieces']:
            filled.update(tuple(map(int,key.split(','))) for key in piece['cells'])
            self.assertEqual(sum(int(record['entries'][key]) for key in piece['cells']) % 5, 0)
        self.assertFalse(has_filled_square(filled))
        self.assertEqual(set(record['entries']), {key for piece in record['pieces'] for key in piece['cells']})

    def test_limits_and_cancellation_are_incomplete(self):
        puzzle = example_puzzle()
        search = PentominoSearch(puzzle.data, node_limit=3)
        list(search.run())
        self.assertEqual(search.outcome, 'limit')
        search = PentominoSearch(puzzle.data, placement_limit=1)
        list(search.run())
        self.assertEqual(search.outcome, 'limit')
        search = PentominoSearch(puzzle.data)
        steps = search.run()
        next(steps)
        search.cancelled = True
        list(steps)
        self.assertEqual(search.outcome, 'cancelled')
        puzzle.data['analysis']['outcome'] = 'limit'
        search = PentominoSearch(puzzle.data)
        list(search.run())
        self.assertEqual(search.outcome, 'limit')
        self.assertTrue(search.source_incomplete)

    def test_persistence_history_invalidation_and_rendering(self):
        puzzle = example_puzzle()
        original = copy.deepcopy(puzzle.data)
        search = PentominoSearch(puzzle.data)
        list(search.run())
        puzzle.set_pentomino_analysis(search, 0.25)
        analyzed = copy.deepcopy(puzzle.data)
        self.assertIsNotNone(preview_record(puzzle.data))
        self.assertEqual(puzzle.data['entries'], original['entries'])
        texts, strokes = {}, []
        draw(puzzle.data, lambda *args: None, lambda *args: strokes.append(args),
             lambda pos,value,color: texts.update({pos:(value,color)}))
        self.assertEqual(texts[(210,90)], ('4','black'))  # speculative filled U cell
        self.assertTrue(any(stroke[1] == '#b0304a' for stroke in strokes))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            working, snapshot = Path(folder)/'working.json', Path(folder)/'snapshot.json'
            write(working, puzzle.data)
            self.assertEqual(read(working), analyzed)
            save_snapshot(snapshot, puzzle, None)
            puzzle.change('entries', '0,1', '4')
            self.assertNotIn('pentomino_analysis', puzzle.data)
            load_snapshot(snapshot, puzzle)
            self.assertEqual(puzzle.data, analyzed)
        puzzle.undo_stack = [original]
        puzzle.undo()
        self.assertNotIn('pentomino_analysis', puzzle.data)
        puzzle.redo()
        self.assertEqual(puzzle.data, analyzed)
        puzzle.preview_pentominoes(0, 'placements')
        self.assertEqual(puzzle.data['pentomino_analysis']['view'], 'placements')
        puzzle.preview_hooks(-1)
        self.assertIsNone(preview_record(puzzle.data))
        puzzle.change('borders', 'h,1,0', True)
        self.assertNotIn('pentomino_analysis', puzzle.data)

    def test_invalid_pentomino_load_preserves_current_state(self):
        puzzle = example_puzzle()
        search = PentominoSearch(puzzle.data)
        list(search.run())
        puzzle.set_pentomino_analysis(search, 0.25)
        original = copy.deepcopy(puzzle.data)
        invalid = copy.deepcopy(original)
        invalid['pentomino_analysis']['candidates'][0]['entries'] = {}
        with self.assertRaises(ValueError):
            puzzle.replace(invalid)
        self.assertEqual(puzzle.data, original)


if __name__ == '__main__':
    unittest.main()
