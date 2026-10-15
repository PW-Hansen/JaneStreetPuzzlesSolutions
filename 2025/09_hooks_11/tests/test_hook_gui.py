import time
import tkinter as tk
import unittest
from unittest.mock import patch

from functions.model import Puzzle
from puzzle_gui import Editor


class HookGuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.writer = patch('puzzle_gui.write').start()
        self.errors = patch('puzzle_gui.messagebox.showerror', side_effect=AssertionError('Unexpected error dialog')).start()

    def tearDown(self):
        self.root.destroy()
        patch.stopall()

    def wait_for_search(self, editor):
        deadline = time.perf_counter() + 3
        while editor.search is not None and time.perf_counter() < deadline:
            self.root.update()
        self.assertIsNone(editor.search, 'Search did not finish within three seconds')

    def test_analysis_navigation_commit_and_undo(self):
        puzzle = Puzzle('Gui', 3, 3)
        puzzle.change('entries', '1,1', '1')
        editor = Editor(self.root, puzzle)
        editor.draw_hooks()
        self.wait_for_search(editor)
        self.assertEqual(len(puzzle.data['analysis']['candidates']), 4)
        self.assertEqual(puzzle.data['analysis']['outcome'], 'complete')
        self.assertEqual(len(puzzle.data['analysis']['canonical_borders']), 4)
        self.assertEqual(puzzle.data['borders'], {})
        editor.navigate_hooks(1)
        self.assertEqual(puzzle.data['analysis']['preview'], 1)
        editor.confirmed_hooks()
        self.assertEqual(puzzle.data['analysis']['preview'], -1)
        self.assertIn('4 canonical borders', editor.analysis_status.get())
        editor.navigate_hooks(1)
        editor.use_hooks()
        self.assertTrue(puzzle.data['borders'])
        editor.undo()
        self.assertFalse(puzzle.data['borders'])
        editor.undo()
        self.assertNotIn('analysis', puzzle.data)
        editor.redo()
        self.assertIn('analysis', puzzle.data)
        self.assertTrue(self.writer.called)
        self.assertIn('Complete', editor.analysis_status.get())

    def test_abort_is_incomplete_and_edit_discards_search(self):
        puzzle = Puzzle('Gui', 9, 9)
        puzzle.change('entries', '4,4', '1')
        editor = Editor(self.root, puzzle)
        editor.draw_hooks()
        editor.abort_hooks()
        self.wait_for_search(editor)
        self.assertEqual(puzzle.data['analysis']['outcome'], 'cancelled')
        self.assertIn('incomplete', editor.analysis_status.get())
        editor.draw_hooks()
        puzzle.change('entries', '0,0', '2')
        editor.changed()
        self.wait_for_search(editor)
        self.assertNotIn('analysis', puzzle.data)
        self.assertIn('puzzle state changed', editor.analysis_status.get())

    def test_invalid_anchor_has_feedback_without_starting(self):
        editor = Editor(self.root, Puzzle('Gui', 3, 3))
        editor.draw_hooks()
        self.assertIsNone(editor.search)
        self.assertIn('1-clue', editor.analysis_status.get())


if __name__ == '__main__':
    unittest.main()
