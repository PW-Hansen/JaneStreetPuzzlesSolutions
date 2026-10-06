import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from puzzle_gui import GridCanvas, PuzzleApp, format_candidates, read_state, write_state, can_connect_region, check_grid_connectivity, grow_forced_regions, region_colors, canonical_shape, filter_containment, fraction_parts, evaluate, math_runs, draw_math, inline_math, analyze_clues, solve_rational_clue, inferred_integer_variables, minimum_region_size, find_region_overlays, shape_orientations

class VariableSearchTests(unittest.TestCase):
    def test_larger_region_keeps_preferred_color(self):
        colors = region_colors(2, {0:16, 1:7})
        self.assertEqual(colors[16], '#e7afd4')
        self.assertNotEqual(colors[7], colors[16])
    def test_overlay_uses_highest_clue_and_preserves_originals(self):
        grid = [['2','',''],['','3',''],['','','']]
        highest, labels, states, tested = find_region_overlays(grid,{})
        self.assertEqual(highest,3)
        self.assertEqual(tested,9)
        self.assertEqual(len(states),8)  # source 2 is an obstacle
        self.assertTrue(all(0 not in state['cells'] for state in states))
        self.assertEqual(grid[0][0],'2')
        self.assertEqual(labels,{0:2,4:3})

    def test_overlay_rotations_and_reflections_are_unique(self):
        orientations = shape_orientations([0,5,10,11],5)
        self.assertEqual(len(orientations),8)
        self.assertEqual(len({shape for _,_,shape in orientations}),8)
        self.assertEqual(orientations[0][2],((0,0),(1,0),(2,0),(2,1)))

    def test_minimum_connection_matches_exhaustive_small_graphs(self):
        from itertools import combinations
        cases = [({0:3,8:3},[0,8]), ({0:3,2:3},[0,2]),
                 ({0:3,1:1,2:3},[0,2]), ({1:4,3:4,5:4},[1,3,5])]
        for labels,terminals in cases:
            number=labels[terminals[0]]
            allowed=[cell for cell in range(9) if cell not in labels or labels[cell]==number]
            expected=None
            for count in range(len(terminals),number+1):
                for cells in combinations(allowed,count):
                    cells=set(cells)
                    if not set(terminals)<=cells: continue
                    reached={terminals[0]}
                    while True:
                        extended=reached|{cell for cell in cells if any(
                            abs(cell//3-other//3)+abs(cell%3-other%3)==1 for other in reached)}
                        if extended==reached: break
                        reached=extended
                    if reached==cells:
                        expected=count
                        break
                if expected is not None: break
            self.assertEqual(minimum_region_size(3,labels,number,terminals),expected)
    def test_single_assignment_fills_known_variables_only(self):
        from fractions import Fraction
        def variable(initial):
            data = [initial]
            return SimpleNamespace(get=lambda:data[0], set=lambda value:data.__setitem__(0,value))
        app = PuzzleApp.__new__(PuzzleApp)
        app.variables = {'a':variable('9'), 'b':variable('9'), 'c':variable('9')}
        app.clear_regions = lambda:None
        app.refresh = lambda:None
        app.connectivity_message = variable('')
        app.analytical_assignments = [{'a':Fraction(1,4), 'b':Fraction(-3), 'c':None}]
        self.assertTrue(app.apply_single_assignment())
        self.assertEqual({name:value.get() for name,value in app.variables.items()},
                         {'a':'1/4', 'b':'-3', 'c':'9'})
        app.analytical_assignments *= 2
        self.assertFalse(app.apply_single_assignment())
    def test_integer_requirement_inferred_from_addition_and_subtraction(self):
        from fractions import Fraction
        self.assertEqual(inferred_integer_variables('8-b', {}), {'b'})
        self.assertEqual(inferred_integer_variables('b+c', {'b':2}), {'c'})
        self.assertEqual(inferred_integer_variables('b+c', {'b':Fraction(1,2)}), set())
        assignments, _ = analyze_clues(['b+1/2'], ['b'], 3)
        self.assertEqual({item['b'] for item in assignments}, {Fraction(1,2),Fraction(3,2),Fraction(5,2)})
        assignments, _ = analyze_clues(['2*c'], ['c'], 3)
        self.assertEqual({item['c'] for item in assignments}, {Fraction(1,2),Fraction(1),Fraction(3,2)})

    def test_unsupported_analysis_does_not_guess_values(self):
        with self.assertRaisesRegex(ValueError, 'More information'):
            analyze_clues(['a+b'], ['a','b'], 6)
        with self.assertRaisesRegex(ValueError, 'More information'):
            analyze_clues(['log_a(2)'], ['a'], 6)

    def test_square_root_clue_is_solved_without_enumeration(self):
        from fractions import Fraction
        assignments, _ = analyze_clues(['sqrt(a+2)/a'], ['a'], 17)
        self.assertIn({'a':Fraction(1,4)}, assignments)
        self.assertTrue(all(item['a'] > 0 for item in assignments))
        for assignment in assignments:
            value = evaluate('sqrt(a+2)/a', assignment)
            self.assertTrue(1 <= value <= 17 and value.denominator == 1)

    def test_full_puzzle_converges_to_one_assignment(self):
        from fractions import Fraction
        clues = ['6*c-4*b','8-b','(a^b-4)/(6*c+1)','(b+c)/(c-1)',
                 'b^2-b/c','sqrt(30+a)/c','(a+b)/(c-3*a)',
                 '(b-3*a)/(a-c)','8*a-2*b','b/(a-c)','(b+9)/sqrt(c-a)',
                 '18/(a*c+1)','c^b','(3+b^2)/sqrt(3+2*c)',
                 'b/(a^2-c^2)','sqrt(a+2)/a','a^b-12/a','2*c+c/a',
                 '4*a-5*b','c+2*a','b/(9*a-5*c)','(b^3+2*c)/(b+2*c)',
                 'b/(a-1)','(c-b)/(2*a)','b/(a-c)','(b+c)/(a-c)',
                 'log_c(a)','(c^2-b)/a','(b-1)^2','cbrt(43-a*c)/a',
                 '(b-a)/(a-c)','(11-b)','(b-2*a)/(a-c)','(c+3)/a',
                 '8*c-b/c','b^2','(2^b+1)/(a*c)']
        result, steps = analyze_clues(clues, ['a','b','c'], 17)
        self.assertEqual(result, [{'a':Fraction(1,4),'b':Fraction(-3),'c':Fraction(1,2)}])
        self.assertEqual(len(steps), len(clues))


    def test_gui_example_bounds_do_not_filter_analytical_pairs(self):
        clues = ['8-b', '(b-1)^2', '(11-b)', 'b^2', '6*c-4*b', 'b^2-b/c']
        result, steps = analyze_clues(clues, {'a': (0, 1), 'b': (-10, 10), 'c': (1, 17)}, 17)
        self.assertIn('102 partial assignments', steps[4])
        self.assertEqual(len(result), 18)
        self.assertTrue(all((assignment['a'] is None for assignment in result)))

    def test_analytical_example_keeps_correlated_partial_assignments(self):
        clues = ['6*c-4*b', '8-b', 'b^2', 'b^2-b/c', '(b-1)^2', '11-b']
        bounds = {name: (-20, 20) for name in ('a', 'b', 'c')}
        result, steps = analyze_clues(clues, bounds, 17)
        self.assertEqual([step.split(':')[0] for step in steps], ['8-b', 'b^2', '(b-1)^2', '11-b', '6*c-4*b', 'b^2-b/c'])
        self.assertIn('102 partial assignments', steps[4])
        self.assertEqual(len(result), 18)
        self.assertTrue(all((assignment['a'] is None and assignment['b'] != 1 for assignment in result)))
        for assignment in result:
            known = {name: value for name, value in assignment.items() if value is not None}
            for clue in clues:
                value = evaluate(clue, known)
                self.assertEqual(value.denominator, 1)
                self.assertTrue(1 <= value <= 17)

    def test_disabled_equations_are_preserved_but_excluded(self):
        app = PuzzleApp.__new__(PuzzleApp)
        app.SIZE = 2
        app.expressions = [['a', 'b'], ['3', '4']]
        app.disabled_cells = {1, 2}
        self.assertEqual(app.active_expressions(), [['a', ''], ['', '4']])
        self.assertEqual(app.expressions, [['a', 'b'], ['3', '4']])
        app.disabled_cells.clear()
        self.assertEqual(app.active_expressions(), app.expressions)

    def test_power_preserves_compound_base_parentheses(self):
        self.assertEqual(math_runs(inline_math('(b-1)^2')), [('power', ([('text', '(b − 1)')], [('text', '2')]))])
        self.assertEqual(math_runs(inline_math('b-1^2')), [('text', 'b − '), ('power', ([('text', '1')], [('text', '2')]))])
        self.assertEqual(evaluate('(b-1)^2', {'b': 4}), 9)

    def test_cube_root_evaluation_and_display(self):
        self.assertEqual(evaluate('cbrt(43-a*c)/a', {'a': 1, 'c': 16}), 3)
        self.assertEqual(evaluate('cbrt(-8)', {}), -2)
        self.assertEqual(evaluate('cbrt(1/8)', {}), evaluate('1/2', {}))
        self.assertEqual(evaluate('cbrt(0)', {}), 0)
        self.assertNotEqual(evaluate('cbrt(2)', {}).denominator, 1)
        self.assertEqual(fraction_parts('cbrt(43-a*c)/a'), ('∛(43 − a · c)', 'a'))
        self.assertEqual(math_runs('∛(43 − a · c)')[0][0], 'cube_root')

    def test_logarithm_with_variable_or_numeric_base(self):
        self.assertEqual(evaluate('log_c(a)', {'c': 2, 'a': 8}), 3)
        self.assertEqual(evaluate('log_2(16)+1', {}), 5)
        self.assertEqual(evaluate('log_c(a)', {'c': '1/2', 'a': 4}), -2)
        self.assertEqual(math_runs(inline_math('log_c(a)')), [('log', ([('text', 'c')], [('text', 'a')]))])
        for values in ({'c': 1, 'a': 8}, {'c': 0, 'a': 8}, {'c': 2, 'a': 0}, {'c': -2, 'a': 8}):
            with self.assertRaises(ValueError):
                evaluate('log_c(a)', values)

    def test_fraction_inside_subtraction_is_stacked(self):
        runs = math_runs(inline_math('a^b-12/a'))
        self.assertEqual(runs, [('power', ([('text', 'a')], [('text', 'b')])), ('text', ' − '), ('fraction', ([('text', '12')], [('text', 'a')]))])
        texts, lines = ([], [])
        font = SimpleNamespace(measure=lambda value: len(value) * 8, cget=lambda key: 12, metrics=lambda key: 18)
        canvas = SimpleNamespace(create_text=lambda *args, **kw: texts.append((args, kw['text'])), create_line=lambda *args, **kw: lines.append(args))
        draw_math(canvas, 50, 30, inline_math('a^b-12/a'), font)
        self.assertLess(texts[3][0][1], texts[4][0][1])
        self.assertEqual(len(lines), 1)

    def test_radical_draws_bar_and_removes_outer_parentheses(self):
        text, lines = ([], [])
        font = SimpleNamespace(measure=lambda value: len(value) * 8, cget=lambda key: 12, metrics=lambda key: 18)
        canvas = SimpleNamespace(create_text=lambda *args, **kwargs: text.append(kwargs['text']), create_line=lambda *args, **kwargs: lines.append(args))
        draw_math(canvas, 50, 30, '√(3 + 2c)', font)
        self.assertEqual(text, ['3 + 2c'])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][-1], lines[0][-3])
        self.assertEqual(math_runs('√(a + √(b))'), [('root', [('text', 'a + '), ('root', [('text', 'b')])])])

    def test_square_roots(self):
        self.assertEqual(evaluate('(b+9)/sqrt(c-a)', {'a': 1, 'b': 3, 'c': 5}), 6)
        self.assertEqual(evaluate('sqrt(1/4)', {}), evaluate('1/2', {}))
        self.assertEqual(evaluate('sqrt(2)*sqrt(2)', {}), 2)
        self.assertNotEqual(evaluate('sqrt(2)', {}).denominator, 1)
        self.assertEqual(fraction_parts('(b+9)/sqrt(c-a)'), ('b + 9', '√(c − a)'))
        with self.assertRaises(ValueError):
            evaluate('sqrt(-1)', {})
        with self.assertRaises(ZeroDivisionError):
            evaluate('1/sqrt(0)', {})

    def test_compound_fraction_notation_preserves_denominator(self):
        self.assertEqual(fraction_parts('(x-y)/(y-c)'), ('x − y', 'y − c'))
        self.assertEqual(fraction_parts('(a^b-b)/(6*c+1)'), ('〖a¦b〗 − b', '6c + 1'))
        self.assertEqual(fraction_parts('(a^2-b)/(6*c+1)'), ('〖a¦2〗 − b', '6c + 1'))
        self.assertEqual(fraction_parts('b/a'), ('b', 'a'))
        self.assertIsNone(fraction_parts('a/b + 1'))
        self.assertIsNone(fraction_parts('a//b'))

    def test_display_toggle_preserves_colors_and_number_only_cells(self):
        app = PuzzleApp.__new__(PuzzleApp)

        def variable(initial):
            data = [initial]
            return SimpleNamespace(get=lambda: data[0], set=lambda value: data.__setitem__(0, value))
        app.SIZE = 2
        app.expressions = [['a', ''], ['a/2', 'unknown']]
        app.variables = {'a': variable('2')}
        app.selected = (0, 0)
        app.show_values = variable(False)
        app.detail, app.status = (variable(''), variable(''))
        app.region_labels = {0: 2, 1: 2}
        app.region_palette = {2: '#123456'}
        app.board = SimpleNamespace(draw=lambda: None)
        app.display_button = SimpleNamespace(configure=lambda **kw: None)
        app.save_state = lambda: None
        app.refresh()
        before = app.board.cells[:]
        self.assertEqual([cell[2] for cell in before], ['a', '2', 'a/2', 'unknown'])
        app.toggle_display()
        self.assertEqual([cell[2] for cell in app.board.cells], ['2', '2', '1', 'unknown'])
        self.assertEqual([cell[3] for cell in before], [cell[3] for cell in app.board.cells])
        app.toggle_display()
        self.assertEqual(app.board.cells, before)

    def test_forced_regions_from_blocked_paths(self):
        grid = [['', '6', '', '3', ''], ['', '', '5', '', ''], ['4', '', '', '', '5'], ['', '1', '', '6', ''], ['4', '', '', '', '2']]
        labels, added = grow_forced_regions(grid, {}, use_containment=False)
        self.assertEqual(labels[15], 4)
        for cell in (6, 11, 12):
            self.assertEqual(labels[cell], 6)
        self.assertEqual(labels[8], 5)
        self.assertNotIn(13, labels)
        self.assertNotIn(17, labels)
        self.assertGreater(added, 0)
        self.assertEqual(grid[1][1], '')

    def test_containment_forces_screenshot_cell_and_restarts_growth(self):
        grid = [['', '6', '', '3', ''], ['', '', '5', '', ''], ['4', '', '', '', '5'], ['', '1', '', '6', ''], ['4', '', '', '', '2']]
        ordinary, _ = grow_forced_regions(grid, {}, use_containment=False)
        labels, added = grow_forced_regions(grid, {})
        self.assertNotIn(9, ordinary)
        self.assertEqual(labels[9], 5)
        self.assertEqual(labels[13], 6)
        self.assertEqual(labels[19], 5)
        self.assertEqual(added, 12)
        self.assertEqual(len(labels), 21)

    def test_shape_equivalence_allows_rotations_and_reflections(self):
        original = {0, 5, 10, 11}
        reflected = {1, 6, 10, 11}
        rotated = {0, 1, 2, 5}
        self.assertEqual(canonical_shape(original, 5), canonical_shape(reflected, 5))
        self.assertEqual(canonical_shape(original, 5), canonical_shape(rotated, 5))

    def test_containment_rejects_incompatible_shapes(self):
        with self.assertRaisesRegex(ValueError, 'shape containment'):
            filter_containment({4: [frozenset({0, 1, 3, 4})], 3: [frozenset({6, 7, 8})]}, 3)

    def test_ambiguous_growth_stays_blank(self):
        labels, added = grow_forced_regions([['', '', ''], ['', '2', ''], ['', '', '']], {})
        self.assertEqual(labels, {4: 2})
        self.assertEqual(added, 0)

    def test_color_conflicts_are_resolved(self):
        labels = {0: 4, 1: 13, 2: 22, 3: 6}
        colors = region_colors(2, labels)
        for first, second in ((4, 13), (4, 22), (13, 6), (22, 6)):
            self.assertNotEqual(colors[first], colors[second])
        self.assertEqual(colors[22], '#efa5a5')
        self.assertNotEqual(colors[4], colors[22])
        self.assertEqual(colors[6], '#a9d8af')

    def test_connectivity_counts_reject_before_search(self):
        with patch('puzzle_gui.can_connect_region') as search:
            passed, message = check_grid_connectivity([['1', '1'], ['', '']], {})
            self.assertFalse(passed)
            self.assertIn('at most 1', message)
            search.assert_not_called()

    def test_connectivity_blank_bridge_and_obstacle(self):
        self.assertTrue(check_grid_connectivity([['3', '', '3'], ['', '', ''], ['', '', '']], {})[0])
        self.assertFalse(check_grid_connectivity([['3', '1', '3'], ['', '', ''], ['', '', '']], {})[0])

    def test_connectivity_checks_total_region_size(self):
        self.assertFalse(can_connect_region(3, {0: 3, 2: 3, 6: 3}, 3, [0, 2, 6]))
        self.assertTrue(can_connect_region(3, {1: 4, 3: 4, 5: 4}, 4, [1, 3, 5]))

    def test_connectivity_candidate_evaluation_and_boundaries(self):
        grid = [['a', 'a'], ['', '']]
        self.assertTrue(check_grid_connectivity(grid, {'a': 2})[0])
        for candidate in (0, -1, '1/2', 3):
            self.assertFalse(check_grid_connectivity(grid, {'a': candidate})[0])

    def test_candidate_range_format(self):
        self.assertEqual(format_candidates({1, 2, 3, 5, 7, 8}), '1–3, 5, 7–8')
        self.assertEqual(format_candidates(set()), 'None')

    def test_bounds_are_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'grid.json'
            state = {'size': 1, 'expressions': [['a']], 'variables': {'a': '2'}, 'bounds': {'a': {'min': '-2', 'max': '12'}}}
            write_state(path, state)
            self.assertEqual(read_state(path), state)

    def test_grid_hit_testing_with_left_alignment(self):
        canvas = GridCanvas.__new__(GridCanvas)
        canvas.size = 5
        canvas.bounds = (4, 30, 250)
        selected = []
        canvas.select_cell = lambda x, y: selected.append((x, y))
        canvas.click(SimpleNamespace(x=253, y=279))
        canvas.click(SimpleNamespace(x=400, y=100))
        self.assertEqual(selected, [(4, 4)])
if __name__ == '__main__':
    unittest.main()
