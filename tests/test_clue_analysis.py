import copy
import threading
import unittest
from itertools import product

from functions.clue_analysis import ClueAnalysis, analyze_clue, area_lower_bound, incorporate_analysis, partial_region
from puzzle_gui import ARC_CYCLE, PuzzleEditor, allowed_arc_configurations, blank_grid, determine_regions, validate_state


def board(rows, columns):
    return {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}


def exhaustive_local_states(state, selected):
    """Full tiny-board enumeration, without partial-region pruning."""
    undecided = [(r, c) for r, row in enumerate(state["cells"])
                 for c, cell in enumerate(row) if not cell["green"] and cell["arc"] is None]
    expected = {}
    for orientations in product(ARC_CYCLE, repeat=len(undecided)):
        candidate = copy.deepcopy(state)
        for (r, c), orientation in zip(undecided, orientations):
            candidate["cells"][r][c]["arc"] = orientation
        region = determine_regions(candidate)[0][(*selected, 0)]
        score = region.determine_score(candidate)
        if score is None:
            continue
        if any(side == 0 and candidate["cells"][r][c]["number"] not in (None, score)
               and (r, c) != selected for r, c, side in region.fragments):
            continue
        reached = {(r, c) for r, c, side in region.fragments}
        signature = tuple((r, c, candidate["cells"][r][c]["arc"]) for r, c in sorted(reached))
        expected.setdefault(score, set()).add(signature)
    return expected


class ClueAnalysisTests(unittest.TestCase):
    def test_matches_exhaustive_tiny_boards(self):
        for green, fixed in ((False, None), (True, None), (False, "br")):
            state = board(2, 2)
            state["cells"][1][1]["green"] = green
            state["cells"][1][1]["arc"] = fixed
            expected = exhaustive_local_states(state, (0, 0))
            for clue in range(1, 21):
                state["cells"][0][0]["number"] = clue
                result = analyze_clue(state, (0, 0), accepted_limit=10000)
                self.assertFalse(result.limit_reached)
                self.assertEqual(set(result.accepted_states), expected.get(clue, set()),
                                 (green, fixed, clue))

    def test_other_clue_majority_constraint(self):
        state = board(2, 2)
        state["cells"][1][1]["number"] = 4
        expected = exhaustive_local_states(state, (0, 0))
        for target in (3, 4, 6, 8, 12, 16):
            state["cells"][0][0]["number"] = target
            self.assertEqual(set(analyze_clue(state, (0, 0), accepted_limit=10000).accepted_states),
                             expected.get(target, set()))

    def test_corner_three_wraparound_and_no_arc_candidates(self):
        state = board(4, 4)
        state["cells"][0][0]["number"] = 3
        original = copy.deepcopy(state)
        result = analyze_clue(state, (0, 0))
        self.assertEqual(len(result.accepted_states), 2)
        self.assertEqual(state, original)
        one = board(1, 1)
        one["cells"][0][0]["number"] = 4
        self.assertEqual(analyze_clue(one, (0, 0)).accepted_states, [((0, 0, None),)])

    def test_green_propagation_and_neighbor_minimum_area(self):
        state = board(3, 3)
        state["cells"][1][1]["green"] = True
        assigned = {(0, 1): None, (1, 1): None}
        fragments, frontier = partial_region(state, (0, 1), assigned)
        self.assertIn((1, 1, 0), fragments)
        self.assertEqual(len(frontier), 5)
        self.assertEqual(area_lower_bound(state, assigned, fragments, frontier), 4)

    def test_early_stop_and_cancellation(self):
        state = board(3, 3)
        state["cells"][1][1]["number"] = 12
        result = analyze_clue(state, (1, 1))
        self.assertEqual(len(result.accepted_states), 26)
        self.assertTrue(result.limit_reached)
        event = threading.Event()
        event.set()
        result = analyze_clue(state, (1, 1), stop_event=event)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.explored, 0)

    def test_requires_numbered_selection(self):
        with self.assertRaises(ValueError):
            analyze_clue(board(1, 1), (0, 0))

    def test_unique_state_is_applied_and_no_arc_is_confirmed(self):
        state = board(2, 2)
        state["cells"][0][0]["number"] = 3
        state["cells"][0][1]["arc"] = "br"
        state["cells"][1][0]["green"] = True
        result = analyze_clue(state, (0, 0))
        self.assertEqual(len(result.accepted_states), 1)
        changes = incorporate_analysis(state, result)
        self.assertTrue(changes["applied"])
        self.assertEqual(state["cells"][0][0]["arc"], "tr")
        self.assertEqual(allowed_arc_configurations(state, 0, 0), ("tr",))
        validate_state(state)
        one = board(1, 1)
        one["cells"][0][0]["number"] = 4
        incorporate_analysis(one, analyze_clue(one, (0, 0)))
        self.assertEqual(one["arc_domains"], [[[None]]])

    def test_optional_cells_are_not_restricted(self):
        state = board(2, 2)
        state["cells"][0][0]["number"] = 3
        result = analyze_clue(state, (0, 0))
        incorporate_analysis(state, result)
        self.assertEqual(allowed_arc_configurations(state, 0, 0), ("tr", "bl"))
        self.assertEqual(allowed_arc_configurations(state, 0, 1), ARC_CYCLE)
        self.assertEqual(allowed_arc_configurations(state, 1, 0), ARC_CYCLE)

    def test_later_clue_consults_learned_neighbor_domain(self):
        state = board(2, 2)
        # Model an exhaustive result whose region necessarily reaches cell below.
        proven = ClueAnalysis(accepted_states=[((0, 0, "tl"), (1, 0, "br")),
                                              ((0, 0, "tr"), (1, 0, "bl"))])
        incorporate_analysis(state, proven)
        self.assertEqual(allowed_arc_configurations(state, 1, 0), ("br", "bl"))
        state["cells"][1][1]["number"] = 3
        # Compare domain-based search against the union of searches with each
        # supported configuration explicitly fixed, from a different clue.
        supported = set()
        for first, below in product(("tl", "tr"), ("br", "bl")):
            explicit = copy.deepcopy(state)
            explicit.pop("arc_domains")
            explicit["cells"][0][0]["arc"] = first
            explicit["cells"][1][0]["arc"] = below
            supported.update(analyze_clue(explicit, (1, 1), accepted_limit=10000).accepted_states)
        result = analyze_clue(state, (1, 1), accepted_limit=10000)
        self.assertEqual(set(result.accepted_states), supported)
        for accepted in result.accepted_states:
            self.assertTrue(all(orientation in ("br", "bl") for r, c, orientation in accepted if (r, c) == (1, 0)))

    def test_partial_or_empty_results_do_not_learn(self):
        state = board(1, 1)
        original = copy.deepcopy(state)
        for result in (ClueAnalysis(), ClueAnalysis(accepted_states=[((0, 0, "tl"),)], limit_reached=True),
                       ClueAnalysis(accepted_states=[((0, 0, "tl"),)], cancelled=True)):
            self.assertEqual(incorporate_analysis(state, result), {"removed": 0, "applied": False})
            self.assertEqual(state, original)

    def test_master_list_persistence_and_history(self):
        import json
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = board(1, 1)
        editor.state["cells"][0][0]["number"] = 4
        original = copy.deepcopy(editor.state)
        editor.undo_stack, editor.redo_stack = [], []
        editor.draw = lambda: None
        editor.save = lambda: True
        incorporate_analysis(editor.state, analyze_clue(editor.state, (0, 0)))
        editor.commit(original, preserve_domains=True)
        inferred = copy.deepcopy(editor.state)
        self.assertEqual(validate_state(json.loads(json.dumps(inferred))), inferred)
        editor.undo()
        self.assertEqual(editor.state, original)
        editor.redo()
        self.assertEqual(editor.state, inferred)
        before_edit = copy.deepcopy(editor.state)
        editor.state["cells"][0][0]["number"] = 8
        editor.commit(before_edit)
        self.assertNotIn("arc_domains", editor.state)

    def test_multiple_states_apply_shared_arcs_and_no_arc_only(self):
        state = board(2, 2)
        result = ClueAnalysis(accepted_states=[
            ((0, 0, "tl"), (0, 1, "tr"), (1, 0, None), (1, 1, "br")),
            ((0, 0, "tl"), (0, 1, "tr"), (1, 0, None), (1, 1, "bl")),
        ])
        changes = incorporate_analysis(state, result)
        self.assertFalse(changes["applied"])
        self.assertEqual(changes["forced"], 3)
        self.assertEqual(state["cells"][0][0]["arc"], "tl")
        self.assertEqual(state["cells"][0][1]["arc"], "tr")
        self.assertEqual(state["arc_domains"][1][0], [None])
        self.assertEqual(state["cells"][1][1]["arc"], None)
        self.assertEqual(state["arc_domains"][1][1], ["br", "bl"])

    def test_shared_config_absent_from_one_state_is_not_applied(self):
        state = board(1, 2)
        result = ClueAnalysis(accepted_states=[((0, 0, "tl"), (0, 1, "tr")),
                                              ((0, 0, "tl"),)])
        incorporate_analysis(state, result)
        self.assertEqual(state["cells"][0][0]["arc"], "tl")
        self.assertEqual(state["cells"][0][1]["arc"], None)
        self.assertEqual(allowed_arc_configurations(state, 0, 1), ARC_CYCLE)

    def test_previews_are_display_only_and_state_zero_is_confirmed(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = board(1, 2)
        editor.state["cells"][0][0]["arc"] = "tl"
        editor.analysis_result = ClueAnalysis(accepted_states=[((0, 0, "tl"), (0, 1, "tr")),
                                                              ((0, 0, "tl"), (0, 1, "br"))])
        original = copy.deepcopy(editor.state)
        editor.draw = lambda: None
        editor.set_preview(1)
        display, colors = editor.preview_grid()
        self.assertEqual(display["cells"][0][1]["arc"], "tr")
        self.assertEqual(colors, {(0, 1): "#1769aa"})
        editor.set_preview(2)
        self.assertEqual(editor.preview_grid()[0]["cells"][0][1]["arc"], "br")
        editor.set_preview(0)
        self.assertIs(editor.preview_grid()[0], editor.state)
        self.assertEqual(editor.preview_grid()[1], {})
        self.assertEqual(editor.state, original)
        editor.set_preview(-1)
        self.assertEqual(editor.preview_index, 0)
        editor.set_preview(99)
        self.assertEqual(editor.preview_index, 2)





if __name__ == "__main__":
    unittest.main()
