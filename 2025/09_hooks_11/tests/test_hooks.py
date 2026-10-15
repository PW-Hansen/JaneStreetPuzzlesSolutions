import copy
import math
import tempfile
import unittest
from pathlib import Path

from functions.hooks import (HookSearch, hook_cells, canonical_borders, small_hook_digits_allowed,
                             outside_two_rays, three_cell_hook_visible, available_five_cell_digits,
                             five_cell_digits_from_clues, outside_digit_rays)
from functions.model import Puzzle, read, write, save_snapshot, load_snapshot


def search_grid(n, entries, **limits):
    puzzle = Puzzle('Hooks', n, n)
    for key, value in entries.items():
        puzzle.change('entries', key, value)
    search = HookSearch(puzzle.data, **limits)
    list(search.run())
    return puzzle, search


def regions(borders, n):
    remaining = {(r, c) for r in range(n) for c in range(n)}
    groups = []
    while remaining:
        group = {remaining.pop()}
        pending = list(group)
        while pending:
            r, c = pending.pop()
            for nr, nc, edge in ((r-1, c, f'h,{r},{c}'), (r+1, c, f'h,{r+1},{c}'),
                                 (r, c-1, f'v,{r},{c}'), (r, c+1, f'v,{r},{c+1}')):
                if (nr, nc) in remaining and edge not in borders:
                    remaining.remove((nr, nc))
                    group.add((nr, nc))
                    pending.append((nr, nc))
        groups.append(group)
    return groups


class HookTests(unittest.TestCase):
    def test_five_cell_domain_uses_digits_elsewhere_and_singleton_contact(self):
        cells = hook_cells((0,0,2), (0,0,3))
        self.assertEqual(available_five_cell_digits(cells, (0,0), {}), {3,4,5})
        elsewhere = {(0,3):3, (1,3):4, (2,3):5}
        self.assertEqual(available_five_cell_digits(cells, (0,0), elsewhere), set())
        self.assertEqual(available_five_cell_digits(cells, (0,0), {(0,2):3, (1,2):3}), {3})
        self.assertEqual(available_five_cell_digits(cells, (0,0), {(0,2):3, (0,3):3}), set())
        self.assertEqual(available_five_cell_digits(cells, (0,0), {(0,2):2}), set())
        others = {(0,3):3, (1,3):4}
        self.assertEqual(available_five_cell_digits(cells, (1,1), others), set())
        self.assertEqual(available_five_cell_digits(cells, (0,1), others), {5})

    def test_five_cell_clues_allow_one_three_cell_crossing_but_not_two(self):
        cells, three = {(0,2),(1,2),(2,0),(2,1),(2,2)}, {(0,0),(0,1),(1,0)}
        one = ((1,0),(1,2))
        two = ((0,0),(0,1),(0,2))
        for digit in (3,4,5):
            self.assertEqual(five_cell_digits_from_clues({digit}, cells, three, {digit:[one]}, {}), {digit})
            self.assertEqual(five_cell_digits_from_clues({digit}, cells, three, {digit:[two]}, {}), set())
        # A failed 3-clue eliminates only digit 3, not 4 or 5.
        self.assertEqual(five_cell_digits_from_clues({3,4,5}, cells, three, {3:[two]}, {}), {4,5})
        self.assertEqual(five_cell_digits_from_clues({3}, cells, three, {3:[one,two]}, {}), set())
        self.assertEqual(five_cell_digits_from_clues({3}, cells, three, {3:[one]}, {(1,0):2}), set())
        self.assertEqual(five_cell_digits_from_clues({3}, cells, three, {3:[((0,3),(1,3))]}, {}), set())
        # Cells of the three-cell hook beyond the first five-cell cell do not block it.
        self.assertEqual(five_cell_digits_from_clues({3}, cells, three, {3:[tuple(reversed(two))]}, {}), {3})

    def test_five_cell_outside_clue_rays_from_every_side(self):
        puzzle = Puzzle('Rays', 5, 5)
        puzzle.data['entries'] = {'-1,1':'3', '5,1':'4', '1,-1':'5', '1,5':'3', '0,0':'3'}
        self.assertEqual([ray[0] for ray in outside_digit_rays(puzzle.data, {3,4,5})], [(0,1),(4,1),(1,0),(1,4)])

    def test_hook_search_rejects_five_cell_digit_already_elsewhere(self):
        _, search = search_grid(4, {'0,0':'1', '0,2':'3', '3,0':'3'})
        self.assertEqual(search.candidates, [])

    def test_outside_two_clues_constrain_three_cell_hook_from_each_side(self):
        for key in ('0,-1', '0,3', '-1,0', '3,0'):
            puzzle, search = search_grid(3, {'1,1':'1', key:'2'})
            self.assertEqual(search.outcome, 'complete')
            self.assertEqual(len(search.candidates), 2, key)
            rays = outside_two_rays(puzzle.data)
            for candidate in search.candidates:
                hook = next(group for group in regions(candidate, 3) if len(group) == 3)
                self.assertTrue(three_cell_hook_visible(hook, rays, {(1,1)}))

    def test_outside_two_cannot_look_through_singleton(self):
        _, search = search_grid(3, {'1,1':'1', '1,-1':'2'})
        self.assertEqual(len(search.candidates), 2)
        for candidate in search.candidates:
            hook = next(group for group in regions(candidate, 3) if len(group) == 3)
            self.assertIn((1,0), hook)
            self.assertNotIn((1,2), hook)

    def test_every_outside_two_must_see_same_three_cell_hook(self):
        _, one = search_grid(3, {'1,1':'1', '0,-1':'2', '3,0':'2'})
        self.assertEqual(len(one.candidates), 1)
        _, none = search_grid(3, {'1,1':'1', '0,-1':'2', '2,3':'2'})
        self.assertEqual(none.candidates, [])
        _, other_digits = search_grid(3, {'1,1':'1', '0,-1':'3', '2,3':'4'})
        self.assertEqual(len(other_digits.candidates), 4)

    def test_two_visibility_allows_empty_prefix_but_not_extra_two(self):
        hook = {(0,0),(0,1),(1,0)}
        self.assertTrue(three_cell_hook_visible(hook, [((0,2),(0,1),(0,0))], {(1,1)}))
        self.assertFalse(three_cell_hook_visible(hook, [((0,2),(0,1),(0,0))], {(0,2)}))
        # Both 2s are already filled off this sightline; its only hook cell
        # cannot be filled as an additional 2.
        self.assertFalse(three_cell_hook_visible(hook, [((0,1),(1,1),(2,1))], {(0,0),(1,0),(1,1)}))

    def test_canonical_borders_require_all_complete_layouts(self):
        layouts = [{'h,1,0': True, 'v,0,1': True}, {'h,1,0': True, 'v,1,1': True}]
        self.assertEqual(canonical_borders(layouts, 'complete'), {'h,1,0': True})
        self.assertEqual(canonical_borders(layouts[:1], 'complete'), layouts[0])
        for outcome in ('cancelled', 'limit'):
            self.assertEqual(canonical_borders(layouts[:1], outcome), {})
        self.assertEqual(canonical_borders([], 'complete'), {})

    def test_canonical_borders_are_undoable_and_invalidated_separately(self):
        puzzle, search = search_grid(3, {'1,1':'1'})
        puzzle.change('borders', 'h,1,0', True)
        original = copy.deepcopy(puzzle.data)
        puzzle.set_hook_analysis(search, 0.25)
        expected = {'h,1,1': True, 'h,2,1': True, 'v,1,1': True, 'v,1,2': True}
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], expected)
        puzzle.preview_hooks(-1)
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], expected)
        puzzle.undo()
        self.assertEqual(puzzle.data, original)
        puzzle.redo()
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], expected)
        puzzle.change('entries', '0,0', '2')
        self.assertNotIn('analysis', puzzle.data)
        self.assertEqual(puzzle.data['borders'], original['borders'])
        puzzle.undo()
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], expected)

    def test_all_expansion_orientations(self):
        inner = (1, 1, 1)
        for top, left in ((0,0), (0,1), (1,0), (1,1)):
            cells = hook_cells(inner, (top, left, 2))
            self.assertEqual(len(cells), 3)
            self.assertEqual(len(set(cells)), 3)
            self.assertNotIn((1,1), cells)

    def test_exhaustive_unconstrained_small_grids(self):
        for n in range(1, 5):
            for r in range(n):
                for c in range(n):
                    _, search = search_grid(n, {f'{r},{c}': '1'})
                    self.assertEqual(search.outcome, 'complete')
                    self.assertEqual(len(search.candidates), math.comb(n-1, r)*math.comb(n-1, c))
                    self.assertEqual(len({tuple(sorted(candidate)) for candidate in search.candidates}), len(search.candidates))
                    for candidate in search.candidates:
                        groups = regions(candidate, n)
                        self.assertEqual(sorted(map(len, groups)), list(range(1, 2*n, 2)))
                        self.assertIn({(r,c)}, groups)

    def test_distinct_digits_rejected_but_repeated_allowed(self):
        _, allowed = search_grid(2, {'0,0': '1', '0,1': '2', '1,0': '2'})
        self.assertEqual(len(allowed.candidates), 1)
        _, rejected = search_grid(2, {'0,0': '1', '0,1': '2', '1,0': '3'})
        self.assertEqual(rejected.outcome, 'complete')
        self.assertEqual(rejected.candidates, [])

    def test_only_interior_numbers_restrict_hooks(self):
        _, search = search_grid(2, {'0,0': '1', '-1,0': '1', '0,2': '9', '0,1': 'F', '1,0': '2'})
        self.assertEqual(len(search.candidates), 1)

    def test_digit_cannot_exceed_hook_cell_count(self):
        # Five cells can contain 5 when separated from the singleton.
        _, allowed = search_grid(3, {'0,0': '1', '2,2': '5'})
        self.assertEqual(len(allowed.candidates), 1)
        _, rejected = search_grid(2, {'0,0': '1', '0,1': '4'})
        self.assertEqual(rejected.outcome, 'complete')
        self.assertEqual(rejected.candidates, [])
        # A 4 may still occur on the five-cell size-3 hook.
        _, larger = search_grid(3, {'0,0': '1', '2,2': '4'})
        self.assertEqual(len(larger.candidates), 1)
        _, too_large = search_grid(3, {'0,0': '1', '2,2': '6'})
        self.assertEqual(too_large.candidates, [])

    def test_three_cell_hook_only_allows_two(self):
        for digit in ('0', '3', '4', '5'):
            _, search = search_grid(2, {'0,0':'1', '1,1':digit})
            self.assertEqual(search.candidates, [], digit)
        _, search = search_grid(2, {'0,0':'1', '1,1':'2'})
        self.assertEqual(len(search.candidates), 1)

    def test_five_cell_hook_touching_singleton(self):
        for digit in ('3', '4'):
            _, search = search_grid(3, {'1,1':'1', '0,0':digit})
            self.assertTrue(search.candidates, digit)
            for candidate in search.candidates:
                hook = next(group for group in regions(candidate, 3) if (0,0) in group)
                self.assertEqual(len(hook), 5)
                self.assertTrue(any(abs(r-1)+abs(c-1) == 1 for r,c in hook))
        for digit in ('2', '5'):
            _, search = search_grid(3, {'1,1':'1', '0,0':digit})
            for candidate in search.candidates:
                hook = next(group for group in regions(candidate, 3) if (0,0) in group)
                self.assertNotEqual(len(hook), 5)
            if digit == '5':
                self.assertEqual(search.candidates, [])

    def test_five_allowed_when_separated_or_touching_one_side(self):
        observed_contacts = set()
        for anchor_row in range(3):
            for anchor_col in range(3):
                for row in range(3):
                    for col in range(3):
                        if (row,col) == (anchor_row,anchor_col):
                            continue
                        _, search = search_grid(3, {f'{anchor_row},{anchor_col}':'1', f'{row},{col}':'5'})
                        for candidate in search.candidates:
                            hook = next(group for group in regions(candidate, 3) if (row,col) in group)
                            self.assertEqual(len(hook), 5)
                            contacts = sum(abs(r-anchor_row)+abs(c-anchor_col) == 1 for r,c in hook)
                            self.assertLessEqual(contacts, 1)
                            observed_contacts.add(contacts)
        self.assertEqual(observed_contacts, {0, 1})
        _, separated = search_grid(3, {'0,0':'1', '2,2':'5'})
        self.assertEqual(len(separated.candidates), 1)

    def test_small_hook_rules_leave_blank_hooks_and_diagonal_contacts(self):
        cells = hook_cells((0,0,2), (0,0,3))
        self.assertTrue(small_hook_digits_allowed(cells, set(), (1,1)))
        # (1,1) touches the outer L along an edge, whereas (0,0) does not.
        self.assertFalse(small_hook_digits_allowed(cells, {5}, (1,1)))
        self.assertTrue(small_hook_digits_allowed(cells, {5}, (0,1)))
        self.assertFalse(small_hook_digits_allowed(cells, {2}, (0,1)))
        self.assertTrue(small_hook_digits_allowed(cells, {5}, (0,0)))

    def test_each_candidate_matches_numeric_clues(self):
        entries = {'1,1': '1', '0,0': '2', '0,1': '3', '2,2': '2'}
        _, search = search_grid(3, entries)
        for candidate in search.candidates:
            for group in regions(candidate, 3):
                self.assertLessEqual(len({entries[f'{r},{c}'] for r,c in group if f'{r},{c}' in entries}), 1)
        self.assertLess(len(search.candidates), 4)

    def test_anchor_validation(self):
        for rows, cols, entries in ((2,3,{'0,0':'1'}), (2,2,{}), (2,2,{'0,0':'1','1,1':'1'})):
            puzzle = Puzzle('Invalid', rows, cols)
            puzzle.data['entries'] = entries
            with self.assertRaises(ValueError):
                HookSearch(puzzle.data)

    def test_cancellation_and_limits_are_incomplete(self):
        _, limited = search_grid(4, {'1,1':'1'}, node_limit=2)
        self.assertEqual(limited.outcome, 'limit')
        _, limited = search_grid(4, {'1,1':'1'}, candidate_limit=1)
        self.assertEqual(limited.outcome, 'limit')
        puzzle = Puzzle('Cancelled', 4, 4)
        puzzle.data['entries'] = {'1,1':'1'}
        search = HookSearch(puzzle.data)
        steps = search.run()
        next(steps)
        search.cancelled = True
        list(steps)
        self.assertEqual(search.outcome, 'cancelled')

    def test_history_persistence_invalidation_and_commit(self):
        puzzle, search = search_grid(3, {'1,1':'1'})
        original = copy.deepcopy(puzzle.data)
        puzzle.set_hook_analysis(search, 0.25)
        analyzed = copy.deepcopy(puzzle.data)
        puzzle.undo()
        self.assertEqual(puzzle.data, original)
        puzzle.redo()
        self.assertEqual(puzzle.data, analyzed)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'working.json'
            write(path, puzzle.data)
            self.assertEqual(read(path), analyzed)
            snapshot = Path(folder) / 'snapshot.json'
            save_snapshot(snapshot, puzzle, None)
            puzzle.change('entries', '0,0', '2')
            self.assertNotIn('analysis', puzzle.data)
            load_snapshot(snapshot, puzzle)
            self.assertEqual(puzzle.data, analyzed)
        puzzle.use_hook_preview()
        self.assertEqual(puzzle.data['borders'], search.candidates[0])
        self.assertEqual(puzzle.data['analysis']['preview'], -1)
        puzzle.undo()
        self.assertEqual(puzzle.data['borders'], {})
        self.assertEqual(puzzle.data['analysis']['preview'], 0)


if __name__ == '__main__':
    unittest.main()
