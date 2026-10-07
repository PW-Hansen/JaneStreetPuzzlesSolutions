import unittest
from itertools import product

from puzzle_gui import RegionArea, blank_grid, determine_regions, determine_region_areas


class RegionAreaTests(unittest.TestCase):
    def board(self, rows, columns):
        return {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}

    def test_whole_grid(self):
        areas = determine_region_areas(self.board(3, 4))
        self.assertEqual(list(areas.values()), [RegionArea(12, 0, 0)])
        self.assertEqual(next(iter(areas.values())).integer_area, 12)

    def test_single_arc_each_orientation(self):
        for orientation in ("tl", "tr", "br", "bl"):
            state = self.board(1, 1)
            state["cells"][0][0]["arc"] = orientation
            areas = determine_region_areas(state)
            self.assertEqual(set(areas.values()), {RegionArea(0, 1, 0), RegionArea(0, 0, 1)})
            self.assertTrue(all(not area.is_integer for area in areas.values()))

    def test_balanced_and_unbalanced_exact_expressions(self):
        self.assertEqual(RegionArea(3, 2, 2).integer_area, 5)
        self.assertEqual(str(RegionArea(3, 2, 2)), "5")
        self.assertEqual(str(RegionArea(0, 1, 0)), "π/4")
        self.assertEqual(str(RegionArea(0, 0, 1)), "1 − π/4")
        self.assertIsNone(RegionArea(3, 2, 1).integer_area)

    def test_dangling_arc_can_have_integer_area(self):
        state = self.board(3, 3)
        state["cells"][1][1]["arc"] = "tl"
        regions, _, invalid = determine_regions(state)
        self.assertEqual(invalid, [(1, 1)])
        area = next(iter(determine_region_areas(state, regions).values()))
        self.assertEqual(area, RegionArea(8, 1, 1))
        self.assertEqual(area.integer_area, 9)

    def test_conservation_all_small_boards(self):
        state = self.board(2, 2)
        for orientations in product((None, "tl", "tr", "br", "bl"), repeat=4):
            for cell, orientation in zip((cell for row in state["cells"] for cell in row), orientations):
                cell["arc"] = orientation
            regions = determine_regions(state)[0]
            areas = determine_region_areas(state, regions)
            self.assertEqual(areas, determine_region_areas(state))
            self.assertEqual(sum(area.constant for area in areas.values()), 4)
            self.assertEqual(sum(area.pi_quarters for area in areas.values()), 0)
            arc_count = sum(orientation is not None for orientation in orientations)
            self.assertEqual(sum(area.arc_insides for area in areas.values()), arc_count)
            self.assertEqual(sum(area.arc_outsides for area in areas.values()), arc_count)


if __name__ == "__main__":
    unittest.main()
