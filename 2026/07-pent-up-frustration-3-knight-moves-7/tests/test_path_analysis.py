from copy import deepcopy
import unittest

from functions.state import Session, new_grid
from functions.path_analysis import ContinuationSearch, apply_continuation


def analyze(session, start, moves):
    search = ContinuationSearch(session.grid, start, moves)
    while not search.done:
        search.advance()
    return search


def board(rows, columns, start, score, visit, target, target_score):
    session = Session(new_grid("path", rows, columns))
    session.grid["scores"][start[0]][start[1]] = score
    session.grid["visits"][start[0]][start[1]] = visit
    session.grid["scores"][target[0]][target[1]] = target_score
    return session


class PathAnalysisTests(unittest.TestCase):
    def test_unique_level_move_commits_visits_scores_and_non_towers(self):
        s = board(3, 3, (0, 0), 0, 0, (1, 2), 1)
        original = deepcopy(s.grid)
        search = analyze(s, (0, 0), 1)
        self.assertEqual(search.path_count, 1)
        self.assertTrue(apply_continuation(s, search))
        self.assertEqual(s.grid["visits"][1][2], 1)
        self.assertIn([0, 0], s.grid["non_towers"])
        self.assertIn([1, 2], s.grid["non_towers"])
        self.assertEqual(len(s.undo_stack), 1)
        s.history()
        self.assertEqual(s.grid, original)

    def test_up_and_down_moves_have_two_square_planar_displacement(self):
        up = board(1, 3, (0, 0), 2, 1, (0, 2), 4)
        search = analyze(up, (0, 0), 1)
        self.assertEqual(search.path_count, 1)
        apply_continuation(up, search)
        self.assertEqual(up.grid["towers"], [[0, 2]])
        self.assertEqual(up.grid["visits"][0][2], 2)
        down = board(1, 3, (0, 0), 2, 1, (0, 2), 1)
        down.mark_tower((0, 0))
        search = analyze(down, (0, 0), 1)
        self.assertEqual(search.path_count, 1)
        apply_continuation(down, search)
        self.assertIn([0, 2], down.grid["non_towers"])

    def test_multiple_paths_apply_only_shared_information(self):
        s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
        search = analyze(s, (0, 0), 2)
        self.assertEqual(search.path_count, 2)
        apply_continuation(s, search)
        self.assertEqual(s.grid["visits"][3][3], 2)
        self.assertIsNone(s.grid["visits"][1][2])
        self.assertIsNone(s.grid["visits"][2][1])
        self.assertIsNone(s.grid["scores"][1][2])

    def test_visited_cell_blocks_one_branch(self):
        s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
        s.grid["visits"][1][2] = 20
        search = analyze(s, (0, 0), 2)
        self.assertEqual(search.path_count, 1)
        apply_continuation(s, search)
        self.assertEqual(s.grid["visits"][2][1], 1)
        self.assertEqual(s.grid["scores"][2][1], 1)
        self.assertEqual(s.grid["visits"][1][2], 20)

    def test_retained_paths_resolve_after_score_edit_and_undo(self):
        s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
        apply_continuation(s, analyze(s, (0, 0), 2))
        self.assertEqual(len(s.pending_paths[0]), 2)
        s.select((1, 2))
        s.mode = "Score"
        s.set_value(99)
        self.assertEqual(s.grid["scores"][2][1], 1)
        self.assertEqual(s.grid["visits"][2][1], 1)
        self.assertFalse(s.pending_paths)
        self.assertIn("applied", s.path_notice)
        s.history()
        self.assertEqual(len(s.pending_paths[0]), 2)
        self.assertIsNone(s.grid["visits"][2][1])
        s.history(True)
        self.assertEqual(s.grid["visits"][2][1], 1)
        self.assertFalse(s.pending_paths)

    def test_retained_paths_resolve_after_visit_or_tower_edit(self):
        for mode, value in (("Visit number", 20), ("Tower", None)):
            with self.subTest(mode=mode):
                s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
                apply_continuation(s, analyze(s, (0, 0), 2))
                s.select((1, 2))
                s.mode = mode
                if mode == "Tower":
                    s.mark_tower((1, 2))
                else:
                    s.set_value(value)
                self.assertEqual(s.grid["visits"][2][1], 1)
                self.assertFalse(s.pending_paths)

    def test_saved_alternatives_survive_reload_and_reset_undo(self):
        import json
        s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
        apply_continuation(s, analyze(s, (0, 0), 2))
        restored = Session.deserialize(json.loads(json.dumps(s.serialize())))
        self.assertEqual(restored.pending_paths, s.pending_paths)
        restored.reset_visits()
        self.assertFalse(restored.pending_paths)
        self.assertTrue(all(value is None for row in restored.grid["visits"] for value in row))
        restored.history()
        self.assertEqual(restored.pending_paths, s.pending_paths)
        restored.select((1, 2))
        restored.mode = "Score"
        restored.set_value(99)
        self.assertEqual(restored.grid["visits"][2][1], 1)

    def test_all_retained_paths_impossible_reports_without_applying(self):
        s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
        apply_continuation(s, analyze(s, (0, 0), 2))
        s.select((3, 3))
        s.mode = "Score"
        s.set_value(99)
        self.assertFalse(s.pending_paths)
        self.assertIn("No retained path", s.path_notice)
        self.assertIsNone(s.grid["visits"][1][2])
        self.assertIsNone(s.grid["visits"][2][1])

    def test_tower_edits_force_visit_eleven_while_two_paths_remain(self):
        s = board(8, 8, (2, 3), 23, 9, (3, 0), 528)
        # Four regions allow the three relevant towers to be asserted independently.
        s.grid["borders"] = ([[2, c, 3, c] for c in range(8)]
                             + [[r, 1, r, 2] for r in range(8)])
        s.mark_tower((3, 0))
        s.grid["visits"][3][0] = 12
        alternatives = [((4, 2), (5, 0)), ((3, 1), (5, 0)),
                        ((3, 1), (1, 0)), ((1, 1), (3, 2)),
                        ((0, 2), (1, 0))]
        s.pending_paths = [[[[2, 3, 23, 9, 0], [*first, 33, 10, 0],
                              [*second, 44, 11, 0], [3, 0, 528, 12, 1]]
                             for first, second in alternatives]]
        s.mark_tower((3, 2))
        self.assertEqual(len(s.pending_paths[0]), 4)
        self.assertIsNone(s.grid["visits"][5][0])
        s.mark_tower((1, 0))
        self.assertEqual(len(s.pending_paths[0]), 2)
        self.assertEqual(s.grid["visits"][5][0], 11)
        self.assertEqual(s.grid["scores"][5][0], 44)
        self.assertIn([5, 0], s.grid["non_towers"])
        self.assertIsNone(s.grid["visits"][4][2])
        self.assertIsNone(s.grid["visits"][3][1])
        s.history()
        self.assertEqual(len(s.pending_paths[0]), 4)
        self.assertIsNone(s.grid["visits"][5][0])
        s.history(True)
        self.assertEqual(s.grid["visits"][5][0], 11)

    def test_clue_conflicts_and_multiple_targets_do_not_commit(self):
        s = board(4, 4, (0, 0), 0, 0, (3, 3), 3)
        s.grid["scores"][1][2] = 99
        s.grid["scores"][2][1] = 99
        before = deepcopy(s.grid)
        search = analyze(s, (0, 0), 2)
        self.assertEqual(search.path_count, 0)
        self.assertFalse(apply_continuation(s, search))
        self.assertEqual(before, s.grid)
        s = board(3, 3, (0, 0), 0, 0, (1, 2), 1)
        s.grid["scores"][2][1] = 1
        search = analyze(s, (0, 0), 1)
        self.assertEqual(len(search.matching_targets), 2)
        self.assertFalse(apply_continuation(s, search))

    def test_unreachable_target_and_tower_contradiction(self):
        s = board(3, 3, (0, 0), 0, 0, (1, 1), 1)
        self.assertEqual(analyze(s, (0, 0), 1).path_count, 0)
        s = board(3, 3, (0, 0), 0, 0, (1, 2), 1)
        s.mark_tower((1, 2))
        self.assertEqual(analyze(s, (0, 0), 1).path_count, 0)

    def test_incomplete_or_stale_analysis_cannot_apply(self):
        s = board(3, 3, (0, 0), 0, 0, (1, 2), 1)
        search = ContinuationSearch(s.grid, (0, 0), 1)
        self.assertFalse(apply_continuation(s, search))
        while not search.done:
            search.advance()
        s.grid["scores"][2][2] = 7
        with self.assertRaises(ValueError):
            apply_continuation(s, search)
