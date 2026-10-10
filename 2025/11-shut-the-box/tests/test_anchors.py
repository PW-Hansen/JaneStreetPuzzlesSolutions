import unittest
from functions.anchors import select_solver_anchor, neighborhood_box_count


class AnchorSelectionTests(unittest.TestCase):
    def test_explicit_coordinates_are_one_based(self):
        boxes = [False]*400
        boxes[4*20+5] = True
        self.assertEqual(select_solver_anchor(boxes, 20, 20, (5, 6)), 85)
        for coordinates in ((0, 1), (21, 1), (1, 1)):
            with self.assertRaises(ValueError): select_solver_anchor(boxes, 20, 20, coordinates)

    def test_primary_score_uses_three_by_three_including_center(self):
        boxes = [False]*49
        for r in range(1, 4):
            for c in range(1, 4): boxes[r*7+c] = True
        self.assertEqual(select_solver_anchor(boxes, 7, 7), 2*7+2)
        self.assertEqual(neighborhood_box_count(boxes, 7, 7, 2*7+2, 1), 9)

    def test_five_by_five_breaks_three_by_three_tie(self):
        boxes = [False]*25
        boxes[0] = boxes[2*5+2] = boxes[24] = True
        self.assertEqual(neighborhood_box_count(boxes, 5, 5, 0, 1), 1)
        self.assertEqual(neighborhood_box_count(boxes, 5, 5, 12, 1), 1)
        self.assertEqual(select_solver_anchor(boxes, 5, 5), 12)

    def test_remaining_tie_uses_earliest_row_major_index(self):
        boxes = [None]*400
        boxes[19] = boxes[20] = True
        self.assertEqual(select_solver_anchor(boxes, 20, 20), 19)
        with self.assertRaises(ValueError): select_solver_anchor([None]*4, 2, 2)

class SolverAnchorRegionTests(unittest.TestCase):
    def test_solver_can_anchor_a_confirmed_region_other_than_largest(self):
        from functions.folding import folding_trials
        boxes = [True, True, False, True]
        trials = list(folding_trials(boxes, 1, 4, 3, use_anchor_region=True))
        self.assertIsInstance(trials, list)
        with self.assertRaises(ValueError): list(folding_trials(boxes, 1, 4, 3))
