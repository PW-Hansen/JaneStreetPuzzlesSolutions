import copy
import json
import unittest
from types import SimpleNamespace

from clue_analysis import ClueAnalysis
from puzzle_gui import PuzzleEditor, blank_grid, save_accepted_states, validate_state, prune_saved_states


class SavedAnalysisTests(unittest.TestCase):
    def board(self):
        state = {'rows': 2, 'columns': 2, 'cells': blank_grid(2, 2)}
        state['cells'][0][0]['number'] = 21
        state['cells'][0][1]['number'] = 27
        return state

    def test_completed_states_round_trip_and_incomplete_runs_preserve_them(self):
        state = self.board()
        result = ClueAnalysis(accepted_states=[((0, 0, 'tl'),), ((0, 0, 'br'),)])
        self.assertTrue(save_accepted_states(state, (0, 0), result))
        saved = copy.deepcopy(state)
        self.assertEqual(validate_state(json.loads(json.dumps(state))), saved)
        for flag in ('cancelled', 'limit_reached', 'worklist_limit_reached'):
            self.assertFalse(save_accepted_states(state, (0, 0), ClueAnalysis(**{flag: True})))
            self.assertEqual(state, saved)
        self.assertFalse(save_accepted_states(state, (0, 0),
                         ClueAnalysis(accepted_states=[((0, 0, 'tl'),)] * 25)))
        self.assertEqual(state, saved)

    def test_click_switches_saved_clue_and_resets_preview_without_editing(self):
        state = self.board()
        save_accepted_states(state, (0, 0), ClueAnalysis(accepted_states=[((0, 0, 'tl'),), ((0, 0, 'br'),)]))
        save_accepted_states(state, (0, 1), ClueAnalysis(accepted_states=[((0, 1, 'tr'),), ((0, 1, 'bl'),)]))
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = state
        editor.mode = SimpleNamespace(get=lambda: 'arc')
        editor.size = 50
        editor.canvas = SimpleNamespace(focus_set=lambda: None, canvasx=lambda x: x, canvasy=lambda y: y)
        editor.draw = lambda: None
        editor.load_saved_clue((0, 0))
        editor.set_preview(1)
        self.assertEqual(editor.preview_grid()[0]['cells'][0][0]['arc'], 'tl')
        before = copy.deepcopy(state)
        editor.click(SimpleNamespace(x=67, y=17))
        self.assertEqual(editor.preview_index, 0)
        self.assertEqual(editor.analysis_result.source_clue, (0, 1))
        self.assertEqual(editor.preview_grid(), (state, {}))
        editor.set_preview(2)
        self.assertEqual(editor.preview_grid()[0]['cells'][0][1]['arc'], 'bl')
        self.assertEqual(state, before)

    def test_invalid_saved_placements_rejected(self):
        state = self.board()
        state['saved_analyses'] = {'0,0': {'clue': 21, 'states': [[[5, 0, 'tl']]]}}
        with self.assertRaises(ValueError):
            validate_state(state)

    def test_placed_arc_prunes_conflicts_but_omitted_cells_are_unrestricted(self):
        state = self.board()
        save_accepted_states(state, (0, 0), ClueAnalysis(accepted_states=[
            ((0, 0, 'tl'), (1, 0, None)), ((0, 0, 'br'), (1, 0, 'tr')), ((0, 0, None),)]))
        save_accepted_states(state, (0, 1), ClueAnalysis(accepted_states=[((0, 1, 'tr'), (1, 0, 'tl'))]))
        before = copy.deepcopy(state)
        state['cells'][1][0]['arc'] = 'tr'
        self.assertEqual(prune_saved_states(state), 2)
        self.assertNotIn('0,1', state['saved_analyses'])
        self.assertEqual(len(state['saved_analyses']['0,0']['states']), 2)
        # Removing the arc does not restore discarded states; undo does.
        state['cells'][1][0]['arc'] = None
        self.assertEqual(prune_saved_states(state), 0)
        self.assertEqual(len(before['saved_analyses']['0,0']['states']), 3)

    def test_commit_prunes_and_saves_with_undo_snapshot_and_state_zero(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = self.board()
        save_accepted_states(editor.state, (0, 0), ClueAnalysis(accepted_states=[
            ((0, 0, 'tl'),), ((0, 0, 'br'),)]))
        editor.selected = (0, 0)
        editor.preview_index = 2
        editor.undo_stack, editor.redo_stack = [], []
        editor.cancel_clue_analysis = lambda: None
        editor.draw = lambda: None
        saved = []
        editor.save = lambda: saved.append(copy.deepcopy(editor.state))
        previous = copy.deepcopy(editor.state)
        editor.state['cells'][0][0]['arc'] = 'tl'
        editor.commit(previous, preserve_domains=True)
        self.assertEqual(editor.preview_index, 0)
        self.assertEqual(editor.analysis_result.accepted_states, [((0, 0, 'tl'),)])
        self.assertEqual(len(saved[-1]['saved_analyses']['0,0']['states']), 1)
        self.assertEqual(editor.undo_stack[-1], previous)


if __name__ == '__main__':
    unittest.main()
