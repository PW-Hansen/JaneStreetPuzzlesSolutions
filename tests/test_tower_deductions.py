from copy import deepcopy
import unittest

from functions.state import Session, new_grid
from functions.regions import tower_colors
from functions.rendering import primitives


class TowerDeductionTests(unittest.TestCase):
    def setUp(self):
        self.session = Session(new_grid("deductions", 1, 3))

    def test_analysis_tower_assertion_excludes_whole_region_and_undoes_atomically(self):
        s = self.session
        s.mark_tower((0, 1))  # Works in Select mode, for analysis callers.
        self.assertEqual(s.grid["towers"], [[0, 1]])
        self.assertEqual(s.grid["non_towers"], [[0, 0], [0, 2]])
        self.assertEqual(len(s.undo_stack), 1)
        s.history()
        self.assertFalse(s.grid["towers"])
        self.assertFalse(s.grid["non_towers"])
        s.history(True)
        self.assertEqual(s.grid["non_towers"], [[0, 0], [0, 2]])

    def test_last_available_cell_becomes_tower_and_survives_save(self):
        s = self.session
        s.mark_tower((0, 0), False)
        self.assertFalse(s.grid["towers"])
        s.mark_tower((0, 1), False)
        self.assertEqual(s.grid["towers"], [[0, 2]])
        restored = Session.deserialize(s.serialize())
        self.assertEqual(restored.grid, s.grid)
        restored.history()
        self.assertFalse(restored.grid["towers"])
        self.assertEqual(restored.grid["non_towers"], [[0, 0]])

    def test_conflicts_leave_grid_and_history_intact(self):
        s = self.session
        s.mark_tower((0, 0), False)
        s.mark_tower((0, 1), False)
        before = deepcopy(s.serialize())
        with self.assertRaises(ValueError):
            s.mark_tower((0, 2), False)
        self.assertEqual(s.serialize(), before)
        s.mark_tower((0, 2))
        before = deepcopy(s.serialize())
        with self.assertRaises(ValueError):
            s.mark_tower((0, 1))
        self.assertEqual(s.serialize(), before)

    def test_clear_retracts_deductions_and_non_tower_toggle(self):
        s = self.session
        s.mode = "Tower"
        s.select((0, 0))
        s.toggle_tower()
        s.toggle_tower()
        self.assertFalse(s.grid["non_towers"])
        s.select((0, 1))
        s.toggle_non_tower()
        self.assertEqual(s.grid["non_towers"], [[0, 1]])
        s.toggle_non_tower()
        self.assertFalse(s.grid["non_towers"])

    def test_region_split_recomputes_and_rejects_impossible_region(self):
        s = self.session
        s.mark_tower((0, 0))
        s.mode = "Cell border drawing"
        s.toggle_edge([0, 0, 0, 1])
        self.assertEqual(s.grid["non_towers"], [])
        self.assertEqual(s.grid["towers"], [[0, 0]])
        s.toggle_edge([0, 1, 0, 2])
        self.assertEqual(s.grid["towers"], [[0, 0], [0, 1], [0, 2]])
        s.toggle_edge([0, 1, 0, 2])  # Retract forced singleton towers on merge.
        self.assertEqual(s.grid["towers"], [[0, 0]])

    def test_non_tower_shading_and_bottom_bar_in_all_modes(self):
        s = self.session
        s.mark_tower((0, 0), False)
        self.assertEqual(tower_colors(s.grid)[(0, 0)], "#e5e7eb")
        self.assertEqual(tower_colors(s.grid)[(0, 1)], "#dcfce7")
        for mode in ("Select", "Tower", "Score"):
            s.mode = mode
            bars = [item for item in primitives(s) if item[0] == "line" and item[2]["width"] == 2]
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0][1][1], 66)

    def test_old_tower_files_migrate_to_deductions(self):
        grid = new_grid("legacy", 1, 3)
        for field in ("tower_marks", "non_tower_marks", "non_towers"):
            grid.pop(field)
        grid["towers"] = [[0, 0]]
        migrated = Session(grid)
        self.assertEqual(migrated.grid["non_towers"], [[0, 1], [0, 2]])
        migrated.clear_tower((0, 0))
        self.assertFalse(migrated.grid["non_towers"])
