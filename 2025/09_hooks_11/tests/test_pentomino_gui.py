import time
import tkinter as tk
import unittest
from unittest.mock import patch

from functions.model import Puzzle
from functions.pentominoes import preview_record
from puzzle_gui import Editor
from pentomino_fixtures import example_puzzle


class PentominoGuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.writer = patch('puzzle_gui.write').start()
        patch('puzzle_gui.messagebox.showerror', side_effect=AssertionError('Unexpected error dialog')).start()

    def tearDown(self):
        self.root.destroy()
        patch.stopall()

    def wait_for_search(self, editor):
        deadline = time.perf_counter()+3
        while editor.search is not None and time.perf_counter() < deadline:
            self.root.update()
        self.assertIsNone(editor.search)

    def test_requires_hooks_and_searches_navigates_without_committing(self):
        missing = Editor(self.root, Puzzle('Missing',5,5))
        missing.draw_pentominoes()
        self.assertIsNone(missing.search)
        self.assertIn('Draw hooks first', missing.pentomino_status.get())
        for child in self.root.winfo_children():
            child.destroy()
        puzzle = example_puzzle()
        original_entries = dict(puzzle.data['entries'])
        editor = Editor(self.root, puzzle)
        editor.draw_pentominoes()
        self.wait_for_search(editor)
        self.assertEqual(len(puzzle.data['pentomino_analysis']['candidates']), 1)
        self.assertEqual(len(puzzle.data['analysis']['candidates']), 1)
        self.assertEqual(puzzle.data['analysis']['canonical_borders'], puzzle.data['analysis']['candidates'][0])
        self.assertIsNotNone(preview_record(puzzle.data))
        self.assertEqual(puzzle.data['entries'], original_entries)
        self.assertIn('Complete', editor.pentomino_status.get())
        editor.pentomino_view.set('Individual placements')
        editor.change_pentomino_view()
        self.assertEqual(puzzle.data['pentomino_analysis']['view'], 'placements')
        editor.navigate_pentominoes(1)
        self.assertEqual(puzzle.data['pentomino_analysis']['preview'], 1)
        editor.confirmed_pentominoes()
        self.assertIsNone(preview_record(puzzle.data))
        editor.undo()
        self.assertNotIn('pentomino_analysis', puzzle.data)
        editor.redo()
        self.assertIn('pentomino_analysis', puzzle.data)
        self.assertTrue(self.writer.called)

    def test_abort_and_edit_cancellation(self):
        puzzle = example_puzzle()
        editor = Editor(self.root, puzzle)
        editor.draw_pentominoes()
        editor.abort_hooks()
        self.wait_for_search(editor)
        self.assertEqual(puzzle.data['pentomino_analysis']['outcome'], 'cancelled')
        self.assertIn('incomplete', editor.pentomino_status.get())
        editor.draw_pentominoes()
        puzzle.change('entries','0,1','4')
        editor.changed()
        self.wait_for_search(editor)
        self.assertNotIn('pentomino_analysis', puzzle.data)
        self.assertIn('state changed', editor.pentomino_status.get())


if __name__ == '__main__':
    unittest.main()
