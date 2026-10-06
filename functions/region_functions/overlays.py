"""Overlay placement, forced growth, continuation, and completion branches."""

from collections import deque
from copy import deepcopy
from heapq import heapify, heappop, heappush
from functions.equations_functions import evaluate
from .cancellation import check_region_abort
from .connectivity import max_region_size, minimum_region_size, can_connect_region
from .shapes import shape_orientations, reverse_overlay_orientations


class InvalidOverlay(ValueError):
    """A candidate contradiction, rather than a failure of the whole search."""


def force_overlay_neighbors(size, labels, number, cells):
    """Force multiply-adjacent blanks that no size-bounded completion can avoid."""
    terminals = {cell for cell,value in labels.items() if value == number} | set(cells)
    added = set()
    while True:
        if not can_connect_region(size,labels,number,terminals):
            raise InvalidOverlay(f"Region {number} cannot connect within its size.")
        touches = {}
        for cell in terminals:
            row,column = divmod(cell,size)
            for r,c in ((row-1,column),(row+1,column),(row,column-1),(row,column+1)):
                neighbor = r*size+c
                if 0 <= r < size and 0 <= c < size and neighbor not in labels and neighbor not in terminals:
                    touches[neighbor] = touches.get(neighbor,0)+1
        forced = set()
        for cell,count in touches.items():
            if count < 2: continue
            blocked = dict(labels)
            blocked[cell] = -1
            if not can_connect_region(size,blocked,number,terminals):
                forced.add(cell)
        if not forced:
            return frozenset(set(cells)|added),frozenset(added)
        terminals.update(forced)
        added.update(forced)
        if len(terminals) > number:
            raise InvalidOverlay(f"Forced cells exceed region {number}'s size.")


def bordering_regions_reachable(size, labels, target, cells):
    """Cheap necessary check for neighboring regions, without simulating growth."""
    combined = dict(labels)
    combined.update({cell:target for cell in cells})
    target_cells = {cell for cell,value in combined.items() if value == target}
    bordering = set()
    def neighbors(cell):
        row,column = divmod(cell,size)
        return [r*size+c for r,c in ((row-1,column),(row+1,column),(row,column-1),(row,column+1))
                if 0 <= r < size and 0 <= c < size]
    for cell in target_cells:
        for other in neighbors(cell):
            value = combined.get(other)
            if value is not None and value != target:
                bordering.add(value)
    for number in bordering:
        required = {cell for cell,value in combined.items() if value == number}
        if len(required) < 2:
            continue
        # Root each shortest-path search at a required clue. A path exceeding
        # N-1 edges cannot fit into any connected N-cell region.
        for start in required:
            distances = {start:0}
            heap = [(0,start)]
            while heap:
                distance,cell = heappop(heap)
                if distance != distances[cell] or distance >= number-1:
                    continue
                for other in neighbors(cell):
                    if other in combined and combined[other] != number:
                        continue
                    candidate = distance+1
                    if candidate < distances.get(other,number):
                        distances[other] = candidate
                        heappush(heap,(candidate,other))
            if not required <= distances.keys():
                return False
    return True


def force_bordering_growth(size, labels, target, cells, candidate_limit=10, max_depth=3):
    """Propagate growth with bounded rounds per region and bounded frontiers."""
    combined = dict(labels)
    combined.update({cell:target for cell in cells})
    added = {}
    limited = False

    def neighbors(cell):
        row,column = divmod(cell,size)
        return [r*size+c for r,c in ((row-1,column),(row+1,column),
                                    (row,column-1),(row,column+1))
                if 0 <= r < size and 0 <= c < size]

    def can_complete(number, required, blocked=None):
        # Connectivity alone does not catch a single clue trapped in an area
        # too small to fill its region. Count its entire reachable area too.
        board = combined if blocked is None else {**combined,blocked:-1}
        reached = {min(required)}
        queue = list(reached)
        while queue:
            for other in neighbors(queue.pop()):
                if other not in reached and board.get(other,number) == number:
                    reached.add(other)
                    queue.append(other)
        return (required <= reached and len(reached) >= number
                and can_connect_region(size,board,number,required))

    pending = deque(sorted({combined[other]
                            for cell,value in combined.items() if value == target
                            for other in neighbors(cell)
                            if other in combined and combined[other] != target}))
    queued = set(pending)
    rounds = {}
    while pending:
        number = pending.popleft()
        check_region_abort()
        queued.remove(number)
        required = {cell for cell,value in combined.items() if value == number}
        if len(required) < number:
            if max_depth is not None and rounds.get(number,0) >= max_depth:
                limited = True
                continue
            rounds[number] = rounds.get(number,0)+1
        frontier = {other for cell in required for other in neighbors(cell)
                    if other not in combined}
        # An incomplete connected piece must have an exit even when the
        # entire region has too many candidates for the expensive check.
        remaining = set(required)
        forced_exit = None
        while remaining:
            piece = {remaining.pop()}
            stack = list(piece)
            while stack:
                for other in neighbors(stack.pop()):
                    if other in remaining:
                        remaining.remove(other)
                        piece.add(other)
                        stack.append(other)
            if len(piece) >= number:
                continue
            exits = {other for cell in piece for other in neighbors(cell)
                     if other not in combined}
            if not exits:
                raise InvalidOverlay(f"Region {number} has an isolated incomplete piece.")
            if len(exits) == 1:
                forced_exit = next(iter(exits))
                break
        if len(required) > number:
            raise InvalidOverlay(f"Region {number} exceeds its required size.")
        if forced_exit is not None:
            combined[forced_exit] = number
            added[forced_exit] = number
            affected = {number} | {combined[other] for other in neighbors(forced_exit)
                                   if other in combined}
            for value in sorted(affected):
                if value not in queued:
                    pending.append(value)
                    queued.add(value)
            continue
        if len(required) < number and len(frontier) > candidate_limit:
            limited = True
            continue
        if not can_complete(number,required):
            raise InvalidOverlay(f"Region {number} cannot grow to its required size.")
        if len(required) == number:
            continue
        for cell in sorted(frontier):
            if can_complete(number,required,blocked=cell):
                continue
            combined[cell] = number
            added[cell] = number
            # Revisit this region and regions touching its new cell. This
            # includes regions checked earlier whose available space changed.
            affected = {number} | {combined[other] for other in neighbors(cell)
                                   if other in combined}
            for value in sorted(affected):
                if value not in queued:
                    pending.append(value)
                    queued.add(value)
            break
    return combined,added,limited


def low_slack_connections(size, labels, target, cells):
    """Check all isolated pieces and branch recursively on tight connections."""
    terminals = {cell for cell,value in labels.items() if value == target} | set(cells)
    def neighbors(cell):
        row,column = divmod(cell,size)
        return [r*size+c for r,c in ((row-1,column),(row+1,column),(row,column-1),(row,column+1))
                if 0 <= r < size and 0 <= c < size
                and (r*size+c not in labels or labels[r*size+c] == target)]
    remaining,components = set(terminals),[]
    while remaining:
        part = {remaining.pop()}
        queue = list(part)
        while queue:
            for other in neighbors(queue.pop()):
                if other in remaining:
                    remaining.remove(other)
                    part.add(other)
                    queue.append(other)
        components.append(part)
    if len(components) < 2:
        return [frozenset(cells)]
    budget = target-len(terminals)
    constrained = []
    for source in components:
        destinations = terminals-source
        # Reverse Dijkstra counts blank cells needed, not existing region cells.
        distance = {cell:0 for cell in destinations}
        heap = [(0,cell) for cell in destinations]
        heapify(heap)
        while heap:
            cost,cell = heappop(heap)
            if cost != distance[cell]: continue
            for other in neighbors(cell):
                candidate = cost+(0 if cell in terminals else 1)
                if candidate < distance.get(other,target+1):
                    distance[other] = candidate
                    heappush(heap,(candidate,other))
        shortest = min((distance.get(cell,target+1) for cell in source),default=target+1)
        slack = budget-shortest
        if slack < 0:
            return []
        if slack <= 1:
            constrained.append((slack,len(source),min(source),source,destinations,distance))
    if not constrained:
        return [frozenset(cells)]
    # Branch on the tightest piece first, then reconsider every piece in each
    # successor. Each path joins components, so this recursion always progresses.
    _,_,_,source,destinations,distance = min(constrained,key=lambda item:item[:3])
    successors = set()
    stack = [(start,frozenset([start]),frozenset()) for start in source]
    while stack:
        cell,visited,added = stack.pop()
        check_region_abort()
        if cell in destinations:
            connected = frozenset(set(cells)|set(added))
            successors.update(low_slack_connections(size,labels,target,connected))
            continue
        for other in neighbors(cell):
            if other in visited or other in source: continue
            next_added = added if other in terminals else added|{other}
            if len(next_added)+distance.get(other,target+1) <= budget:
                stack.append((other,visited|{other},next_added))
    return sorted(successors,key=lambda region:tuple(sorted(region)))


def find_region_overlays(expressions, variables, progress=None, region=None):
    size = len(expressions)
    labels = {r*size+c:int(evaluate(expression,variables))
              for r,row in enumerate(expressions) for c,expression in enumerate(row) if expression.strip()}
    limit = max_region_size(size)
    for row in expressions:
        for expression in row:
            if expression.strip():
                value = evaluate(expression,variables)
                if value.denominator != 1 or not 1 <= value <= limit:
                    raise ValueError("All included clues must evaluate to valid region sizes.")
    if not labels: raise ValueError("No included clues to overlay.")
    highest = max(labels.values()) if region is None else region
    if type(highest) is not int or not 1 <= highest <= limit:
        raise ValueError(f"Choose a region from 1 to {limit}.")
    source = [cell for cell,value in labels.items() if value == highest-1]
    higher = {cell for cell,value in labels.items() if value == highest+1}
    reverse = len(higher) == highest+1
    if reverse and minimum_region_size(size,labels,highest+1,higher) is None:
        raise ValueError(f"The completed region {highest+1} is disconnected.")
    if highest > 1 and not source and not reverse:
        raise ValueError(f"No {highest-1} cells are available to overlay onto region {highest}.")
    anchors = {cell for cell,value in labels.items() if value == highest}
    tested, survivors = 0, []
    occupied_sets = set()
    if reverse:
        orientations = reverse_overlay_orientations(higher,size)
    else:
        orientations = [(0,False,((0,0),))] if highest == 1 else shape_orientations(source,size)
    for rotation,reflected,shape in orientations:
        height,width = max(r for r,c in shape)+1,max(c for r,c in shape)+1
        for top in range(size-height+1):
            for left in range(size-width+1):
                check_region_abort()
                tested += 1
                cells = frozenset((r+top)*size+c+left for r,c in shape)
                if reverse and not anchors <= cells: continue
                if any(cell in labels and labels[cell] != highest for cell in cells): continue
                terminals = anchors | cells
                minimum = minimum_region_size(size,labels,highest,terminals)
                if minimum is not None:
                    try:
                        expanded,forced = force_overlay_neighbors(size,labels,highest,cells)
                    except InvalidOverlay:
                        if progress: progress(tested,len(survivors))
                        continue
                    if not bordering_regions_reachable(size,labels,highest,expanded):
                        if progress: progress(tested,len(survivors))
                        continue
                    for successor in low_slack_connections(size,labels,highest,expanded):
                        connection_cells = frozenset(set(successor)-set(expanded))
                        try:
                            successor,post_connection_forced = force_overlay_neighbors(size,labels,highest,successor)
                        except InvalidOverlay:
                            continue
                        if not bordering_regions_reachable(size,labels,highest,successor): continue
                        try:
                            combined,neighbor_growth,growth_limited = force_bordering_growth(
                                size,labels,highest,successor)
                        except InvalidOverlay:
                            continue
                        successor = frozenset(set(successor) | {cell for cell,value in neighbor_growth.items()
                                                               if value == highest})
                        completed_minimum = minimum_region_size(size,combined,highest,anchors|set(successor))
                        if completed_minimum is None: continue
                        occupied = frozenset(anchors|set(successor))
                        if occupied in occupied_sets: continue
                        occupied_sets.add(occupied)
                        survivors.append({'cells':successor,'overlay_cells':cells,
                                          'forced_cells':forced|post_connection_forced,
                                          'connection_cells':connection_cells,
                                          'assumptions':combined,'neighbor_growth':neighbor_growth,
                                          'growth_limited':growth_limited,
                                          'reverse_containment':reverse,
                                          'row':top,'column':left,'rotation':rotation,
                                          'reflected':reflected,'minimum_size':completed_minimum})
                if progress: progress(tested,len(survivors))
    return highest,labels,survivors,tested


def compare_incomplete_regions(size, base_labels, current, states, progress=None):
    """Intersect reverse-containment placements separately in each branch."""
    survivors,seen = [],set()
    for index,state in enumerate(states):
        board = dict(state.get('assumptions',base_labels))
        board.update({cell:current for cell in state['cells']})
        added = {}
        try:
            changed = True
            while changed:
                changed = False
                largest = max(board.values())
                for number in range(largest-1,0,-1):
                    required = {cell for cell,value in board.items() if value == number}
                    higher = {cell for cell,value in board.items() if value == number+1}
                    if not required or not higher:
                        continue
                    if len(required) > number or len(higher) > number+1:
                        raise InvalidOverlay("A region exceeds its required size.")
                    if minimum_region_size(size,board,number+1,higher) is None:
                        raise InvalidOverlay(f"Region {number+1} cannot connect within its size.")
                    complete = len(higher) == number+1
                    if complete:
                        orientations = reverse_overlay_orientations(higher,size)
                    elif len(higher) == number:
                        # With just one unknown higher-region cell, check its
                        # actual possible positions too. Otherwise a lower
                        # placement might imply a higher cell on another clue.
                        frontier = set()
                        for cell in higher:
                            row,column = divmod(cell,size)
                            for r,c in ((row-1,column),(row+1,column),(row,column-1),(row,column+1)):
                                if 0 <= r < size and 0 <= c < size and r*size+c not in board:
                                    frontier.add(r*size+c)
                        orientations = []
                        for extra in frontier:
                            completion = higher | {extra}
                            if minimum_region_size(size,board,number+1,completion) is None: continue
                            orientations.extend(reverse_overlay_orientations(completion,size))
                        complete = True  # Each tested shape now has exactly K cells.
                    else:
                        # The omitted cell might be unknown, so also retain
                        # every known cell. Incomplete remnants need not be
                        # connected yet: unknown cells may connect them later.
                        orientations = shape_orientations(higher,size)
                        for omitted in higher:
                            remainder = higher-{omitted}
                            if remainder:
                                orientations.extend(shape_orientations(remainder,size))
                            else:
                                orientations.append((0,False,()))
                    placements = set()
                    checked_shapes = set()
                    for _,_,shape in orientations:
                        if shape in checked_shapes: continue
                        checked_shapes.add(shape)
                        if not shape:
                            placements.add(frozenset(required))
                            continue
                        height,width = max(r for r,c in shape)+1,max(c for r,c in shape)+1
                        for top in range(size-height+1):
                            for left in range(size-width+1):
                                check_region_abort()
                                cells = frozenset((r+top)*size+c+left for r,c in shape)
                                if complete and not required <= cells: continue
                                if any(cell in board and board[cell] != number for cell in cells): continue
                                cells = cells | required
                                if minimum_region_size(size,board,number,cells) is None: continue
                                if not bordering_regions_reachable(size,board,number,cells): continue
                                placements.add(cells)
                    if not placements:
                        raise InvalidOverlay(f"No containment placement for region {number}.")
                    forced = set.intersection(*(set(cells) for cells in placements))-required
                    if forced:
                        board.update({cell:number for cell in forced})
                        added.update({cell:number for cell in forced})
                        changed = True
                        break  # New knowledge restarts from the largest incomplete region.
        except InvalidOverlay:
            if progress: progress(index+1,len(states),len(survivors))
            continue
        key = (tuple(sorted(board.items())),tuple(state.get('ancestor_regions',[])))
        if key not in seen:
            seen.add(key)
            result = deepcopy(state)
            result['assumptions'] = board
            result['cells'] = frozenset(cell for cell,value in board.items() if value == current)
            result['comparison_growth'] = added
            survivors.append(result)
        if progress: progress(index+1,len(states),len(survivors))
    return survivors


def attempt_region_completions(size, base_labels, current, states, progress=None):
    """Complete one-cell gaps and carry the completed shape through higher ranks."""
    def neighbors(cell):
        row,column = divmod(cell,size)
        return [r*size+c for r,c in ((row-1,column),(row+1,column),(row,column-1),(row,column+1))
                if 0 <= r < size and 0 <= c < size]

    def finish(board, number, required):
        if len(required) > number: return []
        additions = [set()] if len(required) == number else [
            {cell} for cell in sorted({other for anchor in required for other in neighbors(anchor)
                                      if other not in board and other not in required})]
        results = []
        for extra in additions:
            cells = required | extra
            if len(cells) != number or minimum_region_size(size,board,number,cells) is None: continue
            if not bordering_regions_reachable(size,board,number,cells): continue
            result = dict(board)
            result.update({cell:number for cell in cells})
            results.append(result)
        return results

    def mirror(board, number, largest):
        if number >= largest: return [board]
        target = number+1
        anchors = {cell for cell,value in board.items() if value == target}
        if not anchors: return [board]
        source = {cell for cell,value in board.items() if value == number}
        successors = {}
        for _,_,shape in shape_orientations(source,size):
            height,width = max(r for r,c in shape)+1,max(c for r,c in shape)+1
            for top in range(size-height+1):
                for left in range(size-width+1):
                    check_region_abort()
                    cells = {(r+top)*size+c+left for r,c in shape}
                    if any(cell in board and board[cell] != target for cell in cells): continue
                    for result in finish(board,target,cells | anchors):
                        successors[tuple(sorted(result.items()))] = result
        results = {}
        for successor in successors.values():
            for result in mirror(successor,target,largest):
                results[tuple(sorted(result.items()))] = result
        return list(results.values())

    survivors,seen = [],set()
    for index,state in enumerate(states):
        original = dict(state.get('assumptions',base_labels))
        original.update({cell:current for cell in state['cells']})
        largest = max(original.values())
        branches = [original]
        for number in range(1,largest+1):
            successors = {}
            for board in branches:
                required = {cell for cell,value in board.items() if value == number}
                results = [board]
                if required and len(required) == number-1:
                    results = [result for completed in finish(board,number,required)
                               for result in mirror(completed,number,largest)]
                for result in results:
                    successors[tuple(sorted(result.items()))] = result
            branches = list(successors.values())
            if not branches: break
        for board in branches:
            key = (tuple(sorted(board.items())),tuple(state.get('ancestor_regions',[])))
            if key in seen: continue
            seen.add(key)
            result = deepcopy(state)
            result['assumptions'] = board
            result['cells'] = frozenset(cell for cell,value in board.items() if value == current)
            result['completion_growth'] = {cell:value for cell,value in board.items() if cell not in original}
            survivors.append(result)
        if progress: progress(index+1,len(states),len(survivors))
    return survivors


def continue_region_overlays(size, base_labels, current, states, progress=None, region=None):
    target = current+1 if region is None else region
    if target > max_region_size(size):
        raise ValueError("The next region exceeds max region size.")
    survivors, tested = [], 0
    occupied_sets = set()
    for parent_index,parent in enumerate(states):
        check_region_abort()
        assumed = dict(parent.get('assumptions',base_labels))
        assumed.update({cell:current for cell in parent['cells']})
        expressions = [[str(assumed[r*size+c]) if r*size+c in assumed else ''
                        for c in range(size)] for r in range(size)]
        _,_,children,count = find_region_overlays(expressions,{},region=target)
        tested += count
        for child in children:
            combined = dict(child.get('assumptions',assumed))
            combined.update({cell:target for cell in child['cells']})
            # New cells also become obstacles for the assumed ancestor regions.
            ancestors = set(parent.get('ancestor_regions', [])) | {current}
            if any(not can_connect_region(size,combined,number,
                    [cell for cell,value in combined.items() if value==number]) for number in ancestors):
                continue
            # Equal target shapes can inherit different earlier regions.
            # Dropping one loses a branch that may be needed by a later step.
            branch = (tuple(sorted(combined.items())),tuple(sorted(ancestors)))
            if branch in occupied_sets: continue
            occupied_sets.add(branch)
            child.update(assumptions=combined, parent_index=parent_index,
                         ancestor_regions=sorted(ancestors))
            survivors.append(child)
        if progress: progress(parent_index+1,len(states),len(survivors))
    return target,survivors,tested
