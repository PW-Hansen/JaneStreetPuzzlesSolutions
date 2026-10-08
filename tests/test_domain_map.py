import copy
import unittest
from types import SimpleNamespace

from puzzle_gui import (ARC_CYCLE, PuzzleEditor, allowed_arc_configurations,
                        blank_grid, validate_state)


class DomainMapTests(unittest.TestCase):
    def make_editor(self):
        editor = PuzzleEditor.__new__(PuzzleEditor)
        editor.state = {'rows': 2, 'columns': 2, 'cells': blank_grid(2, 2)}
        editor.selected = (0, 0)
        editor.undo_stack, editor.redo_stack = [], []
        editor.draw = lambda: None
        editor.save = lambda: True
        editor.cancel_clue_analysis = lambda: None
        editor.status = SimpleNamespace(set=lambda message: None)
        return editor

    def test_manual_exclusion_uses_master_list_and_survives_undo_redo(self):
        editor = self.make_editor()
        original = copy.deepcopy(editor.state)
        editor.toggle_domain('tr')
        self.assertNotIn('tr', allowed_arc_configurations(editor.state, 0, 0))
        self.assertEqual(allowed_arc_configurations(editor.state, 0, 1), ARC_CYCLE)
        validate_state(editor.state)
        editor.undo()
        self.assertEqual(editor.state, original)
        editor.redo()
        self.assertNotIn('tr', allowed_arc_configurations(editor.state, 0, 0))

    def test_other_cells_and_learned_restrictions_are_preserved(self):
        editor = self.make_editor()
        editor.state['arc_domains'] = [[['tl', 'tr'], ['br']], [list(ARC_CYCLE), list(ARC_CYCLE)]]
        editor.toggle_domain('tr')
        self.assertEqual(editor.state['arc_domains'][0], [['tl'], ['br']])
        editor.toggle_domain('tr')
        self.assertEqual(editor.state['arc_domains'][0], [['tl', 'tr'], ['br']])

    def test_last_configuration_cannot_be_removed(self):
        editor = self.make_editor()
        editor.state['arc_domains'] = [[[None], list(ARC_CYCLE)], [list(ARC_CYCLE), list(ARC_CYCLE)]]
        previous = copy.deepcopy(editor.state)
        editor.toggle_domain(None)
        self.assertEqual(editor.state, previous)
        self.assertFalse(editor.undo_stack)

    def test_fixed_marks_cannot_be_excluded(self):
        for marking in ({'green': True}, {'arc': 'tr'}):
            editor = self.make_editor()
            editor.state['cells'][0][0].update(marking)
            previous = copy.deepcopy(editor.state)
            editor.toggle_domain('tr')
            self.assertEqual(editor.state, previous)

    def test_manual_arc_cycle_preserves_deductions_and_skips_excluded_arcs(self):
        editor = self.make_editor()
        editor.state['arc_domains'] = [[['tl', 'br'], [None, 'tr']],
                                       [list(ARC_CYCLE), list(ARC_CYCLE)]]
        domains = copy.deepcopy(editor.state['arc_domains'])
        editor.mode = SimpleNamespace(get=lambda: 'arc')
        editor.size = 40
        editor.canvas = SimpleNamespace(focus_set=lambda: None, canvasx=lambda x: x,
                                        canvasy=lambda y: y)
        event = SimpleNamespace(x=36, y=36)
        for expected in ('tl', 'br', None):
            editor.click(event)
            self.assertEqual(editor.state['cells'][0][0]['arc'], expected)
            self.assertEqual(editor.state['arc_domains'], domains)
            validate_state(editor.state)
        editor.undo()
        self.assertEqual(editor.state['arc_domains'], domains)
        editor.redo()
        self.assertEqual(editor.state['arc_domains'], domains)

    def test_arc_erasure_and_delete_preserve_master_list(self):
        editor = self.make_editor()
        editor.state['arc_domains'] = [[['tl', 'br'], [None, 'tr']],
                                       [list(ARC_CYCLE), list(ARC_CYCLE)]]
        domains = copy.deepcopy(editor.state['arc_domains'])
        editor.state['cells'][0][0]['arc'] = 'tl'
        editor.mode = SimpleNamespace(get=lambda: 'arc')
        editor.size = 40
        editor.canvas = SimpleNamespace(focus_set=lambda: None, canvasx=lambda x: x,
                                        canvasy=lambda y: y)
        editor.click(SimpleNamespace(x=36, y=36), erase=True)
        self.assertIsNone(editor.state['cells'][0][0]['arc'])
        self.assertEqual(editor.state['arc_domains'], domains)
        editor.state['cells'][0][0]['arc'] = 'br'
        editor.key(SimpleNamespace(keysym='Delete', state=0))
        self.assertIsNone(editor.state['cells'][0][0]['arc'])
        self.assertEqual(editor.state['arc_domains'], domains)


if __name__ == '__main__':
    unittest.main()
