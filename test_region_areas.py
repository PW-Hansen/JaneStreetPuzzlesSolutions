import unittest
from itertools import product

from puzzle_gui import Region, blank_grid, determine_regions, determine_region_areas


class RegionAreaTests(unittest.TestCase):
    def board(self, rows, columns):
        return {"rows": rows, "columns": columns, "cells": blank_grid(rows, columns)}

    def test_whole_grid(self):
        areas = determine_region_areas(self.board(3, 4))
        self.assertEqual(list(areas.values()), [12])
        self.assertEqual(next(iter(areas.values())), 12)

    def test_region_objects_own_area_and_fragments(self):
        state = self.board(2, 2)
        mapping, _, invalid = determine_regions(state)
        region = mapping[(0, 0, 0)]
        self.assertIsInstance(region, Region)
        self.assertEqual(region.area, 4)
        self.assertEqual(region.fragments, frozenset(mapping))
        self.assertTrue(region.is_valid)
        self.assertEqual(invalid, [])
        self.assertTrue(all(other is region for other in mapping.values()))
        self.assertIs(determine_region_areas(state, mapping)[region.id], region.area)

    def test_single_arc_each_orientation(self):
        for orientation in ("tl", "tr", "br", "bl"):
            state = self.board(1, 1)
            state["cells"][0][0]["arc"] = orientation
            areas = determine_region_areas(state)
            self.assertEqual(set(areas.values()), {"π/4", "1 − π/4"})
            self.assertTrue(all(not region.is_integer for region in set(determine_regions(state)[0].values())))

    def test_balanced_and_unbalanced_exact_expressions(self):
        self.assertEqual(Region(0, frozenset(), 3, 2, 2).area, 5)
        self.assertEqual(str(Region(0, frozenset(), 3, 2, 2).area), "5")
        self.assertEqual(Region(0, frozenset(), 0, 1, 0).area, "π/4")
        self.assertEqual(Region(0, frozenset(), 0, 0, 1).area, "1 − π/4")
        self.assertIsNone(Region(0, frozenset(), 3, 2, 1).integer_area)

    def test_dangling_arc_can_have_integer_area(self):
        state = self.board(3, 3)
        state["cells"][1][1]["arc"] = "tl"
        regions, _, invalid = determine_regions(state)
        self.assertEqual(invalid, [(1, 1)])
        self.assertFalse(regions[(1, 1, 0)].is_valid)
        self.assertEqual(regions[(1, 1, 0)].invalid_arcs, frozenset({(1, 1)}))
        area = next(iter(determine_region_areas(state, regions).values()))
        self.assertEqual(area, 9)
        region = regions[(1, 1, 0)]
        self.assertEqual((region.whole_cells, region.arc_insides, region.arc_outsides), (8, 1, 1))

    def test_conservation_all_small_boards(self):
        state = self.board(2, 2)
        for orientations in product((None, "tl", "tr", "br", "bl"), repeat=4):
            for cell, orientation in zip((cell for row in state["cells"] for cell in row), orientations):
                cell["arc"] = orientation
            regions = determine_regions(state)[0]
            areas = determine_region_areas(state, regions)
            self.assertEqual(areas, determine_region_areas(state))
            objects = set(regions.values())
            self.assertEqual(sum(region.constant for region in objects), 4)
            self.assertEqual(sum(region.pi_quarters for region in objects), 0)
            arc_count = sum(orientation is not None for orientation in orientations)
            self.assertEqual(sum(region.arc_insides for region in objects), arc_count)
            self.assertEqual(sum(region.arc_outsides for region in objects), arc_count)


if __name__ == "__main__":
    unittest.main()
