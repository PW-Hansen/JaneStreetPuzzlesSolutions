import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from puzzle_gui import continue_region_overlays
from puzzle_gui import force_overlay_neighbors
from puzzle_gui import bordering_regions_reachable
from puzzle_gui import low_slack_connections
from puzzle_gui import InvalidOverlay
from puzzle_gui import force_bordering_growth
from puzzle_gui import reverse_overlay_orientations
from puzzle_gui import compare_incomplete_regions
from puzzle_gui import attempt_region_completions
from puzzle_gui import encode_overlay, decode_overlay
from puzzle_gui import GridCanvas, PuzzleApp, format_candidates, read_state, write_state, can_connect_region, check_grid_connectivity, grow_forced_regions, region_colors, canonical_shape, filter_containment, fraction_parts, evaluate, math_runs, draw_math, inline_math, analyze_clues, solve_rational_clue, inferred_integer_variables, minimum_region_size, find_region_overlays, shape_orientations

class VariableSearchTests(unittest.TestCase):
    def test_growth_toggle_skips_bordering_growth_but_keeps_target_growth(self):
        original=force_overlay_neighbors
        with patch('puzzle_gui.force_bordering_growth',side_effect=AssertionError('bordering growth ran')), \
             patch('puzzle_gui.force_overlay_neighbors',wraps=original) as target_growth:
            _,_,states,_=find_region_overlays([['2','',''],['','3',''],['','','']],{},forced_growth=False)
        self.assertTrue(states)
        self.assertTrue(target_growth.called)
        self.assertTrue(all(not state['neighbor_growth'] for state in states))

    def test_growth_toggle_is_carried_into_continuation(self):
        grid=[['1','',''],['','2',''],['','','3']]
        current,base,parents,_=find_region_overlays(grid,{},region=2,forced_growth=False)
        with patch('puzzle_gui.force_bordering_growth',side_effect=AssertionError('bordering growth ran')):
            _,children,_=continue_region_overlays(3,base,current,parents,forced_growth=False)
        self.assertTrue(children)

    def test_saved_state_round_trip_retains_overlay_branch_types_and_history(self):
        snapshot={'states':[{'cells':frozenset({2,3}),'assumptions':{0:1,2:2,3:2}}],
                  'index':0,'highest':2,'base':{0:1},'tested':12,'target':'2',
                  'message':'Overlay 1/1','labels':{0:1,2:2,3:2},'palette':{1:'red',2:'blue'}}
        state={'size':2,'expressions':[['a',''],['','']], 'variables':{'a':'1'},
               'overlay_snapshot':encode_overlay(snapshot),
               'overlay_history':encode_overlay({'undo':[snapshot],'redo':[]})}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'saved states'/'test.json'
            write_state(path,state)
            restored=read_state(path)
        self.assertEqual(decode_overlay(restored['overlay_snapshot']),snapshot)
        self.assertEqual(decode_overlay(restored['overlay_history']),{'undo':[snapshot],'redo':[]})

    def test_reset_keeps_equations_candidates_and_variable_analysis(self):
        app=PuzzleApp.__new__(PuzzleApp)
        def value(initial):
            storage=[initial]
            return SimpleNamespace(get=lambda:storage[0],set=lambda new:storage.__setitem__(0,new))
        app.expressions=[['a',''],['','']]
        app.variables={'a':value('1')}
        app.valid_values={'a':value('1, 2')}
        app.analytical_assignments=[{'a':Fraction(1)},{'a':Fraction(2)}]
        app.SIZE=2
        app.overlay_states=[{'cells':{0,1}}]
        app.overlay_undo=[{}]
        app.overlay_redo=[{}]
        app.overlay_message=value('Some overlay')
        app.overlay_target=value('2')
        app.disabled_cells={0}
        app.connectivity_message=value('Passed')
        app.show_values=value(True)
        app.update_display_button=lambda:None
        app.refresh=lambda:None
        app.save_state=lambda:None
        app.reset_to_equations()
        self.assertEqual(app.expressions,[['a',''],['','']])
        self.assertEqual(app.variables['a'].get(),'1')
        self.assertEqual(app.valid_values['a'].get(),'1, 2')
        self.assertEqual(len(app.analytical_assignments),2)
        self.assertEqual(app.SIZE,2)
        self.assertFalse(app.overlay_states)
        self.assertFalse(app.overlay_undo)
        self.assertFalse(app.disabled_cells)
        self.assertFalse(app.show_values.get())

    def test_completion_mirrors_through_two_higher_regions_and_preserves_branches(self):
        cells=frozenset({0,1,5,6,10})
        base={cell:5 for cell in cells}
        base.update({15:4,16:4,20:4,22:3,23:3,24:2})
        original=dict(base)
        states=attempt_region_completions(5,base,5,[{'cells':cells}])
        self.assertTrue(states)
        for state in states:
            board=state['assumptions']
            for number in (2,3,4,5):
                shape={cell for cell,value in board.items() if value==number}
                self.assertEqual(len(shape),number)
                self.assertEqual(minimum_region_size(5,board,number,shape),number)
            for number in (2,3,4):
                lower={cell for cell,value in board.items() if value==number}
                higher={cell for cell,value in board.items() if value==number+1}
                lower_shape=canonical_shape(lower,5)
                self.assertTrue(any(canonical_shape(higher-{removed},5)==lower_shape
                                    for removed in higher))
            self.assertIn(19,state['completion_growth'])
        self.assertEqual(base,original)

    def test_completion_rejects_shape_that_cannot_be_mirrored_into_higher_region(self):
        base={0:4,1:4,2:4,3:4,15:3,21:3,24:2}
        states=attempt_region_completions(5,base,4,[{'cells':frozenset({0,1,2,3})}])
        self.assertEqual(states,[])

    def test_completion_keeps_alternative_final_cells(self):
        base={0:4,1:4,5:4,6:4,15:3,16:3,24:2}
        states=attempt_region_completions(5,base,4,[{'cells':frozenset({0,1,5,6})}])
        self.assertEqual({cell for state in states for cell,value in state['completion_growth'].items()
                          if value==2},{19,23})
        self.assertEqual(len({tuple(sorted(state['assumptions'].items())) for state in states}),len(states))

    def test_partial_higher_region_comparison_matches_screenshot_deduction(self):
        rows=[
            [0,5,5,5,15,15,0,11,0,0,0,0,0],
            [0,0,0,5,0,15,0,11,0,0,11,11,11],
            [15,15,15,5,0,15,15,11,11,11,11,0,11],
            [15,0,15,15,15,15,8,8,8,12,12,12,11],
            [15,16,0,0,8,8,8,0,8,12,6,6,6],
            [0,16,0,16,16,16,16,0,8,12,12,0,6],
            [0,16,16,16,3,0,16,16,1,4,12,6,6],
            [13,13,13,13,0,0,16,4,4,4,12,10,10],
            [7,7,7,13,14,16,16,12,12,12,12,10,0],
            [7,2,2,13,14,16,14,14,14,14,0,10,0],
            [7,7,13,13,14,14,14,0,9,14,0,10,10],
            [0,7,13,9,9,9,9,0,9,14,0,0,10],
            [0,0,13,13,13,0,9,9,9,14,10,10,10]]
        board={r*13+c:value for r,row in enumerate(rows) for c,value in enumerate(row) if value}
        state={'cells':frozenset(cell for cell,value in board.items() if value==16)}
        result=compare_incomplete_regions(13,board,16,[state])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['comparison_growth'][10*13+10],14)
        first=dict(board)
        first.update({6*13+5:3,7*13+4:14,7*13+5:3})
        del first[9*13+6]
        result=compare_incomplete_regions(13,first,16,[state])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['comparison_growth'][9*13+6],14)
        self.assertEqual(result[0]['comparison_growth'][10*13+10],14)

    def test_comparison_forces_only_cells_common_to_all_reverse_placements(self):
        cells=frozenset({0,1,4,5})
        base={12:3,13:3}
        result=compare_incomplete_regions(4,base,4,[{'cells':cells}])
        self.assertEqual(result[0]['comparison_growth'],{})
        result=compare_incomplete_regions(4,{**base,8:1},4,[{'cells':cells}])
        self.assertEqual(result[0]['comparison_growth'],{9:3})
        self.assertEqual(result[0]['assumptions'][9],3)

    def test_comparison_preserves_each_parent_and_does_not_modify_inputs(self):
        cells=frozenset({0,1,4,5})
        states=[{'cells':cells,'assumptions':{12:3,13:3,8:1}},
                {'cells':cells,'assumptions':{12:3,13:3,9:1}}]
        result=compare_incomplete_regions(4,{},4,states)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['comparison_growth'],{9:3})
        self.assertEqual(result[1]['comparison_growth'],{8:3})
        self.assertNotIn(9,states[0]['assumptions'])
        self.assertNotIn(8,states[1]['assumptions'])

    def test_comparison_rejects_branch_without_a_containment_placement(self):
        result=compare_incomplete_regions(4,{12:3,13:3,8:1,9:2},4,
                                           [{'cells':frozenset({0,1,4,5})}])
        self.assertEqual(result,[])

    def test_reverse_overlays_keep_different_parent_boards_with_identical_target_shapes(self):
        cells=frozenset({0,1,4,5})
        parents=[{'cells':cells,'assumptions':{12:3,13:3,14:1}},
                 {'cells':cells,'assumptions':{12:3,13:3,15:1}},
                 {'cells':cells,'assumptions':{12:3,13:3,14:1}}]
        _,children,_=continue_region_overlays(4,{12:3,13:3},4,parents,region=3)
        self.assertEqual(len(children),4)
        self.assertEqual({child['parent_index'] for child in children},{0,1})
        self.assertEqual(len({child['cells'] for child in children}),2)
        self.assertEqual(len({tuple(sorted(child['assumptions'].items())) for child in children}),4)

    def test_overlay_undo_redo_restores_candidates_deductions_and_preview(self):
        def value(initial):
            storage=[initial]
            return SimpleNamespace(get=lambda:storage[0],set=lambda new:storage.__setitem__(0,new))
        app=PuzzleApp.__new__(PuzzleApp)
        app.overlay_states=[]
        app.overlay_index=0
        app.overlay_target=value('12')
        app.overlay_message=value('')
        app.region_labels={}
        app.region_palette={}
        app.overlay_undo=[]
        app.overlay_redo=[]
        app.overlay_buttons=[]
        app.refresh=lambda:None
        app.save_state=lambda:None
        initial=app.overlay_snapshot()
        app.record_overlay(initial)
        app.overlay_highest=12
        app.overlay_base_labels={0:11}
        app.overlay_tested=100
        app.overlay_states=[{'cells':{1,2},'assumptions':{0:11,3:2}},
                            {'cells':{1,4},'assumptions':{0:11,3:2}}]
        app.overlay_index=1
        app.region_labels={0:11,1:12,4:12,3:2}
        app.region_palette={12:'green'}
        app.overlay_message.set('Overlay 2/2')
        expected=app.overlay_snapshot()
        app.undo_overlay()
        self.assertEqual(app.overlay_states,[])
        self.assertEqual(app.region_labels,{})
        app.redo_overlay()
        self.assertEqual(app.overlay_snapshot(),expected)
        app.undo_overlay()
        app.record_overlay(app.overlay_snapshot())
        self.assertEqual(app.overlay_redo,[])

    def test_reverse_containment_uses_completed_higher_region_without_lower_clues(self):
        grid=[['4','4','',''],['4','4','',''],['','','',''],['3','3','','']]
        _,_,states,_=find_region_overlays(grid,{},region=3)
        self.assertEqual({state['cells'] for state in states},
                         {frozenset({8,12,13}),frozenset({9,12,13})})
        self.assertTrue(all(state['reverse_containment'] for state in states))

    def test_reverse_containment_deletion_never_disconnects_shape(self):
        orientations=reverse_overlay_orientations({0,1,2,5},4)
        self.assertTrue(orientations)
        shapes=[shape for _,_,shape in orientations]
        self.assertEqual(len(shapes),len(set(shapes)))
        for shape in shapes:
            cells={r*4+c for r,c in shape}
            self.assertEqual(minimum_region_size(4,{},3,cells),3)
        self.assertNotIn(((0,0),(0,2),(1,1)),shapes)

    def test_reverse_containment_uses_higher_region_from_prior_overlay(self):
        target,children,_=continue_region_overlays(4,{12:3,13:3},4,
                                                  [{'cells':frozenset({0,1,4,5})}],region=3)
        self.assertEqual(target,3)
        self.assertEqual({state['cells'] for state in children},
                         {frozenset({8,12,13}),frozenset({9,12,13})})
        self.assertTrue(all(state['reverse_containment'] for state in children))
        self.assertTrue(all(state['assumptions'][0]==4 for state in children))

    def test_region_buttons_disable_only_identical_complete_regions(self):
        buttons=[SimpleNamespace(configure=lambda **kwargs:None) for _ in range(4)]
        status={}
        for number,button in enumerate(buttons,start=1):
            button.configure=lambda number=number,**kwargs:status.update({number:kwargs['state']})
        app=SimpleNamespace(overlay_buttons=buttons,overlay_highest=4,
                            overlay_base_labels={0:1,1:2,2:2,5:3},
                            overlay_states=[{'cells':{8,9,10,11}},{'cells':{8,9,10,12}}])
        PuzzleApp.update_overlay_buttons(app)
        self.assertEqual(status,{1:'disabled',2:'disabled',3:'normal',4:'normal'})
        app.overlay_states[1]['cells']={8,9,10,11}
        PuzzleApp.update_overlay_buttons(app)
        self.assertEqual(status[4],'disabled')
        app.overlay_states=[]
        PuzzleApp.update_overlay_buttons(app)
        self.assertTrue(all(value=='normal' for value in status.values()))
        app.overlay_busy=True
        PuzzleApp.update_overlay_buttons(app)
        self.assertTrue(all(value=='disabled' for value in status.values()))

    def test_region_buttons_use_prior_candidates_for_the_next_region(self):
        calls=[]
        app=SimpleNamespace(overlay_target=SimpleNamespace(set=lambda value:calls.append(value)),
                            save_state=lambda:None,overlay_states=[{}],overlay_highest=12,
                            continue_overlay=lambda number:calls.append(('continue',number)),
                            overlay_regions=lambda:calls.append('fresh'))
        PuzzleApp.select_overlay_region(app,13)
        self.assertEqual(calls,['13',('continue',13)])
        app.overlay_states=[]
        PuzzleApp.select_overlay_region(app,12)
        self.assertEqual(calls[-2:],['12','fresh'])

    def test_region_one_generates_single_cell_candidates(self):
        _,_,states,_=find_region_overlays([['1','',''],['','',''],['','','']],{},region=1)
        self.assertEqual(len(states),1)
        self.assertEqual(states[0]['cells'],frozenset({0}))

    def test_single_exit_is_forced_even_with_more_than_ten_region_candidates(self):
        walls={23,25,31}
        labels={cell:14 for cell in walls}
        labels.update({cell:16 for cell in (0,6,10,24,42,48)})
        board,added,limited=force_bordering_growth(7,labels,14,walls)
        self.assertEqual(board[17],16)
        self.assertEqual(added[17],16)
        self.assertTrue(limited)

    def test_wide_frontier_does_not_interrupt_other_regions_growth(self):
        walls=set(range(6,12))
        labels={cell:6 for cell in walls}
        labels.update({0:3,12:9,16:9,25:9,28:9})
        board,added,limited=force_bordering_growth(6,labels,6,walls)
        self.assertTrue(limited)
        self.assertEqual(added,{1:3,2:3})
        self.assertEqual({cell for cell,value in board.items() if value==3},{0,1,2})

    def test_bordering_growth_cascades_back_to_previously_checked_region(self):
        labels={14:5,13:5,5:5,10:5,6:5,11:7,4:2}
        original=dict(labels)
        board,added,limited=force_bordering_growth(4,labels,5,{14,13,5,10,6},max_depth=None)
        self.assertFalse(limited)
        self.assertEqual(added,{7:7,3:7,2:7,1:7,0:7,8:2,15:7})
        self.assertEqual(sum(value==7 for value in board.values()),7)
        self.assertEqual(sum(value==2 for value in board.values()),2)
        self.assertEqual(labels,original)

    def test_bordering_growth_caps_each_region_at_three_rounds(self):
        labels={14:5,13:5,5:5,10:5,6:5,11:7,4:2}
        board,added,limited=force_bordering_growth(4,labels,5,{14,13,5,10,6})
        self.assertTrue(limited)
        self.assertEqual({cell for cell,value in added.items() if value==7},{7,3,2})
        self.assertNotIn(1,added)
        self.assertEqual(labels[11],board[11])

    def test_bordering_growth_rejects_single_clue_without_room_to_grow(self):
        walls={1,2,3,5,6,7,8}
        labels={cell:7 for cell in walls}
        labels[4]=2
        with self.assertRaises(InvalidOverlay):
            force_bordering_growth(3,labels,7,walls)

    def test_bordering_growth_preserves_optional_cells(self):
        board,added,limited=force_bordering_growth(3,{0:1,1:3},1,{0})
        self.assertEqual(board,{0:1,1:3})
        self.assertEqual(added,{})
        self.assertFalse(limited)

    def test_bordering_growth_stops_before_testing_more_than_ten_candidates(self):
        labels={0:1,1:9,9:9,17:9,25:9}
        with patch('puzzle_gui.can_connect_region',side_effect=AssertionError('cutoff failed')):
            board,added,limited=force_bordering_growth(6,labels,1,{0})
        self.assertTrue(limited)
        self.assertEqual(board,labels)
        self.assertEqual(added,{})

    def test_all_isolated_pieces_are_checked_for_impossible_connections(self):
        cells={0,2,24}
        self.assertEqual(low_slack_connections(5,{cell:5 for cell in cells},5,cells),[])

    def test_more_constrained_larger_piece_is_connected_too(self):
        cells={0,2,3,23,24}
        labels={cell:9 for cell in cells}
        successors=low_slack_connections(5,labels,9,cells)
        self.assertTrue(successors)
        self.assertTrue(all(1 in region for region in successors))
        self.assertTrue(all(len(region)<=9 for region in successors))
        for region in successors:
            reached={0}
            while True:
                grown=reached|{cell for cell in region if any(
                    abs(cell//5-other//5)+abs(cell%5-other%5)==1 for other in reached)}
                if grown==reached: break
                reached=grown
            self.assertEqual(reached,set(region))
    def test_impossible_successor_is_rejected_before_forced_growth(self):
        with self.assertRaises(InvalidOverlay):
            force_overlay_neighbors(3,{0:2,8:2},2,{0,8})

    def test_candidate_contradiction_does_not_abort_overlay_search(self):
        original=force_overlay_neighbors
        calls=[0]
        def reject_one(size,labels,number,cells):
            calls[0]+=1
            if calls[0]==2:
                raise InvalidOverlay('Forced cells exceed region size')
            return original(size,labels,number,cells)
        with patch('puzzle_gui.force_overlay_neighbors',side_effect=reject_one):
            _,_,states,tested=find_region_overlays([['2','',''],['','3',''],['','','']],{})
        self.assertTrue(states)
        self.assertEqual(tested,9)
        self.assertGreater(calls[0],2)
    def test_low_slack_branches_into_four_short_connections(self):
        cells={1,2,3,17,20,21,22,23,24}
        labels={cell:12 for cell in cells}
        labels[7]=6
        successors=low_slack_connections(5,labels,12,cells)
        self.assertEqual({frozenset(set(region)-cells) for region in successors},
                         {frozenset(path) for path in ((6,11,12),(6,11,16),(8,12,13),(8,13,18))})
        self.assertTrue(all(len(region)==12 for region in successors))

    def test_high_slack_does_not_branch_and_impossible_connection_rejects(self):
        cells={0,2}
        self.assertEqual(low_slack_connections(3,{0:5,2:5},5,cells),[frozenset(cells)])
        self.assertEqual(low_slack_connections(3,{0:2,8:2},2,{0,8}),[])
    def test_bordering_region_rejects_disconnected_clues(self):
        self.assertFalse(bordering_regions_reachable(5,{11:6,13:6},7,{2,7,12,17,22}))

    def test_bordering_region_checks_shortest_path_size_budget(self):
        self.assertFalse(bordering_regions_reachable(5,{11:4,13:4},6,{12}))
        self.assertTrue(bordering_regions_reachable(5,{11:5,13:5},6,{12}))

    def test_single_neighbor_clue_does_not_require_connection(self):
        self.assertTrue(bordering_regions_reachable(3,{0:1},3,{1,3}))
    def test_overlay_forces_unavoidable_bridge_only_in_target_region(self):
        labels={0:3,2:3,6:2,8:2}
        expanded,forced=force_overlay_neighbors(3,labels,3,{0,2})
        self.assertEqual(forced,frozenset({1}))
        self.assertEqual(expanded,frozenset({0,1,2}))
        self.assertNotIn(7,expanded)
        self.assertEqual(labels,{0:3,2:3,6:2,8:2})

    def test_optional_adjacent_cell_is_not_forced(self):
        expanded,forced=force_overlay_neighbors(3,{0:5,2:5},5,{0,2})
        self.assertEqual(expanded,frozenset({0,2}))
        self.assertFalse(forced)

    def test_multiple_forced_bridge_cells_are_added(self):
        expanded,forced=force_overlay_neighbors(3,{0:5,2:5,6:5},5,{0,2,6})
        self.assertEqual(forced,frozenset({1,3}))
        self.assertEqual(expanded,frozenset({0,1,2,3,6}))
    def test_continue_overlay_branches_from_every_parent(self):
        grid=[['1','',''],['','2',''],['','','3']]
        current,base,parents,_=find_region_overlays(grid,{},region=2)
        progress=[]
        target,children,tested=continue_region_overlays(3,base,current,parents,
            lambda done,total,count:progress.append(done))
        self.assertEqual(target,3)
        self.assertEqual(len(children),15)
        self.assertEqual(progress,list(range(1,len(parents)+1)))
        self.assertEqual(len({tuple(sorted(child['assumptions'].items())) for child in children}),len(children))
        self.assertLess(len({frozenset(set(child['cells'])|{8}) for child in children}),len(children))
        self.assertGreater(tested,0)
        for child in children:
            parent=parents[child['parent_index']]
            self.assertTrue(all(child['assumptions'][cell]==2 for cell in parent['cells']))
            self.assertTrue(all(child['assumptions'].get(cell,3)==3 for cell in child['cells']))
            combined=dict(child['assumptions'])
            combined.update({cell:3 for cell in child['cells']})
            self.assertTrue(can_connect_region(3,combined,2,[cell for cell,value in combined.items() if value==2]))
        self.assertEqual(base,{0:1,4:2,8:3})
        with self.assertRaisesRegex(ValueError,'exceeds'):
            continue_region_overlays(3,base,3,children)
    def test_overlay_can_target_region_below_highest(self):
        grid = [['2','',''],['','3',''],['1','','']]
        target, labels, states, tested = find_region_overlays(grid,{},region=2)
        self.assertEqual(target,2)
        self.assertEqual(tested,9)
        self.assertTrue(states)
        self.assertEqual(len({frozenset(set(state['cells'])|{0}) for state in states}),len(states))
        self.assertTrue(all(state['minimum_size'] <= 2 for state in states))
        self.assertTrue(all(not state['cells'] & {4,6} for state in states))
        with self.assertRaisesRegex(ValueError,'Choose a region'):
            find_region_overlays(grid,{},region=4)
    def test_larger_region_keeps_preferred_color(self):
        colors = region_colors(2, {0:16, 1:7})
        self.assertEqual(colors[16], '#e7afd4')
        self.assertNotEqual(colors[7], colors[16])
    def test_overlay_uses_highest_clue_and_preserves_originals(self):
        grid = [['2','',''],['','3',''],['','','']]
        highest, labels, states, tested = find_region_overlays(grid,{})
        self.assertEqual(highest,3)
        self.assertEqual(tested,9)
        self.assertEqual(len(states),11)  # near-forced connections branch some placements
        self.assertTrue(all(0 not in state['cells'] for state in states))
        self.assertEqual(grid[0][0],'2')
        self.assertEqual(labels,{0:2,4:3})

    def test_overlay_rotations_and_reflections_are_unique(self):
        orientations = shape_orientations([0,5,10,11],5)
        self.assertEqual(len(orientations),8)
        self.assertEqual(len({shape for _,_,shape in orientations}),8)
        self.assertEqual(orientations[0][2],((0,0),(1,0),(2,0),(2,1)))

    def test_minimum_connection_matches_exhaustive_small_graphs(self):
        from itertools import combinations
        cases = [({0:3,8:3},[0,8]), ({0:3,2:3},[0,2]),
                 ({0:3,1:1,2:3},[0,2]), ({1:4,3:4,5:4},[1,3,5])]
        for labels,terminals in cases:
            number=labels[terminals[0]]
            allowed=[cell for cell in range(9) if cell not in labels or labels[cell]==number]
            expected=None
            for count in range(len(terminals),number+1):
                for cells in combinations(allowed,count):
                    cells=set(cells)
                    if not set(terminals)<=cells: continue
                    reached={terminals[0]}
                    while True:
                        extended=reached|{cell for cell in cells if any(
                            abs(cell//3-other//3)+abs(cell%3-other%3)==1 for other in reached)}
                        if extended==reached: break
                        reached=extended
                    if reached==cells:
                        expected=count
                        break
                if expected is not None: break
            self.assertEqual(minimum_region_size(3,labels,number,terminals),expected)
    def test_single_assignment_fills_known_variables_only(self):
        from fractions import Fraction
        def variable(initial):
            data = [initial]
            return SimpleNamespace(get=lambda:data[0], set=lambda value:data.__setitem__(0,value))
        app = PuzzleApp.__new__(PuzzleApp)
        app.variables = {'a':variable('9'), 'b':variable('9'), 'c':variable('9')}
        app.clear_regions = lambda:None
        app.refresh = lambda:None
        app.connectivity_message = variable('')
        app.analytical_assignments = [{'a':Fraction(1,4), 'b':Fraction(-3), 'c':None}]
        self.assertTrue(app.apply_single_assignment())
        self.assertEqual({name:value.get() for name,value in app.variables.items()},
                         {'a':'1/4', 'b':'-3', 'c':'9'})
        app.analytical_assignments *= 2
        self.assertFalse(app.apply_single_assignment())
    def test_integer_requirement_inferred_from_addition_and_subtraction(self):
        from fractions import Fraction
        self.assertEqual(inferred_integer_variables('8-b', {}), {'b'})
        self.assertEqual(inferred_integer_variables('b+c', {'b':2}), {'c'})
        self.assertEqual(inferred_integer_variables('b+c', {'b':Fraction(1,2)}), set())
        assignments, _ = analyze_clues(['b+1/2'], ['b'], 3)
        self.assertEqual({item['b'] for item in assignments}, {Fraction(1,2),Fraction(3,2),Fraction(5,2)})
        assignments, _ = analyze_clues(['2*c'], ['c'], 3)
        self.assertEqual({item['c'] for item in assignments}, {Fraction(1,2),Fraction(1),Fraction(3,2)})

    def test_unsupported_analysis_does_not_guess_values(self):
        with self.assertRaisesRegex(ValueError, 'More information'):
            analyze_clues(['a+b'], ['a','b'], 6)
        with self.assertRaisesRegex(ValueError, 'More information'):
            analyze_clues(['log_a(2)'], ['a'], 6)

    def test_square_root_clue_is_solved_without_enumeration(self):
        from fractions import Fraction
        assignments, _ = analyze_clues(['sqrt(a+2)/a'], ['a'], 17)
        self.assertIn({'a':Fraction(1,4)}, assignments)
        self.assertTrue(all(item['a'] > 0 for item in assignments))
        for assignment in assignments:
            value = evaluate('sqrt(a+2)/a', assignment)
            self.assertTrue(1 <= value <= 17 and value.denominator == 1)

    def test_full_puzzle_converges_to_one_assignment(self):
        from fractions import Fraction
        clues = ['6*c-4*b','8-b','(a^b-4)/(6*c+1)','(b+c)/(c-1)',
                 'b^2-b/c','sqrt(30+a)/c','(a+b)/(c-3*a)',
                 '(b-3*a)/(a-c)','8*a-2*b','b/(a-c)','(b+9)/sqrt(c-a)',
                 '18/(a*c+1)','c^b','(3+b^2)/sqrt(3+2*c)',
                 'b/(a^2-c^2)','sqrt(a+2)/a','a^b-12/a','2*c+c/a',
                 '4*a-5*b','c+2*a','b/(9*a-5*c)','(b^3+2*c)/(b+2*c)',
                 'b/(a-1)','(c-b)/(2*a)','b/(a-c)','(b+c)/(a-c)',
                 'log_c(a)','(c^2-b)/a','(b-1)^2','cbrt(43-a*c)/a',
                 '(b-a)/(a-c)','(11-b)','(b-2*a)/(a-c)','(c+3)/a',
                 '8*c-b/c','b^2','(2^b+1)/(a*c)']
        result, steps = analyze_clues(clues, ['a','b','c'], 17)
        self.assertEqual(result, [{'a':Fraction(1,4),'b':Fraction(-3),'c':Fraction(1,2)}])
        self.assertEqual(len(steps), len(clues))


    def test_gui_example_bounds_do_not_filter_analytical_pairs(self):
        clues = ['8-b', '(b-1)^2', '(11-b)', 'b^2', '6*c-4*b', 'b^2-b/c']
        result, steps = analyze_clues(clues, {'a': (0, 1), 'b': (-10, 10), 'c': (1, 17)}, 17)
        self.assertIn('102 partial assignments', steps[4])
        self.assertEqual(len(result), 18)
        self.assertTrue(all((assignment['a'] is None for assignment in result)))

    def test_analytical_example_keeps_correlated_partial_assignments(self):
        clues = ['6*c-4*b', '8-b', 'b^2', 'b^2-b/c', '(b-1)^2', '11-b']
        bounds = {name: (-20, 20) for name in ('a', 'b', 'c')}
        result, steps = analyze_clues(clues, bounds, 17)
        self.assertEqual([step.split(':')[0] for step in steps], ['8-b', 'b^2', '(b-1)^2', '11-b', '6*c-4*b', 'b^2-b/c'])
        self.assertIn('102 partial assignments', steps[4])
        self.assertEqual(len(result), 18)
        self.assertTrue(all((assignment['a'] is None and assignment['b'] != 1 for assignment in result)))
        for assignment in result:
            known = {name: value for name, value in assignment.items() if value is not None}
            for clue in clues:
                value = evaluate(clue, known)
                self.assertEqual(value.denominator, 1)
                self.assertTrue(1 <= value <= 17)

    def test_disabled_equations_are_preserved_but_excluded(self):
        app = PuzzleApp.__new__(PuzzleApp)
        app.SIZE = 2
        app.expressions = [['a', 'b'], ['3', '4']]
        app.disabled_cells = {1, 2}
        self.assertEqual(app.active_expressions(), [['a', ''], ['', '4']])
        self.assertEqual(app.expressions, [['a', 'b'], ['3', '4']])
        app.disabled_cells.clear()
        self.assertEqual(app.active_expressions(), app.expressions)

    def test_power_preserves_compound_base_parentheses(self):
        self.assertEqual(math_runs(inline_math('(b-1)^2')), [('power', ([('text', '(b − 1)')], [('text', '2')]))])
        self.assertEqual(math_runs(inline_math('b-1^2')), [('text', 'b − '), ('power', ([('text', '1')], [('text', '2')]))])
        self.assertEqual(evaluate('(b-1)^2', {'b': 4}), 9)

    def test_cube_root_evaluation_and_display(self):
        self.assertEqual(evaluate('cbrt(43-a*c)/a', {'a': 1, 'c': 16}), 3)
        self.assertEqual(evaluate('cbrt(-8)', {}), -2)
        self.assertEqual(evaluate('cbrt(1/8)', {}), evaluate('1/2', {}))
        self.assertEqual(evaluate('cbrt(0)', {}), 0)
        self.assertNotEqual(evaluate('cbrt(2)', {}).denominator, 1)
        self.assertEqual(fraction_parts('cbrt(43-a*c)/a'), ('∛(43 − a · c)', 'a'))
        self.assertEqual(math_runs('∛(43 − a · c)')[0][0], 'cube_root')

    def test_logarithm_with_variable_or_numeric_base(self):
        self.assertEqual(evaluate('log_c(a)', {'c': 2, 'a': 8}), 3)
        self.assertEqual(evaluate('log_2(16)+1', {}), 5)
        self.assertEqual(evaluate('log_c(a)', {'c': '1/2', 'a': 4}), -2)
        self.assertEqual(math_runs(inline_math('log_c(a)')), [('log', ([('text', 'c')], [('text', 'a')]))])
        for values in ({'c': 1, 'a': 8}, {'c': 0, 'a': 8}, {'c': 2, 'a': 0}, {'c': -2, 'a': 8}):
            with self.assertRaises(ValueError):
                evaluate('log_c(a)', values)

    def test_fraction_inside_subtraction_is_stacked(self):
        runs = math_runs(inline_math('a^b-12/a'))
        self.assertEqual(runs, [('power', ([('text', 'a')], [('text', 'b')])), ('text', ' − '), ('fraction', ([('text', '12')], [('text', 'a')]))])
        texts, lines = ([], [])
        font = SimpleNamespace(measure=lambda value: len(value) * 8, cget=lambda key: 12, metrics=lambda key: 18)
        canvas = SimpleNamespace(create_text=lambda *args, **kw: texts.append((args, kw['text'])), create_line=lambda *args, **kw: lines.append(args))
        draw_math(canvas, 50, 30, inline_math('a^b-12/a'), font)
        self.assertLess(texts[3][0][1], texts[4][0][1])
        self.assertEqual(len(lines), 1)

    def test_radical_draws_bar_and_removes_outer_parentheses(self):
        text, lines = ([], [])
        font = SimpleNamespace(measure=lambda value: len(value) * 8, cget=lambda key: 12, metrics=lambda key: 18)
        canvas = SimpleNamespace(create_text=lambda *args, **kwargs: text.append(kwargs['text']), create_line=lambda *args, **kwargs: lines.append(args))
        draw_math(canvas, 50, 30, '√(3 + 2c)', font)
        self.assertEqual(text, ['3 + 2c'])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][-1], lines[0][-3])
        self.assertEqual(math_runs('√(a + √(b))'), [('root', [('text', 'a + '), ('root', [('text', 'b')])])])

    def test_square_roots(self):
        self.assertEqual(evaluate('(b+9)/sqrt(c-a)', {'a': 1, 'b': 3, 'c': 5}), 6)
        self.assertEqual(evaluate('sqrt(1/4)', {}), evaluate('1/2', {}))
        self.assertEqual(evaluate('sqrt(2)*sqrt(2)', {}), 2)
        self.assertNotEqual(evaluate('sqrt(2)', {}).denominator, 1)
        self.assertEqual(fraction_parts('(b+9)/sqrt(c-a)'), ('b + 9', '√(c − a)'))
        with self.assertRaises(ValueError):
            evaluate('sqrt(-1)', {})
        with self.assertRaises(ZeroDivisionError):
            evaluate('1/sqrt(0)', {})

    def test_compound_fraction_notation_preserves_denominator(self):
        self.assertEqual(fraction_parts('(x-y)/(y-c)'), ('x − y', 'y − c'))
        self.assertEqual(fraction_parts('(a^b-b)/(6*c+1)'), ('〖a¦b〗 − b', '6c + 1'))
        self.assertEqual(fraction_parts('(a^2-b)/(6*c+1)'), ('〖a¦2〗 − b', '6c + 1'))
        self.assertEqual(fraction_parts('b/a'), ('b', 'a'))
        self.assertIsNone(fraction_parts('a/b + 1'))
        self.assertIsNone(fraction_parts('a//b'))

    def test_display_toggle_preserves_colors_and_number_only_cells(self):
        app = PuzzleApp.__new__(PuzzleApp)

        def variable(initial):
            data = [initial]
            return SimpleNamespace(get=lambda: data[0], set=lambda value: data.__setitem__(0, value))
        app.SIZE = 2
        app.expressions = [['a', ''], ['a/2', 'unknown']]
        app.variables = {'a': variable('2')}
        app.selected = (0, 0)
        app.show_values = variable(False)
        app.detail, app.status = (variable(''), variable(''))
        app.region_labels = {0: 2, 1: 2}
        app.region_palette = {2: '#123456'}
        app.board = SimpleNamespace(draw=lambda: None)
        app.display_button = SimpleNamespace(configure=lambda **kw: None)
        app.save_state = lambda: None
        app.refresh()
        before = app.board.cells[:]
        self.assertEqual([cell[2] for cell in before], ['a', '2', 'a/2', 'unknown'])
        app.toggle_display()
        self.assertEqual([cell[2] for cell in app.board.cells], ['2', '2', '1', 'unknown'])
        self.assertEqual([cell[3] for cell in before], [cell[3] for cell in app.board.cells])
        app.toggle_display()
        self.assertEqual(app.board.cells, before)

    def test_forced_regions_from_blocked_paths(self):
        grid = [['', '6', '', '3', ''], ['', '', '5', '', ''], ['4', '', '', '', '5'], ['', '1', '', '6', ''], ['4', '', '', '', '2']]
        labels, added = grow_forced_regions(grid, {}, use_containment=False)
        self.assertEqual(labels[15], 4)
        for cell in (6, 11, 12):
            self.assertEqual(labels[cell], 6)
        self.assertEqual(labels[8], 5)
        self.assertNotIn(13, labels)
        self.assertNotIn(17, labels)
        self.assertGreater(added, 0)
        self.assertEqual(grid[1][1], '')

    def test_containment_forces_screenshot_cell_and_restarts_growth(self):
        grid = [['', '6', '', '3', ''], ['', '', '5', '', ''], ['4', '', '', '', '5'], ['', '1', '', '6', ''], ['4', '', '', '', '2']]
        ordinary, _ = grow_forced_regions(grid, {}, use_containment=False)
        labels, added = grow_forced_regions(grid, {})
        self.assertNotIn(9, ordinary)
        self.assertEqual(labels[9], 5)
        self.assertEqual(labels[13], 6)
        self.assertEqual(labels[19], 5)
        self.assertEqual(added, 12)
        self.assertEqual(len(labels), 21)

    def test_shape_equivalence_allows_rotations_and_reflections(self):
        original = {0, 5, 10, 11}
        reflected = {1, 6, 10, 11}
        rotated = {0, 1, 2, 5}
        self.assertEqual(canonical_shape(original, 5), canonical_shape(reflected, 5))
        self.assertEqual(canonical_shape(original, 5), canonical_shape(rotated, 5))

    def test_containment_rejects_incompatible_shapes(self):
        with self.assertRaisesRegex(ValueError, 'shape containment'):
            filter_containment({4: [frozenset({0, 1, 3, 4})], 3: [frozenset({6, 7, 8})]}, 3)

    def test_ambiguous_growth_stays_blank(self):
        labels, added = grow_forced_regions([['', '', ''], ['', '2', ''], ['', '', '']], {})
        self.assertEqual(labels, {4: 2})
        self.assertEqual(added, 0)

    def test_color_conflicts_are_resolved(self):
        labels = {0: 4, 1: 13, 2: 22, 3: 6}
        colors = region_colors(2, labels)
        for first, second in ((4, 13), (4, 22), (13, 6), (22, 6)):
            self.assertNotEqual(colors[first], colors[second])
        self.assertEqual(colors[22], '#efa5a5')
        self.assertNotEqual(colors[4], colors[22])
        self.assertEqual(colors[6], '#a9d8af')

    def test_connectivity_counts_reject_before_search(self):
        with patch('puzzle_gui.can_connect_region') as search:
            passed, message = check_grid_connectivity([['1', '1'], ['', '']], {})
            self.assertFalse(passed)
            self.assertIn('at most 1', message)
            search.assert_not_called()

    def test_connectivity_blank_bridge_and_obstacle(self):
        self.assertTrue(check_grid_connectivity([['3', '', '3'], ['', '', ''], ['', '', '']], {})[0])
        self.assertFalse(check_grid_connectivity([['3', '1', '3'], ['', '', ''], ['', '', '']], {})[0])

    def test_connectivity_checks_total_region_size(self):
        self.assertFalse(can_connect_region(3, {0: 3, 2: 3, 6: 3}, 3, [0, 2, 6]))
        self.assertTrue(can_connect_region(3, {1: 4, 3: 4, 5: 4}, 4, [1, 3, 5]))

    def test_connectivity_candidate_evaluation_and_boundaries(self):
        grid = [['a', 'a'], ['', '']]
        self.assertTrue(check_grid_connectivity(grid, {'a': 2})[0])
        for candidate in (0, -1, '1/2', 3):
            self.assertFalse(check_grid_connectivity(grid, {'a': candidate})[0])

    def test_candidate_range_format(self):
        self.assertEqual(format_candidates({1, 2, 3, 5, 7, 8}), '1–3, 5, 7–8')
        self.assertEqual(format_candidates(set()), 'None')

    def test_bounds_are_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'grid.json'
            state = {'size': 1, 'expressions': [['a']], 'variables': {'a': '2'}, 'bounds': {'a': {'min': '-2', 'max': '12'}}}
            write_state(path, state)
            self.assertEqual(read_state(path), state)

    def test_grid_hit_testing_with_left_alignment(self):
        canvas = GridCanvas.__new__(GridCanvas)
        canvas.size = 5
        canvas.bounds = (4, 30, 250)
        selected = []
        canvas.select_cell = lambda x, y: selected.append((x, y))
        canvas.click(SimpleNamespace(x=253, y=279))
        canvas.click(SimpleNamespace(x=400, y=100))
        self.assertEqual(selected, [(4, 4)])
if __name__ == '__main__':
    unittest.main()
