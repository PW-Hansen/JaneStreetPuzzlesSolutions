import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from puzzle_gui import (GridCanvas, PuzzleApp, format_candidates,
                        read_state, valid_combinations, write_state,
                        can_connect_region, check_grid_connectivity, connectivity_candidates,
                        grow_forced_regions, region_colors, canonical_shape, filter_containment,
                        fraction_parts, evaluate, math_runs, draw_math, inline_math, candidate_domain,
                        analyze_clues, solve_rational_clue)


class VariableSearchTests(unittest.TestCase):
    def test_analysis_ignores_bounds_for_all_derived_values(self):
        result, _ = analyze_clues(['8-b'], {'b': (1,2)}, 17)
        self.assertEqual({assignment['b'] for assignment in result}, set(range(-9,8)))
        result, _ = analyze_clues(['2*c'], {'c': (1,1)}, 6, {'c': (False,10)})
        from fractions import Fraction
        self.assertEqual({assignment['c'] for assignment in result},
                         {Fraction(n,2) for n in range(1,7)})
        brute = [value for value in valid_combinations(['8-b'], {'b':(1,2)}, 17) if value]
        self.assertEqual(brute, [{'b':1}, {'b':2}])

    def test_gui_example_bounds_do_not_filter_analytical_pairs(self):
        clues = ['8-b', '(b-1)^2', '(11-b)', 'b^2', '6*c-4*b', 'b^2-b/c']
        result, steps = analyze_clues(clues,
            {'a':(0,1), 'b':(-10,10), 'c':(1,17)}, 17,
            {'a':(True,10), 'b':(True,8), 'c':(False,6)})
        self.assertIn('102 partial assignments', steps[4])
        self.assertEqual(len(result),18)
        self.assertTrue(all(assignment['a'] is None for assignment in result))
    def test_analytical_example_keeps_correlated_partial_assignments(self):
        clues = ['6*c-4*b', '8-b', 'b^2', 'b^2-b/c', '(b-1)^2', '11-b']
        bounds = {name: (-20,20) for name in ('a','b','c')}
        result, steps = analyze_clues(clues, bounds, 17,
                                     {name:(False,10) for name in bounds})
        self.assertEqual([step.split(':')[0] for step in steps],
                         ['8-b','b^2','(b-1)^2','11-b','6*c-4*b','b^2-b/c'])
        self.assertIn('102 partial assignments', steps[4])
        self.assertEqual(len(result), 18)
        self.assertTrue(all(assignment['a'] is None and assignment['b'] != 1 for assignment in result))
        for assignment in result:
            known = {name:value for name,value in assignment.items() if value is not None}
            for clue in clues:
                value = evaluate(clue, known)
                self.assertEqual(value.denominator, 1)
                self.assertTrue(1 <= value <= 17)

    def test_analytical_unconstrained_variables_and_poles(self):
        result, _ = analyze_clues(['2*b'], {'a':(1,6),'b':(0,3)}, 6, {'b':(False,1)})
        self.assertEqual(len(result),6)  # derived fractions need no denominator enumeration
        self.assertTrue(all(assignment['a'] is None for assignment in result))
        result, _ = analyze_clues(['b/b'], {'b':(0,2)}, 6)
        self.assertEqual([assignment['b'] for assignment in result], [1,2])
        self.assertEqual(analyze_clues([], {'a':(1,6)}, 6)[0], [{'a':None}])
    def test_fractional_variable_candidates_are_exact_and_bounded(self):
        from fractions import Fraction
        self.assertEqual(candidate_domain('1/3', '1', False, 3),
                         [Fraction(1,3), Fraction(1,2), Fraction(2,3), Fraction(1)])
        self.assertEqual(candidate_domain('1/3', '1', True), [1])
        bounds = {'a': ('1/3', 1)}
        options = {'a': (False, 3)}
        surviving = [value for value in valid_combinations(['2*a'], bounds, 6, options) if value is not None]
        self.assertEqual(surviving, [{'a':Fraction(1,2)}, {'a':Fraction(1)}])
        count, values, _ = connectivity_candidates([['2*a', ''], ['', '']], bounds, options)
        self.assertEqual(count, 2)
        self.assertEqual(format_candidates(values['a']), '1/2, 1')
        with self.assertRaises(ValueError):
            candidate_domain(0, 1, False, 0)
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
        self.assertEqual(math_runs(inline_math('(b-1)^2')),
                         [('power', ([('text', '(b − 1)')], [('text', '2')]))])
        self.assertEqual(math_runs(inline_math('b-1^2')),
                         [('text', 'b − '), ('power', ([('text', '1')], [('text', '2')]))])
        self.assertEqual(evaluate('(b-1)^2', {'b':4}), 9)
    def test_cube_root_evaluation_and_display(self):
        self.assertEqual(evaluate('cbrt(43-a*c)/a', {'a':1, 'c':16}), 3)
        self.assertEqual(evaluate('cbrt(-8)', {}), -2)
        self.assertEqual(evaluate('cbrt(1/8)', {}), evaluate('1/2', {}))
        self.assertEqual(evaluate('cbrt(0)', {}), 0)
        self.assertNotEqual(evaluate('cbrt(2)', {}).denominator, 1)
        self.assertEqual(fraction_parts('cbrt(43-a*c)/a'), ('∛(43 − a · c)', 'a'))
        self.assertEqual(math_runs('∛(43 − a · c)')[0][0], 'cube_root')
        self.assertEqual([assignment for assignment in valid_combinations(
            ['cbrt(a)'], {'a':(1,8)}, 6) if assignment is not None], [{'a':1}, {'a':8}])
    def test_logarithm_with_variable_or_numeric_base(self):
        self.assertEqual(evaluate('log_c(a)', {'c':2, 'a':8}), 3)
        self.assertEqual(evaluate('log_2(16)+1', {}), 5)
        self.assertEqual(evaluate('log_c(a)', {'c':'1/2', 'a':4}), -2)
        self.assertEqual(math_runs(inline_math('log_c(a)')),
                         [('log', ([('text','c')], [('text','a')]))])
        for values in ({'c':1,'a':8}, {'c':0,'a':8}, {'c':2,'a':0}, {'c':-2,'a':8}):
            with self.assertRaises(ValueError):
                evaluate('log_c(a)', values)
        self.assertEqual([assignment for assignment in valid_combinations(
            ['log_c(a)'], {'c':(2,2), 'a':(2,8)}, 6) if assignment is not None],
            [{'c':2,'a':2}, {'c':2,'a':4}, {'c':2,'a':8}])
    def test_fraction_inside_subtraction_is_stacked(self):
        runs = math_runs(inline_math('a^b-12/a'))
        self.assertEqual(runs, [('power', ([('text','a')], [('text','b')])), ('text', ' − '),
                                ('fraction', ([('text', '12')], [('text', 'a')]))])
        texts, lines = [], []
        font = SimpleNamespace(measure=lambda value:len(value)*8,
                               cget=lambda key:12, metrics=lambda key:18)
        canvas = SimpleNamespace(create_text=lambda *args, **kw:texts.append((args, kw['text'])),
                                 create_line=lambda *args, **kw:lines.append(args))
        draw_math(canvas, 50, 30, inline_math('a^b-12/a'), font)
        self.assertLess(texts[3][0][1], texts[4][0][1])
        self.assertEqual(len(lines), 1)

    def test_radical_draws_bar_and_removes_outer_parentheses(self):
        text, lines = [], []
        font = SimpleNamespace(measure=lambda value: len(value)*8,
                               cget=lambda key:12, metrics=lambda key:18)
        canvas = SimpleNamespace(create_text=lambda *args, **kwargs:text.append(kwargs['text']),
                                 create_line=lambda *args, **kwargs:lines.append(args))
        draw_math(canvas, 50, 30, '√(3 + 2c)', font)
        self.assertEqual(text, ['3 + 2c'])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][-1], lines[0][-3])
        self.assertEqual(math_runs('√(a + √(b))'),
                         [('root', [('text','a + '), ('root',[('text','b')])])])
    def test_square_roots(self):
        self.assertEqual(evaluate('(b+9)/sqrt(c-a)', {'a':1, 'b':3, 'c':5}), 6)
        self.assertEqual(evaluate('sqrt(1/4)', {}), evaluate('1/2', {}))
        self.assertEqual(evaluate('sqrt(2)*sqrt(2)', {}), 2)
        self.assertNotEqual(evaluate('sqrt(2)', {}).denominator, 1)
        self.assertEqual(fraction_parts('(b+9)/sqrt(c-a)'), ('b + 9', '√(c − a)'))
        with self.assertRaises(ValueError):
            evaluate('sqrt(-1)', {})
        with self.assertRaises(ZeroDivisionError):
            evaluate('1/sqrt(0)', {})
        self.assertEqual(list(valid_combinations(['sqrt(a)'], {'a':(1,4)}, 6)),
                         [{'a':1}, None, None, {'a':4}])
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
        app.detail, app.status = variable(''), variable('')
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
        grid = [['', '6', '', '3', ''], ['', '', '5', '', ''],
                ['4', '', '', '', '5'], ['', '1', '', '6', ''],
                ['4', '', '', '', '2']]
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
        grid = [['', '6', '', '3', ''], ['', '', '5', '', ''],
                ['4', '', '', '', '5'], ['', '1', '', '6', ''],
                ['4', '', '', '', '2']]
        ordinary, _ = grow_forced_regions(grid, {}, use_containment=False)
        labels, added = grow_forced_regions(grid, {})
        self.assertNotIn(9, ordinary)
        self.assertEqual(labels[9], 5)  # r2c5, forced by containment
        self.assertEqual(labels[13], 6)  # subsequent connected-region growth
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
            filter_containment({4: [frozenset({0, 1, 3, 4})],
                                3: [frozenset({6, 7, 8})]}, 3)

    def test_ambiguous_growth_stays_blank(self):
        labels, added = grow_forced_regions([['', '', ''], ['', '2', ''], ['', '', '']], {})
        self.assertEqual(labels, {4: 2})
        self.assertEqual(added, 0)

    def test_color_conflicts_are_resolved(self):
        labels = {0: 4, 1: 13, 2: 22, 3: 6}
        colors = region_colors(2, labels)
        for first, second in ((4, 13), (4, 22), (13, 6), (22, 6)):
            self.assertNotEqual(colors[first], colors[second])
        self.assertEqual(colors[4], '#efa5a5')
        self.assertEqual(colors[6], '#a9d8af')
    def test_connectivity_filters_lists_without_losing_valid_partner(self):
        # a=1 is invalid with b=1, but remains valid with b=2 or b=3.
        count, values, first = connectivity_candidates(
            [['a', 'b', ''], ['', '', ''], ['', '', '']],
            {'a': (1, 3), 'b': (1, 3)})
        self.assertEqual(count, 8)
        self.assertEqual(values, {'a': {1, 2, 3}, 'b': {1, 2, 3}})
        self.assertEqual(first, {'a': 1, 'b': 2})

    def test_connectivity_removes_values_with_no_surviving_combination(self):
        count, values, _ = connectivity_candidates(
            [['a', '', 'a'], ['', '', ''], ['', '', '']], {'a': (1, 3)})
        self.assertEqual(count, 1)
        self.assertEqual(values, {'a': {3}})
        count, values, _ = connectivity_candidates([['a', 'a'], ['', '']], {'a': (1, 1)})
        self.assertEqual(count, 0)
        self.assertEqual(values, {'a': set()})
    def test_connectivity_counts_reject_before_search(self):
        with patch('puzzle_gui.can_connect_region') as search:
            passed, message = check_grid_connectivity([['1', '1'], ['', '']], {})
            self.assertFalse(passed)
            self.assertIn('at most 1', message)
            search.assert_not_called()

    def test_connectivity_blank_bridge_and_obstacle(self):
        self.assertTrue(check_grid_connectivity(
            [['3', '', '3'], ['', '', ''], ['', '', '']], {})[0])
        self.assertFalse(check_grid_connectivity(
            [['3', '1', '3'], ['', '', ''], ['', '', '']], {})[0])

    def test_connectivity_checks_total_region_size(self):
        self.assertFalse(can_connect_region(3, {0: 3, 2: 3, 6: 3}, 3, [0, 2, 6]))
        self.assertTrue(can_connect_region(3, {1: 4, 3: 4, 5: 4}, 4, [1, 3, 5]))

    def test_connectivity_candidate_evaluation_and_boundaries(self):
        grid = [['a', 'a'], ['', '']]
        self.assertTrue(check_grid_connectivity(grid, {'a': 2})[0])
        for candidate in (0, -1, '1/2', 3):
            self.assertFalse(check_grid_connectivity(grid, {'a': candidate})[0])

    def test_coupled_variables_reject_fraction_zero_and_negative(self):
        solutions = [value for value in valid_combinations(
            ["b/a", "a-1", "b-a", "a^3-b"], {"a": (1, 3), "b": (1, 6)}, 6)
            if value is not None]
        self.assertEqual(solutions, [{"a": 2, "b": 4}, {"a": 2, "b": 6}])

    def test_region_limit_is_inclusive_and_applies_to_results(self):
        self.assertEqual(list(valid_combinations(["a^2"], {"a": (2, 3)}, 6)),
                         [{"a": 2}, None])
        self.assertEqual(list(valid_combinations(["a-10"], {"a": (16, 17)}, 6)),
                         [{"a": 16}, None])

    def test_zero_denominator_does_not_stop_search(self):
        self.assertEqual(list(valid_combinations(["1/a"], {"a": (-1, 1)}, 6)),
                         [None, None, {"a": 1}])

    def test_constant_grids_and_unused_variables(self):
        self.assertEqual(list(valid_combinations(["2"], {}, 6)), [{}])
        self.assertEqual(list(valid_combinations(["1/2"], {}, 6)), [None])
        self.assertEqual(list(valid_combinations([], {"a": (-1, 1)}, 6)),
                         [{"a": -1}, {"a": 0}, {"a": 1}])

    def test_candidate_range_format(self):
        self.assertEqual(format_candidates({1, 2, 3, 5, 7, 8}), "1–3, 5, 7–8")
        self.assertEqual(format_candidates(set()), "None")

    def test_bounds_are_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grid.json"
            state = {"size": 1, "expressions": [["a"]], "variables": {"a": "2"},
                     "bounds": {"a": {"min": "-2", "max": "12"}}}
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

    def test_batched_search_finishes_and_stale_job_is_ignored(self):
        app = PuzzleApp.__new__(PuzzleApp)
        messages, displayed = [], []
        app.compute_button = SimpleNamespace(configure=lambda **kw: None)
        app.search_message = SimpleNamespace(set=messages.append)
        app.valid_values = {"a": SimpleNamespace(set=displayed.append)}
        app.root = SimpleNamespace(after=lambda delay, callback: callback())
        job = {"iterator": valid_combinations(["a-1"], {"a": (1, 150)}, 6),
               "total": 150, "checked": 0, "count": 0,
               "values": {"a": set()}, "first": None}
        app.search_job = job
        app.search_step(job)
        self.assertEqual(job["count"], 6)
        self.assertEqual(displayed, ["2–7"])
        self.assertIsNone(app.search_job)
        app.search_step(job)
        self.assertEqual(displayed, ["2–7"])


if __name__ == "__main__":
    unittest.main()
