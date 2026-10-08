"""Provisional greedy clue deductions with cascading rollback."""
import copy

from functions.arc_constraints import apply_arc_deductions
from functions.clue_analysis import incorporate_analysis, analysis_timing_summary
from functions.greedy_analysis import analyze_clue_greedy
from functions.incremental_analysis import analyze_clue_with_sanity
from puzzle_gui import (allowed_arc_configurations, determine_regions, ordered_clues,
                        save_accepted_states, prune_saved_states)


def verified_grid(state):
    return all(region.verify(state) for region in set(determine_regions(state)[0].values()))


def determined_grid(state):
    """Distinguish confirmed blank cells from still-undecided no-arc cells."""
    return all(len(allowed_arc_configurations(state, r, c)) == 1
               for r in range(state['rows']) for c in range(state['columns']))


def placed_arcs(state):
    return {(r, c, cell['arc']) for r, row in enumerate(state['cells'])
            for c, cell in enumerate(row) if cell['arc'] is not None}


class GreedySolveSession:
    def __init__(self, state, order, weights, search_options, log, checkpoint):
        self.state = copy.deepcopy(state)
        self.order, self.weights, self.options = order, weights, search_options
        self.log, self.checkpoint = log, checkpoint
        self.greedy = True
        self.history = []
        self.pending = []
        self.pass_number = 0
        self.force_next = False

    def start_pass(self):
        self.pass_number += 1
        self.pass_start_arcs = placed_arcs(self.state)
        self.pending = list(self.order) if self.order is not None else ordered_clues(self.state, self.weights)

    def rollback(self, reason):
        self.greedy = False
        if not self.history:
            return False
        self.state, self.pending, self.pass_start_arcs, self.pass_number = self.history.pop()
        self.force_next = True
        r, c = self.pending[0]
        self.log(f'{reason} Restoring the state before greedy clue '
                 f'{self.state["cells"][r][c]["number"]} at r{r + 1}c{c + 1}; continuing normally.')
        self.checkpoint(self.state)
        return True

    def run(self):
        self.start_pass()
        while True:
            if not self.pending:
                self.log(f'Pass {self.pass_number} complete.')
                if verified_grid(self.state):
                    self.log('Puzzle verified complete.')
                    return self.state
                complete = determined_grid(self.state)
                stalled = not placed_arcs(self.state) - self.pass_start_arcs
                if complete or stalled:
                    reason = 'Completed grid failed verification.' if complete else 'Pass placed no new arcs.'
                    if self.rollback(reason):
                        continue
                    if complete:
                        raise ValueError('The completed grid is invalid; no greedy deductions remain to reverse.')
                    self.log('Stopped: no new arcs placed in the last pass.')
                    return self.state
                self.start_pass()
                continue

            if self.order is None and not self.force_next:
                remaining = set(self.pending)
                self.pending = [cell for cell in ordered_clues(self.state, self.weights) if cell in remaining]
            self.force_next = False
            selected = self.pending.pop(0)
            r, c = selected
            clue = self.state['cells'][r][c]['number']
            while True:
                greedy_attempt = self.greedy
                mode = 'greedy' if greedy_attempt else 'normal'
                self.log(f'Pass {self.pass_number}: starting {mode} analysis of clue {clue} at r{r + 1}c{c + 1}')
                engine = analyze_clue_greedy if greedy_attempt else analyze_clue_with_sanity
                failure = None
                try:
                    result = engine(self.state, selected, **self.options)
                    if result.cancelled:
                        raise KeyboardInterrupt()
                    incomplete = (result.limit_reached or result.worklist_limit_reached or result.branch_limit_reached)
                    self.log(f'Clue {clue} at r{r + 1}c{c + 1} ({mode}): '
                             f'{result.elapsed_seconds:.2f} seconds; {len(result.accepted_states)} accepted states; '
                             f'{analysis_timing_summary(result)}')
                    if result.sanity_pruned:
                        self.log(f'Sanity checks rejected {result.sanity_pruned} accepted states '
                                 f'for clue {clue} at r{r + 1}c{c + 1}.')
                    if not result.accepted_states or greedy_attempt and incomplete:
                        failure = f'{mode.capitalize()} analysis of clue {clue} at r{r + 1}c{c + 1} failed.'
                        if not greedy_attempt and incomplete:
                            self.log('Normal search stopped inconclusively; preserving the checkpoint.')
                            return self.state
                    else:
                        updated = copy.deepcopy(self.state)
                        provisional = copy.copy(result)
                        # Explicit opt-in: use the heuristic as a provisional
                        # hypothesis. Full snapshots undo every resulting rule.
                        provisional.heuristic = False
                        incorporate_analysis(updated, provisional)
                        save_accepted_states(updated, selected, provisional)
                        if updated.get('arc_implications'):
                            apply_arc_deductions(updated)
                        prune_saved_states(updated)
                except ValueError as exc:
                    failure = f'{mode.capitalize()} analysis of clue {clue} contradicted the grid: {exc}.'

                if failure:
                    if greedy_attempt:
                        self.log(f'{failure} Retrying this clue normally; future searches will be normal.')
                        self.greedy = False
                        continue
                    if self.rollback(failure):
                        break
                    raise ValueError(f'{failure} No greedy deductions remain to reverse.')

                if greedy_attempt:
                    self.history.append((copy.deepcopy(self.state), [selected] + list(self.pending),
                                         set(self.pass_start_arcs), self.pass_number))
                self.state = updated
                self.checkpoint(self.state)
                if determined_grid(self.state) and not verified_grid(self.state):
                    if not self.rollback('Completed grid failed verification.'):
                        raise ValueError('The completed grid is invalid; no greedy deductions remain to reverse.')
                break
