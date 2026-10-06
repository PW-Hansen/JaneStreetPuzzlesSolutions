"""Interactive expression grid. Run with: python puzzle_gui.py"""

import ast
import argparse
import json
import operator
import re
import tkinter as tk
import threading
from copy import deepcopy
from datetime import datetime
from time import perf_counter
from collections import deque
from heapq import heapify, heappop, heappush
from decimal import Decimal, localcontext
from queue import Queue, Empty
from fractions import Fraction
from math import isqrt
from pathlib import Path
from tkinter import font as tkfont, messagebox, simpledialog, ttk


DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"
MIN_CELL_SIZE = 40


def max_region_size(grid_size):
    """Largest n with triangular number n(n + 1)/2 <= grid area."""
    return (isqrt(8 * grid_size * grid_size + 1) - 1) // 2


def variable_name(index):
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("a") + remainder) + name
    return name




def clue_variables(expression, names):
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in names:
                used.add(node.id)
            elif node.id.startswith("log_") and node.id[4:] in names:
                used.add(node.id[4:])
            elif node.id not in ("sqrt", "cbrt") and not re.fullmatch(r"log_\d+", node.id):
                raise ValueError(f"Unknown variable: {node.id}")
    return used


def solve_rational_clue(expression, unknown, known, limit):
    """Solve a univariate rational expression for each permitted cell integer.

    Return None for forms requiring the bounded per-clue fallback.
    """
    tree = ast.parse(expression.replace('^', '**'), mode='eval').body
    def square_root(node):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'sqrt' and len(node.args) == 1 and not node.keywords)
    if square_root(tree) or (isinstance(tree, ast.BinOp) and isinstance(tree.op, ast.Div)
                             and (square_root(tree.left) or square_root(tree.right))):
        solutions = set()
        for target in range(1, limit+1):
            if square_root(tree):
                equation = f'({ast.unparse(tree.args[0])})-({target}^2)'
            elif square_root(tree.left):
                equation = f'({ast.unparse(tree.left.args[0])})-({target}^2)*({ast.unparse(tree.right)})^2'
            else:
                equation = f'({ast.unparse(tree.left)})^2-({target}^2)*({ast.unparse(tree.right.args[0])})'
            roots = solve_rational_clue(f'({equation})+1', unknown, known, 1)
            if roots is None:
                return None
            for root in roots:
                try:
                    if evaluate(expression, dict(known, **{unknown:root})) == target:
                        solutions.add(root)
                except (ValueError, ArithmeticError):
                    pass
        return solutions
    def add(a, b, sign=1):
        result = dict(a)
        for degree, coefficient in b.items():
            result[degree] = result.get(degree, 0) + sign*coefficient
        return {degree: coefficient for degree, coefficient in result.items() if coefficient}
    def multiply(a, b):
        result = {}
        for i, x in a.items():
            for j, y in b.items():
                if i+j > 40:
                    raise ValueError("Polynomial degree too large")
                result[i+j] = result.get(i+j, 0)+x*y
        return {degree: coefficient for degree, coefficient in result.items() if coefficient}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return {0: Fraction(str(node.value))}, {0: Fraction(1)}
        if isinstance(node, ast.Name):
            if node.id == unknown:
                return {1: Fraction(1)}, {0: Fraction(1)}
            return {0: Fraction(known[node.id])}, {0: Fraction(1)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            numerator, denominator = visit(node.operand)
            return ({degree: -value for degree, value in numerator.items()}
                    if isinstance(node.op, ast.USub) else numerator), denominator
        if not isinstance(node, ast.BinOp):
            raise ValueError("Unsupported symbolic form")
        if isinstance(node.op, ast.Pow):
            exponent = evaluate(ast.unparse(node.right), known)
            if exponent.denominator != 1 or abs(exponent) > 20:
                raise ValueError("Unsupported symbolic power")
            numerator, denominator = visit(node.left)
            if exponent < 0:
                numerator, denominator = denominator, numerator
            result_n, result_d = {0: Fraction(1)}, {0: Fraction(1)}
            for _ in range(abs(int(exponent))):
                result_n, result_d = multiply(result_n, numerator), multiply(result_d, denominator)
            return result_n, result_d
        a, b = visit(node.left)
        c, d = visit(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            return add(multiply(a, d), multiply(c, b), -1 if isinstance(node.op, ast.Sub) else 1), multiply(b, d)
        if isinstance(node.op, ast.Mult):
            return multiply(a, c), multiply(b, d)
        if isinstance(node.op, ast.Div):
            return multiply(a, d), multiply(b, c)
        raise ValueError("Unsupported symbolic operator")
    try:
        numerator, denominator = visit(ast.parse(expression.replace('^', '**'), mode='eval').body)
        solutions = set()
        for target in range(1, limit+1):
            polynomial = add(numerator, {degree: target*value for degree, value in denominator.items()}, -1)
            degree = max(polynomial, default=-1)
            if degree < 0 or degree > 2:
                return None
            if degree == 0:
                continue
            if degree == 1:
                solutions.add(-polynomial.get(0, 0)/polynomial[1])
            else:
                a, b, c = polynomial[2], polynomial.get(1, 0), polynomial.get(0, 0)
                discriminant = b*b-4*a*c
                if discriminant < 0:
                    continue
                n, d = isqrt(discriminant.numerator), isqrt(discriminant.denominator)
                if n*n == discriminant.numerator and d*d == discriminant.denominator:
                    root = Fraction(n, d)
                    solutions.update(((-b-root)/(2*a), (-b+root)/(2*a)))
        return solutions
    except (ValueError, KeyError, ArithmeticError):
        return None


def inferred_integer_variables(expression, known):
    """An integral sum/difference with an integral operand forces the other operand integral."""
    inferred = set()
    tree = ast.parse(expression.replace('^', '**'), mode='eval').body
    def integer(node):
        try:
            return evaluate(ast.unparse(node), known).denominator == 1
        except (ValueError, ArithmeticError):
            return False
    def require_integer(node):
        if isinstance(node, ast.Name):
            inferred.add(node.id)
        elif isinstance(node, ast.UnaryOp):
            require_integer(node.operand)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            if integer(node.left): require_integer(node.right)
            if integer(node.right): require_integer(node.left)
    require_integer(tree)
    return inferred


def analyze_clues(expressions, names, limit):
    """Solve included clues in variable-count order, without bounded enumeration."""
    names = list(names)
    clues = sorted([(expression, clue_variables(expression, names)) for expression in expressions],
                   key=lambda clue: len(clue[1]))
    assignments = [{name: None for name in names}]
    notes = []
    pending = list(clues)
    while pending and assignments:
        ready = None
        for i, (clue, used) in enumerate(pending):
            solvable = True
            for assignment in assignments:
                unknowns = [name for name in used if assignment[name] is None]
                if len(unknowns) > 1:
                    solvable = False
                    break
                if unknowns:
                    known = {name:value for name,value in assignment.items() if value is not None}
                    if solve_rational_clue(clue, unknowns[0], known, limit) is None:
                        solvable = False
                        break
            if solvable:
                ready = i
                break
        if ready is None:
            raise ValueError('More information is needed to solve these coupled clues analytically: ' +
                             ', '.join(expression for expression, _ in pending))
        expression, used = pending.pop(ready)
        survivors = {}
        for assignment in assignments:
            unknowns = [name for name in used if assignment[name] is None]
            unknown = unknowns[0] if unknowns else None
            known = {name:value for name,value in assignment.items() if value is not None}
            integer_required = inferred_integer_variables(expression, known)
            candidates = [None] if unknown is None else solve_rational_clue(expression, unknown, known, limit)
            if candidates is None:
                raise ValueError(f'Cannot yet solve {expression} analytically; no brute-force fallback is used.')
            for candidate in sorted(candidates) if unknown is not None else candidates:
                updated = dict(assignment)
                if unknown is not None:
                    if unknown in integer_required and Fraction(candidate).denominator != 1:
                        continue
                    updated[unknown] = Fraction(candidate)
                try:
                    value = evaluate(expression, {name:value for name,value in updated.items() if value is not None})
                    if value.denominator != 1 or not 1 <= value <= limit:
                        continue
                except (ValueError, ArithmeticError):
                    continue
                survivors[tuple(updated.items())] = updated
        assignments = list(survivors.values())
        inferred = sorted(set().union(*(inferred_integer_variables(expression, {
            name:value for name,value in assignment.items() if value is not None}) for assignment in assignments)))
        notes.append(f'{expression}: {len(assignments)} partial assignments (solved analytically)' +
                     (f"; integer rule: {', '.join(inferred)}" if inferred else ''))
    return assignments, notes


def format_candidates(values):
    """Compact consecutive candidate values into ranges."""
    numbers = sorted(values)
    if not numbers:
        return "None"
    if any(Fraction(value).denominator != 1 for value in numbers):
        return ", ".join(str(value) for value in numbers)
    parts = []
    start = previous = numbers[0]
    for value in numbers[1:] + [None]:
        if value is not None and value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = value
    return ", ".join(parts)


def minimum_region_size(size, labels, number, terminals):
    """Exact graph Steiner-tree size using terminal-subset dynamic programming."""
    terminals = sorted(set(terminals))
    if not terminals:
        return 0
    if len(terminals) > number:
        return None
    allowed = {cell for cell in range(size*size) if cell not in labels or labels[cell] == number}
    if not set(terminals) <= allowed:
        return None
    neighbors = {cell: [r*size+c for r,c in ((cell//size-1,cell%size),
                  (cell//size+1,cell%size),(cell//size,cell%size-1),(cell//size,cell%size+1))
                  if 0 <= r < size and 0 <= c < size and r*size+c in allowed] for cell in allowed}
    mandatory = set(terminals)
    remaining = set(mandatory)
    components = []
    while remaining:
        component = {remaining.pop()}
        queue = list(component)
        while queue:
            cell = queue.pop()
            for other in neighbors[cell]:
                if other in remaining:
                    remaining.remove(other)
                    component.add(other)
                    queue.append(other)
        components.append(component)
    if len(components) == 1:
        return len(terminals)
    if len(terminals) == number:
        return None  # No spare cells remain to connect disconnected pieces.
    if len(components) == 2:
        # All mandatory cells already belong to two connected pieces. Only
        # the minimum number of blank bridge cells remains to be determined.
        distance = {cell:0 for cell in components[0]}
        queue = deque(components[0])
        while queue:
            cell = queue.popleft()
            if cell in components[1]:
                total = len(terminals)+distance[cell]
                return total if total <= number else None
            for other in neighbors[cell]:
                cost = 0 if other in mandatory else 1
                candidate = distance[cell]+cost
                if candidate < distance.get(other,number+1):
                    distance[other] = candidate
                    if cost: queue.append(other)
                    else: queue.appendleft(other)
        return None
    distances = []
    for terminal in terminals:
        if terminal not in allowed:
            return None
        distance = {terminal:0}
        queue = deque([terminal])
        while queue:
            cell = queue.popleft()
            for other in neighbors[cell]:
                if other not in distance:
                    distance[other] = distance[cell]+1
                    queue.append(other)
        if any(distance.get(other, number) >= number for other in terminals):
            return None
        distances.append(distance)
    # Half the terminal metric MST is a lower bound on a Steiner tree.
    reached, mst = {0}, 0
    while len(reached) < len(terminals):
        distance, new = min((distances[i][terminals[j]],j) for i in reached
                            for j in range(len(terminals)) if j not in reached)
        mst += distance
        reached.add(new)
    if (mst+1)//2+1 > number:
        return None
    budget = number-1
    count = 1 << len(terminals)
    dp = [{} for _ in range(count)]
    for mask in range(1,count):
        if mask & (mask-1) == 0:
            index = mask.bit_length()-1
            dp[mask] = {cell:cost for cell,cost in distances[index].items() if cost <= budget}
            continue
        best = {}
        sub = (mask-1)&mask
        while sub:
            other = mask^sub
            if sub < other:
                first, second = dp[sub],dp[other]
                if len(first) > len(second): first,second = second,first
                for cell,cost in first.items():
                    combined = cost+second.get(cell,number)
                    if combined <= budget and combined < best.get(cell,number):
                        best[cell] = combined
            sub = (sub-1)&mask
        heap = [(cost,cell) for cell,cost in best.items()]
        heapify(heap)
        while heap:
            cost,cell = heappop(heap)
            if cost != best[cell] or cost >= budget: continue
            for neighbor in neighbors[cell]:
                if cost+1 < best.get(neighbor,number):
                    best[neighbor] = cost+1
                    heappush(heap,(cost+1,neighbor))
        dp[mask] = best
    return min(dp[-1].values())+1 if dp[-1] else None


def can_connect_region(size, labels, number, terminals):
    return minimum_region_size(size, labels, number, terminals) is not None


def shape_orientations(cells, size):
    points = [divmod(cell,size) for cell in cells]
    unique = set()
    orientations = []
    for rotation in range(4):
        for reflected in (False,True):
            transformed = []
            for row,column in points:
                if reflected: column = -column
                for _ in range(rotation): row,column = column,-row
                transformed.append((row,column))
            top,left = min(r for r,c in transformed),min(c for r,c in transformed)
            shape = tuple(sorted((r-top,c-left) for r,c in transformed))
            if shape not in unique:
                unique.add(shape)
                orientations.append((rotation,reflected,shape))
    return orientations


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


def reverse_overlay_orientations(cells, size):
    """Unique connected shapes obtained by deleting one cell, with D4 symmetry."""
    number = len(cells)-1
    orientations,seen = [],set()
    for removed in sorted(cells):
        reduced = set(cells)-{removed}
        if not reduced or minimum_region_size(size,{},number,reduced) is None:
            continue
        for rotation,reflected,shape in shape_orientations(reduced,size):
            if shape not in seen:
                seen.add(shape)
                orientations.append((rotation,reflected,shape))
    return orientations


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




def check_grid_connectivity(expressions, variables):
    size = len(expressions)
    limit = max_region_size(size)
    labels, groups = {}, {}
    for row, cells in enumerate(expressions):
        for column, expression in enumerate(cells):
            if not expression.strip():
                continue
            try:
                value = evaluate(expression, variables)
                if value.denominator != 1 or not 1 <= value <= limit:
                    return False, f"Rejected: row {row+1}, column {column+1} must evaluate to an integer from 1 to {limit}."
            except (ValueError, SyntaxError, ArithmeticError, RecursionError) as error:
                return False, f"Rejected: row {row+1}, column {column+1}: {error}"
            number = int(value)
            cell = row * size + column
            labels[cell] = number
            groups.setdefault(number, []).append(cell)
    # Count all fixed cells before attempting any connectivity search.
    for number, terminals in sorted(groups.items()):
        if len(terminals) > number:
            return False, f"Rejected: {len(terminals)} cells evaluate to {number}; at most {number} are allowed."
    for number, terminals in sorted(groups.items()):
        if not can_connect_region(size, labels, number, terminals):
            return False, f"Rejected: the {number} cells cannot be connected in a region of at most {number} cells."
    return True, "Connectivity check passed. Each value can connect through blank cells within its region size."




def region_completions(size, labels, number):
    """All connected regions of exactly number cells containing its fixed cells."""
    terminals = frozenset(cell for cell, value in labels.items() if value == number)
    if not terminals or len(terminals) > number:
        return []
    allowed = {cell for cell in range(size * size) if cell not in labels or labels[cell] == number}
    neighbors = {cell: {r*size+c for r, c in
                        ((cell//size-1, cell%size), (cell//size+1, cell%size),
                         (cell//size, cell%size-1), (cell//size, cell%size+1))
                        if 0 <= r < size and 0 <= c < size and r*size+c in allowed}
                 for cell in allowed}
    seen, completed = set(), []
    stack = [frozenset([min(terminals)])]
    while stack:
        region = stack.pop()
        if region in seen:
            continue
        seen.add(region)
        if len(terminals - region) > number - len(region):
            continue
        if len(region) == number:
            if terminals <= region:
                completed.append(region)
            continue
        frontier = set().union(*(neighbors[cell] for cell in region)) - region
        for cell in frontier:
            stack.append(region | {cell})
    return completed


def canonical_shape(cells, size):
    """Translation-independent shape, allowing all rotations and reflections."""
    points = [divmod(cell, size) for cell in cells]
    shapes = []
    for swap in (False, True):
        for row_sign in (-1, 1):
            for column_sign in (-1, 1):
                transformed = [(row_sign*(c if swap else r), column_sign*(r if swap else c))
                               for r, c in points]
                min_row = min(r for r, c in transformed)
                min_column = min(c for r, c in transformed)
                shapes.append(tuple(sorted((r-min_row, c-min_column) for r, c in transformed)))
    return min(shapes)


def filter_containment(options, size):
    """Enforce adjacent-size shape support, processing largest sizes first."""
    shapes = {region: canonical_shape(region, size)
              for regions in options.values() for region in regions}
    contained = {region: {canonical_shape(region - {cell}, size) for cell in region}
                 for number, regions in options.items() if number > 1 for region in regions}
    while True:
        changed = False
        for number in sorted(options, reverse=True):
            if number - 1 not in options:
                continue
            bigger, smaller = options[number], options[number-1]
            supported_big, supported_small = set(), set()
            for big in bigger:
                for small in smaller:
                    if big.isdisjoint(small) and shapes[small] in contained[big]:
                        supported_big.add(big)
                        supported_small.add(small)
            if not supported_big or not supported_small:
                raise ValueError(f"Regions {number} and {number-1} cannot satisfy shape containment.")
            new_big = [region for region in bigger if region in supported_big]
            new_small = [region for region in smaller if region in supported_small]
            changed |= len(new_big) != len(bigger) or len(new_small) != len(smaller)
            options[number], options[number-1] = new_big, new_small
        if not changed:
            return options


def grow_forced_regions(expressions, variables, use_containment=True):
    passed, message = check_grid_connectivity(expressions, variables)
    if not passed:
        raise ValueError(message)
    size = len(expressions)
    labels = {r*size+c: int(evaluate(expression, variables))
              for r, row in enumerate(expressions) for c, expression in enumerate(row)
              if expression.strip()}
    original = dict(labels)
    while True:
        forced = {}
        candidates = {}
        for number in sorted(set(labels.values())):
            options = region_completions(size, labels, number)
            candidates[number] = options
            if not options:
                raise ValueError(f"Region {number} has no connected completion of size {number}.")
            mandatory = set.intersection(*(set(option) for option in options))
            for cell in mandatory - labels.keys():
                if cell in forced and forced[cell] != number:
                    raise ValueError("Different regions require the same blank cell.")
                forced[cell] = number
        if not forced:
            if not use_containment:
                return labels, len(labels) - len(original)
            candidates = filter_containment(candidates, size)
            for number in sorted(candidates, reverse=True):
                mandatory = set.intersection(*(set(option) for option in candidates[number]))
                for cell in mandatory - labels.keys():
                    if cell in forced and forced[cell] != number:
                        raise ValueError("Different regions require the same blank cell.")
                    forced[cell] = number
            if not forced:
                return labels, len(labels) - len(original)
            # Restart ordinary connected-region deductions before another
            # largest-to-smallest containment pass.
        labels.update(forced)


def region_colors(size, labels):
    """Greedy coloring of the region adjacency graph, with preferred colors."""
    palette = ['#f6d797', '#cab5ec', '#9cd7ed', '#efa5a5', '#efc394', '#a9d8af',
               '#e7afd4', '#b8c9ef', '#d9d79f']
    adjacency = {number: set() for number in labels.values()}
    for cell, number in labels.items():
        row, column = divmod(cell, size)
        for neighbor in (cell+1 if column+1 < size else -1,
                         cell+size if row+1 < size else -1):
            if neighbor in labels and labels[neighbor] != number:
                adjacency[number].add(labels[neighbor])
                adjacency[labels[neighbor]].add(number)
    colors = {}
    for number in sorted(adjacency, reverse=True):
        used = {colors[neighbor] for neighbor in adjacency[number] if neighbor in colors}
        preferred = palette[(number-1) % len(palette)]
        choices = [preferred] + palette
        color = next((color for color in choices if color not in used), None)
        if color is None:
            # A distinct fallback also handles grids with many touching regions.
            color = f"#{(number * 2654435761) & 0xffffff:06x}"
            while color in used:
                color = f"#{(int(color[1:], 16)+1) & 0xffffff:06x}"
        colors[number] = color
    return colors


def grid_name(value):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
            or value.upper() in {"CON", "PRN", "AUX", "NUL",
                                 *(f"COM{i}" for i in range(1, 10)),
                                 *(f"LPT{i}" for i in range(1, 10))}):
        raise argparse.ArgumentTypeError("Use a name of up to 64 letters, digits, hyphens, or underscores.")
    return value


def read_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Expected saved grid settings")
    expressions = state.get("expressions")
    size = state.get("size", len(expressions) if isinstance(expressions, list) else 0)
    if (type(size) is not int or size < 1
            or not isinstance(expressions, list) or len(expressions) != size
            or any(not isinstance(row, list) or len(row) != size
                   or any(not isinstance(cell, str) for cell in row) for row in expressions)):
        raise ValueError("Expected a square grid of expressions")
    variables = state.get("variables", {})
    if (not isinstance(variables, dict)
            or any(not isinstance(name, str) or not re.fullmatch(r"[a-z]+", name)
                   or not isinstance(value, str) for name, value in variables.items())
            or type(state.get("show_values", False)) is not bool):
        raise ValueError("Invalid saved settings")
    state["size"] = size
    disabled = state.get("disabled_cells", [])
    if (not isinstance(disabled, list) or any(type(cell) is not int or not 0 <= cell < size*size for cell in disabled)):
        raise ValueError("Invalid disabled cells")
    return state


def encode_overlay(value):
    """JSON-safe representation retaining cell keys, sets, and tuples."""
    if isinstance(value,dict):
        return {'type':'dict','items':[[encode_overlay(key),encode_overlay(item)] for key,item in value.items()]}
    if isinstance(value,(set,frozenset,tuple)):
        return {'type':type(value).__name__,'items':[encode_overlay(item) for item in value]}
    if isinstance(value,list): return [encode_overlay(item) for item in value]
    return value


def decode_overlay(value):
    if isinstance(value,list): return [decode_overlay(item) for item in value]
    if isinstance(value,dict):
        kind,items = value['type'],value['items']
        if kind == 'dict': return {decode_overlay(key):decode_overlay(item) for key,item in items}
        constructors = {'set':set,'frozenset':frozenset,'tuple':tuple}
        return constructors[kind](decode_overlay(item) for item in items)
    return value


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def migrate_example():
    """Preserve the previous single grid as the named example grid."""
    old_path = Path(__file__).resolve().with_name("grid_state.json")
    new_path = DATA_DIRECTORY / "example.json"
    if old_path.exists() and not new_path.exists():
        write_state(new_path, read_state(old_path))


def prepare_grid(root, name):
    migrate_example()
    path = DATA_DIRECTORY / f"{name}.json"
    if not path.exists():
        size = simpledialog.askinteger("New grid", f"Size for '{name}' (number of rows and columns):",
                                       parent=root, minvalue=1)
        if size is None:
            return None
        state = {"size": size, "expressions": [[""] * size for _ in range(size)],
                 "show_values": False}
    else:
        state = read_state(path)
    if "variables" not in state:
        count = simpledialog.askinteger("Grid variables", f"Number of variables for '{name}':",
                                        parent=root, minvalue=0)
        if count is None:
            return None
        state["variables"] = {variable_name(i): "1" for i in range(count)}
        write_state(path, state)
    # Validate before opening an editable grid so a damaged save isn't overwritten.
    read_state(path)
    return path


def display_expression(expression):
    """Use compact mathematical notation without changing the stored input."""
    expression = re.sub(r"\s*(?:\^|\*\*)\s*(-?\d+)",
                        lambda match: match[1].translate(str.maketrans(
                            "0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")), expression)
    expression = re.sub(r"(?<=\d)\s*\*\s*(?=[a-z])", "", expression)
    return expression.replace("sqrt(", "√(").replace("cbrt(", "∛(").replace("**", "^").replace("-", "−").replace("*", "·")


def fraction_parts(expression):
    """Split a top-level quotient without changing its mathematical meaning."""
    try:
        node = ast.parse(expression.replace("^", "**"), mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return inline_math(ast.unparse(node.left)), inline_math(ast.unparse(node.right))
    return None


def inline_math(expression):
    """Replace divisions anywhere in an expression with layout markers."""
    try:
        tree = ast.parse(expression.replace("^", "**"), mode="eval")
    except (ValueError, SyntaxError):
        return display_expression(expression)
    replacements = {}
    class Fractions(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.func, ast.Name) and re.fullmatch(r"log_([a-z]+|\d+)", node.func.id)
                    and len(node.args) == 1 and not node.keywords):
                name = f"__fraction_{len(replacements)}__"
                replacements[name] = "〔" + node.func.id[4:] + "¦" + ast.unparse(node.args[0]) + "〕"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            return node
        def visit_BinOp(self, node):
            node = self.generic_visit(node)
            if isinstance(node.op, ast.Div):
                name = f"__fraction_{len(replacements)}__"
                replacements[name] = "⟦" + ast.unparse(node.left) + "¦" + ast.unparse(node.right) + "⟧"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            if isinstance(node.op, ast.Pow):
                name = f"__fraction_{len(replacements)}__"
                base = ast.unparse(node.left)
                if isinstance(node.left, (ast.BinOp, ast.UnaryOp)) or (
                        isinstance(node.left, ast.Name) and node.left.id in replacements):
                    base = "(" + base + ")"
                replacements[name] = "〖" + base + "¦" + ast.unparse(node.right) + "〗"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            return node
    text = ast.unparse(Fractions().visit(tree))
    for name, replacement in reversed(list(replacements.items())):
        text = text.replace(name, replacement)
    return display_expression(text)


def math_runs(text):
    """Separate radical arguments from surrounding text, including nested roots."""
    runs = []
    while text:
        root_start, cube_start, fraction_start, power_start, log_start = text.find("√("), text.find("∛("), text.find("⟦"), text.find("〖"), text.find("〔")
        candidates = [start for start in (root_start, cube_start, fraction_start, power_start, log_start) if start >= 0]
        start = min(candidates) if candidates else -1
        if start < 0:
            runs.append(("text", text))
            break
        is_fraction = start == fraction_start
        is_power = start == power_start
        is_log = start == log_start
        paired = is_fraction or is_power or is_log
        opening, closing = ("⟦", "⟧") if is_fraction else ("〖", "〗") if is_power else ("〔", "〕") if is_log else ("(", ")")
        depth, end = 1, start + (1 if paired else 2)
        separator = None
        while end < len(text) and depth:
            if paired and text[end] == "¦" and depth == 1:
                separator = end
            depth += (text[end] == opening) - (text[end] == closing)
            end += 1
        if depth:
            runs.append(("text", text))
            break
        if start:
            runs.append(("text", text[:start]))
        if paired:
            runs.append(("fraction" if is_fraction else "power" if is_power else "log", (math_runs(text[start+1:separator]), math_runs(text[separator+1:end-1]))))
        else:
            runs.append(("cube_root" if start == cube_start else "root", math_runs(text[start+2:end-1])))
        text = text[end:]
    return runs


def math_width(runs, font):
    return sum(font.measure(value) if kind == "text" else
               max(math_width(part, font) for part in value) + 6 if kind == "fraction" else
               math_width(value[0], font) + 0.85 * math_width(value[1], font) if kind == "power" else
               font.measure("log ") + 0.85 * math_width(value[0], font) + math_width(value[1], font) if kind == "log" else
               font.measure("3")*0.55 + font.measure("√") + 4 + math_width(value, font) if kind == "cube_root" else
               font.measure("√") + 4 + math_width(value, font) for kind, value in runs)


def draw_math(canvas, center_x, center_y, text, font):
    runs = math_runs(text)
    font_spec = ("Times New Roman", font.cget("size"), "italic")
    height = font.metrics("linespace")
    def draw(parts, left, y, scale=1):
        font_spec = ("Times New Roman", max(6, round(font.cget("size")*scale)), "italic")
        local_height = height * scale
        for kind, value in parts:
            if kind == "text":
                canvas.create_text(left, y, text=value, anchor="w", font=font_spec, fill="#252525")
                left += font.measure(value) * scale
            elif kind == "power":
                base_width = math_width(value[0], font) * scale
                draw(value[0], left, y, scale)
                draw(value[1], left+base_width, y-local_height*0.42, scale*0.85)
                left += base_width + math_width(value[1], font)*scale*0.85
            elif kind == "log":
                canvas.create_text(left, y, text="log", anchor="w",
                                   font=("Times New Roman", max(6, round(font.cget("size")*scale))), fill="#252525")
                left += font.measure("log")*scale
                draw(value[0], left, y+local_height*0.3, scale*0.85)
                left += math_width(value[0], font)*scale*0.85 + font.measure(" ")*scale
                draw(value[1], left, y, scale)
                left += math_width(value[1], font)*scale
            elif kind == "fraction":
                width = (max(math_width(part, font) for part in value) + 6)*scale
                for part, offset in ((value[0], -local_height*0.8), (value[1], local_height*0.8)):
                    draw(part, left+(width-math_width(part, font)*scale)/2, y+offset, scale)
                canvas.create_line(left, y, left+width, y, fill="#252525", width=1)
                left += width
            else:
                if kind == "cube_root":
                    canvas.create_text(left, y-local_height*0.48, text="3", anchor="w",
                                       font=("Times New Roman", max(6, round(font.cget("size")*scale*0.65))), fill="#252525")
                    left += font.measure("3")*scale*0.55
                root_width = font.measure("√")*scale
                argument_width = math_width(value, font)*scale
                # Draw the radical and vinculum as one continuous stroke.
                bar_y = y - local_height * 0.46
                canvas.create_line(left, y, left+root_width*0.28, y-local_height*0.08,
                                   left+root_width*0.52, y+local_height*0.35,
                                   left+root_width, bar_y,
                                   left+root_width+argument_width+4, bar_y,
                                   fill="#252525", width=1)
                draw(value, left+root_width+2, y, scale)
                left += root_width+argument_width+4
        return left
    draw(runs, center_x - math_width(runs, font)/2, center_y)


class GridCanvas(tk.Canvas):
    """A square paper-style board with clickable cells."""

    def __init__(self, parent, select, size):
        minimum = size * MIN_CELL_SIZE + 8
        super().__init__(parent, bg="#f4f6fa", highlightthickness=0,
                         width=minimum, height=max(360, minimum))
        self.select_cell = select
        self.size = size
        self.cells = []
        self.selection = (0, 0)
        self.bounds = (0, 0, 0)
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Button-1>", self.click)
        self.configure(cursor="hand2")

    def click(self, event):
        left, top, side = self.bounds
        if side and left <= event.x < left + side and top <= event.y < top + side:
            self.select_cell(int((event.x - left) * self.size / side),
                             int((event.y - top) * self.size / side))

    def draw(self):
        self.delete("all")
        side = max(0, min(self.winfo_width(), self.winfo_height()) - 8)
        if side < 5:
            return
        left = 4
        top = (self.winfo_height() - side) / 2
        self.bounds = (left, top, side)
        cell = side / self.size
        self.create_rectangle(left, top, left + side, top + side, fill="white", outline="")
        font_size = max(12, min(24, int(cell * 0.27)))
        for x, y, text, color in self.cells:
            x0, y0 = left + x * cell, top + y * cell
            if color != "#ffffff":
                self.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill=color, outline="")
            cx, cy = x0 + cell / 2, y0 + cell / 2
            fraction = fraction_parts(text)
            if fraction:
                fraction_font = tkfont.Font(family="Times New Roman", size=font_size, slant="italic")
                while max(math_width(math_runs(part), fraction_font) for part in fraction) > cell - 16 and fraction_font.cget("size") > 8:
                    fraction_font.configure(size=fraction_font.cget("size") - 1)
                offset_size = fraction_font.metrics("linespace") * 0.8
                for part, offset in ((fraction[0], -offset_size),
                                     (fraction[1], offset_size)):
                    draw_math(self, cx, cy + offset, part, fraction_font)
                half = (max(math_width(math_runs(part), fraction_font) for part in fraction) + 6) / 2
                self.create_line(cx - half, cy, cx + half, cy, fill="#333333")
            else:
                rendered = inline_math(text)
                math_font = tkfont.Font(family="Times New Roman", size=font_size, slant="italic")
                while math_width(math_runs(rendered), math_font) > cell - 12 and math_font.cget("size") > 8:
                    math_font.configure(size=math_font.cget("size") - 1)
                draw_math(self, cx, cy, rendered, math_font)
        for index in range(1, self.size):
            offset = index * cell
            self.create_line(left + offset, top, left + offset, top + side,
                             fill="#c5c5c5", dash=(1, 3))
            self.create_line(left, top + offset, left + side, top + offset,
                             fill="#c5c5c5", dash=(1, 3))
        self.create_rectangle(left, top, left + side, top + side, outline="#666666", width=1)
        x, y = self.selection
        self.create_rectangle(left + x * cell + 2, top + y * cell + 2,
                              left + (x + 1) * cell - 2, top + (y + 1) * cell - 2,
                              outline="#8ba5bf", width=1)


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def evaluate(expression, variables):
    """Evaluate arithmetic only, keeping rational results exact."""
    if len(expression) > 200:
        raise ValueError("Expression is too long")
    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown variable: {node.id}")
            return Fraction(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "cbrt" and len(node.args) == 1 and not node.keywords):
            value = visit(node.args[0])
            if isinstance(value, Fraction):
                def integer_cube_root(number):
                    low, high = 0, 1 << ((number.bit_length()+2)//3)
                    while low < high:
                        middle = (low+high+1)//2
                        if middle**3 <= number:
                            low = middle
                        else:
                            high = middle-1
                    return low
                numerator = integer_cube_root(abs(value.numerator))
                denominator = integer_cube_root(value.denominator)
                if numerator**3 == abs(value.numerator) and denominator**3 == value.denominator:
                    return Fraction(numerator if value >= 0 else -numerator, denominator)
            with localcontext() as context:
                context.prec = 80
                decimal = Decimal(value.numerator)/Decimal(value.denominator) if isinstance(value, Fraction) else value
                if not decimal:
                    return Fraction(0)
                root = (abs(decimal).ln()/Decimal(3)).exp()
                return root if decimal > 0 else -root
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and re.fullmatch(r"log_([a-z]+|\d+)", node.func.id)
                and len(node.args) == 1 and not node.keywords):
            base_name = node.func.id[4:]
            if base_name.isdigit():
                base = Fraction(int(base_name))
            elif base_name in variables:
                base = Fraction(variables[base_name])
            else:
                raise ValueError(f"Unknown logarithm base variable: {base_name}")
            argument = visit(node.args[0])
            if base <= 0 or base == 1 or argument <= 0:
                raise ValueError("Logarithms require a positive argument and a positive base different from 1")
            with localcontext() as context:
                context.prec = 80
                base_decimal = Decimal(base.numerator)/Decimal(base.denominator)
                argument_decimal = Decimal(argument.numerator)/Decimal(argument.denominator) if isinstance(argument, Fraction) else argument
                return argument_decimal.ln()/base_decimal.ln()
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords):
            value = visit(node.args[0])
            if value < 0:
                raise ValueError("sqrt requires a nonnegative argument")
            if isinstance(value, Fraction):
                numerator, denominator = isqrt(value.numerator), isqrt(value.denominator)
                if numerator*numerator == value.numerator and denominator*denominator == value.denominator:
                    return Fraction(numerator, denominator)
            with localcontext() as context:
                context.prec = 80
                decimal = (Decimal(value.numerator)/Decimal(value.denominator)
                           if isinstance(value, Fraction) else value)
                return decimal.sqrt()
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if right != int(right) or abs(right) > 20:
                    raise ValueError("Powers require an integer exponent from -20 to 20")
                right = int(right)
            if isinstance(left, Decimal) or isinstance(right, Decimal):
                with localcontext() as context:
                    context.prec = 80
                    left = Decimal(left.numerator)/Decimal(left.denominator) if isinstance(left, Fraction) else left
                    right = Decimal(right.numerator)/Decimal(right.denominator) if isinstance(right, Fraction) else right
                    result = OPERATORS[type(node.op)](left, right)
            else:
                result = OPERATORS[type(node.op)](left, right)
            if isinstance(result, Decimal):
                return result
            result = Fraction(result)
            if result.numerator.bit_length() > 4096 or result.denominator.bit_length() > 4096:
                raise ValueError("Result is too large")
            return result
        raise ValueError("Use numbers, defined variables, parentheses, and arithmetic operators only")

    with localcontext() as context:
        context.prec = 80
        result = visit(tree.body)
        if isinstance(result, Decimal):
            nearest = result.to_integral_value()
            if abs(result - nearest) < Decimal("1e-60"):
                return Fraction(int(nearest))
            return Fraction(result)
        return result


class PuzzleApp:
    def __init__(self, root, name, state_path):
        self.root = root
        self.STATE_PATH = state_path
        self.SIZE = read_state(state_path)["size"]
        root.title(f"Jane Street Puzzle — {name}")
        root.geometry("760x720")
        root.minsize(620, 620)
        root.configure(bg="#f4f6fa")
        self.expressions = [["" for _ in range(self.SIZE)] for _ in range(self.SIZE)]
        self.disabled_cells = set()
        self.selected = (0, 0)
        self.show_values = tk.BooleanVar(value=False)
        self.formula = tk.StringVar()
        self.status = tk.StringVar()
        self.detail = tk.StringVar()
        self.variables = {}
        self.valid_values = {}
        self.search_revision = 0
        self.analytical_assignments = None
        self.analysis_steps = []
        self.search_message = tk.StringVar(value="Analyze included clues to find valid values.")
        self.connectivity_message = tk.StringVar()
        self.region_labels = {}
        self.region_palette = {}
        self.overlay_message = tk.StringVar()
        self.overlay_target = tk.StringVar(value="Highest")
        self.region_elapsed = tk.StringVar()
        self.overlay_states = []
        self.overlay_index = 0
        self.overlay_undo = []
        self.overlay_redo = []
        self.storage_error = tk.StringVar()
        self.load_state()
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6fa")
        style.configure("TLabel", background="#f4f6fa", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=7)

        layout = ttk.Frame(root, padding=24)
        layout.pack(fill="both", expand=True)
        layout.columnconfigure(0, weight=1)
        layout.rowconfigure(1, weight=1)
        main = ttk.Frame(layout)
        main.grid(row=0, column=0, sticky="ew")
        ttk.Label(main, text=f"{name} · {self.SIZE}×{self.SIZE}", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        region = ttk.Frame(main)
        region.pack(anchor="w", pady=(0, 8))
        ttk.Label(region, text="max region size =").pack(side="left", padx=(0, 6))
        self.max_region_value = tk.StringVar(value=str(max_region_size(self.SIZE)))
        ttk.Label(region, textvariable=self.max_region_value,
                  font=("Segoe UI", 10)).pack(side="left")
        self.selection_label = ttk.Label(main)
        self.selection_label.pack(anchor="w")
        editor = ttk.Frame(main)
        editor.pack(fill="x", pady=8)
        editor.columnconfigure(0, weight=1, uniform="equation_space")
        editor.columnconfigure(2, weight=1, uniform="equation_space")
        self.entry = ttk.Entry(editor, textvariable=self.formula, font=("Consolas", 14))
        self.entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(editor, text="Set cell", command=self.apply).grid(row=0, column=1, padx=(8, 0))
        help_label = ttk.Label(main, text="Select a cell, edit its expression, then click Set cell to save. Use a blank expression to empty it.")
        help_label.pack(anchor="w", fill="x")

        body = ttk.Frame(layout)
        body.grid(row=1, column=0, sticky="nsew", pady=16)
        body.columnconfigure(0, weight=1)
        minimum_board = self.SIZE * MIN_CELL_SIZE + 8
        body.columnconfigure(0, minsize=minimum_board + 20)
        body.rowconfigure(0, weight=1, minsize=minimum_board + 32)
        self.board = GridCanvas(body, self.select, self.SIZE)
        self.board.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        self.board.bind("<Double-Button-1>", lambda event: self.entry.focus_set())
        self.board.bind("<Button-3>", self.toggle_cell)
        sidebar = ttk.Frame(body)
        sidebar.grid(row=0, column=1, rowspan=2, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)
        variable_area = ttk.Frame(sidebar)
        variable_area.grid(row=0,column=0,sticky="nsew",padx=(0,12))
        variable_area.columnconfigure(0,weight=1)
        variable_area.rowconfigure(0,weight=1)
        overlay_panel = ttk.Frame(sidebar)
        overlay_panel.grid(row=0,column=1,sticky="new")
        overlay_panel.columnconfigure(0,minsize=250)
        ttk.Label(overlay_panel, text="Regions", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        scroll_variables = len(self.variables) > 3
        if scroll_variables:
            variable_canvas = tk.Canvas(variable_area, width=250, height=400,
                                        bg="#f4f6fa", highlightthickness=0)
            variable_canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(variable_area, orient="vertical", command=variable_canvas.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            horizontal_scrollbar = ttk.Scrollbar(variable_area, orient="horizontal", command=variable_canvas.xview)
            horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
            variable_canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal_scrollbar.set)
            panel = ttk.Frame(variable_canvas)
            variable_canvas.create_window(0, 0, window=panel, anchor="nw")
            panel.bind("<Configure>", lambda event: variable_canvas.configure(scrollregion=variable_canvas.bbox("all")))
        else:
            panel = ttk.Frame(variable_area)
            panel.grid(row=0, column=0, sticky="new")
        ttk.Label(panel, text="Variables", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        panel.columnconfigure(0,minsize=250)
        for row, (name, variable) in enumerate(self.variables.items(),start=1):
            field = ttk.LabelFrame(panel, text=name, padding=10)
            field.grid(row=row, column=0, sticky="new", padx=(0, 10), pady=(0, 10))
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text="Candidate").grid(row=0, column=0, sticky="w", padx=(0,10))
            ttk.Entry(field, textvariable=variable, width=10).grid(row=0, column=1, sticky="ew")
            self.valid_values[name] = tk.StringVar(value="Not analyzed")
            ttk.Label(field, text="Valid values").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8,0))
            ttk.Label(field, textvariable=self.valid_values[name], wraplength=210).grid(row=2, column=0, columnspan=2, sticky="w")
        self.analyze_button = ttk.Button(panel, text="Analyze valid values", command=self.analyze_valid_values)
        controls_row = len(self.variables)+1
        self.analyze_button.grid(row=controls_row, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        ttk.Label(panel, textvariable=self.search_message, wraplength=230).grid(row=controls_row+1, column=0, sticky="nw", padx=(0, 10))
        self.connectivity_button = ttk.Button(panel, text="Check connectivity", command=self.check_connectivity)
        self.connectivity_button.grid(row=controls_row+2, column=0, sticky="ew", padx=(0, 10), pady=(12, 8))
        ttk.Label(panel, textvariable=self.connectivity_message, wraplength=230).grid(row=controls_row+3, column=0, sticky="nw", padx=(0, 10))
        overlay_selection = ttk.LabelFrame(overlay_panel, text="Overlay region")
        overlay_selection.grid(row=1, column=0, sticky="ew", padx=(0,10), pady=(0,8))
        self.overlay_buttons = []
        for number in range(1,max_region_size(self.SIZE)+1):
            button = ttk.Button(overlay_selection, text=str(number), width=4,
                                command=lambda value=number:self.select_overlay_region(value))
            button.grid(row=(number-1)//5, column=(number-1)%5, padx=2, pady=2, sticky="ew")
            self.overlay_buttons.append(button)
        for column in range(5):
            overlay_selection.columnconfigure(column,weight=1)
        ttk.Label(overlay_panel, textvariable=self.overlay_message, wraplength=230).grid(row=7, column=0, sticky="nw", padx=(0, 10),pady=(8,0))
        ttk.Label(overlay_panel, textvariable=self.region_elapsed, wraplength=230).grid(row=8,column=0,sticky="w",pady=(4,0))
        overlay_navigation = ttk.Frame(overlay_panel)
        overlay_navigation.grid(row=3, column=0, sticky="ew", padx=(0,10), pady=8)
        ttk.Button(overlay_navigation, text="Previous", command=lambda:self.show_overlay(-1)).pack(side="left")
        ttk.Button(overlay_navigation, text="Next", command=lambda:self.show_overlay(1)).pack(side="left", padx=8)
        history_navigation = ttk.Frame(overlay_panel)
        history_navigation.grid(row=6,column=0,sticky="ew",pady=(0,8))
        self.compare_button = ttk.Button(overlay_panel,text="Compare incomplete regions",command=self.compare_regions,state="disabled")
        self.compare_button.grid(row=4,column=0,sticky="ew",padx=(0,10),pady=(0,8))
        self.completion_button = ttk.Button(overlay_panel,text="Attempt region completion",
                                           command=self.attempt_region_completion,state="disabled")
        self.completion_button.grid(row=5,column=0,sticky="ew",padx=(0,10),pady=(0,8))
        self.overlay_undo_button = ttk.Button(history_navigation,text="Undo",command=self.undo_overlay,state="disabled")
        self.overlay_undo_button.pack(side="left")
        self.overlay_redo_button = ttk.Button(history_navigation,text="Redo",command=self.redo_overlay,state="disabled")
        self.overlay_redo_button.pack(side="left",padx=8)
        footer = ttk.Frame(body)
        footer.grid(row=1, column=0, sticky="ew", padx=(0, 20))
        options = ttk.Frame(footer)
        options.pack(fill="x")
        self.display_button = ttk.Button(options, command=self.toggle_display)
        self.display_button.pack(side="left")
        self.update_display_button()
        ttk.Button(options, text="Exclude all", command=lambda: self.set_all_included(False)).pack(side="left", padx=(8, 0))
        ttk.Button(options, text="Include all", command=lambda: self.set_all_included(True)).pack(side="left", padx=(8, 0))
        saved_controls = ttk.Frame(footer)
        saved_controls.pack(fill="x",pady=(8,0))
        ttk.Button(saved_controls,text="Save state",command=self.save_named_state).pack(side="left")
        ttk.Button(saved_controls,text="Load state",command=self.choose_saved_state).pack(side="left",padx=8)
        ttk.Button(saved_controls,text="Reset to equations",command=self.reset_to_equations).pack(side="left")
        detail_label = ttk.Label(footer, textvariable=self.detail)
        detail_label.pack(anchor="w", fill="x", pady=(12, 4))
        status_label = ttk.Label(footer, textvariable=self.status)
        status_label.pack(anchor="w", fill="x")
        storage_label = ttk.Label(footer, textvariable=self.storage_error, foreground="#a02828")
        storage_label.pack(anchor="w", fill="x")
        def wrap_grid_labels(event):
            width = max(100, min(self.board.winfo_width(), self.board.winfo_height()) - 8)
            for label in (detail_label, status_label, storage_label):
                if str(label.cget("wraplength")) != str(width):
                    label.configure(wraplength=width)
        self.board.bind("<Configure>", wrap_grid_labels, add="+")
        main.bind("<Configure>", lambda event: help_label.configure(wraplength=max(100, event.width)))
        # Messages can add lines after a search finishes. Recalculate the
        # minimum height so the sidebar's last button never gets clipped.
        resize_pending = [False]
        def fit_contents():
            resize_pending[0] = False
            left_height = minimum_board + 32 + footer.winfo_reqheight()
            right_height = max(420 if scroll_variables else panel.winfo_reqheight(),overlay_panel.winfo_reqheight())
            height = max(620, main.winfo_reqheight() + max(left_height, right_height) + 80)
            width = max(820, sidebar.winfo_reqwidth() + minimum_board + 68)
            root.minsize(width, height)
        def schedule_fit(event=None):
            if not resize_pending[0]:
                resize_pending[0] = True
                root.after_idle(fit_contents)
        footer.bind("<Configure>", schedule_fit)
        panel.bind("<Configure>", schedule_fit, add="+")
        overlay_panel.bind("<Configure>", schedule_fit, add="+")
        main.bind("<Configure>", schedule_fit, add="+")
        for message in (self.search_message, self.connectivity_message,
                        self.overlay_message, self.detail, self.status, self.storage_error):
            message.trace_add("write", lambda *_: schedule_fit())
        self.select(0, 0)
        if self.analytical_assignments is not None:
            for name, label in self.valid_values.items():
                values = {assignment.get(name) for assignment in self.analytical_assignments}
                label.set("Unknown" if None in values else format_candidates(values))
            self.search_message.set(f"Restored {len(self.analytical_assignments)} analyzed partial assignments.")
        for variable in self.variables.values():
            variable.trace_add("write", self.settings_changed)
        root.update_idletasks()
        # Reserve room for controls even with Windows font/display scaling.
        body_height = max(minimum_board + 32 + footer.winfo_reqheight(),
                          max(420 if scroll_variables else panel.winfo_reqheight(),overlay_panel.winfo_reqheight()))
        minimum_height = max(620, main.winfo_reqheight() + body_height + 80)
        minimum_width = max(820, sidebar.winfo_reqwidth() + minimum_board + 68)
        root.minsize(minimum_width, minimum_height)
        root.geometry(f"{max(940, minimum_width + 60)}x{max(760, minimum_height)}")

    def load_state(self):
        if not self.STATE_PATH.exists():
            return
        try:
            state = read_state(self.STATE_PATH)
            expressions = state["expressions"]
            show_values = state.get("show_values", False)
            self.expressions = expressions
            self.disabled_cells = set(state.get("disabled_cells", []))
            self.variables = {name: tk.StringVar(value=value) for name, value in state["variables"].items()}
            self.show_values.set(show_values)
            self.overlay_target.set(str(state.get("overlay_region", "Highest")))
            analysis = state.get("analysis")
            if analysis:
                self.analytical_assignments = [{name: None if value is None else Fraction(value)
                                               for name, value in assignment.items()}
                                              for assignment in analysis.get("assignments", [])]
                self.analysis_steps = analysis.get("steps", [])
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.storage_error.set(f"Could not load saved grid: {error}")

    def state_data(self):
        state = {"size": self.SIZE, "expressions": self.expressions,
                 "disabled_cells": sorted(self.disabled_cells),
                 "variables": {name: value.get() for name, value in self.variables.items()},
                 "overlay_region": self.overlay_target.get(),
                 "show_values": self.show_values.get()}
        if self.analytical_assignments is not None:
            state["analysis"] = {
                "assignments": [{name: None if value is None else str(value) for name,value in assignment.items()}
                                for assignment in self.analytical_assignments],
                "steps": self.analysis_steps}
        return state

    def save_state(self):
        state = self.state_data()
        try:
            write_state(self.STATE_PATH, state)
            self.storage_error.set("")
        except OSError as error:
            self.storage_error.set(f"Could not save grid: {error}")

    def save_named_state(self):
        if getattr(self,'overlay_busy',False):
            self.storage_error.set("Wait for the overlay analysis to finish before saving.")
            return
        name = simpledialog.askstring("Save state","Name for this saved state:",parent=self.root,
                                     initialvalue=datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
        if name is None: return
        try:
            name = grid_name(name.strip())
            folder = Path(__file__).resolve().parent / 'saved states' / self.STATE_PATH.stem
            path = folder / f'{name}.json'
            if path.exists() and not messagebox.askyesno("Save state",f"Replace saved state '{name}'?",parent=self.root):
                return
            state = self.state_data()
            state['overlay_snapshot'] = encode_overlay(self.overlay_snapshot())
            state['overlay_history'] = encode_overlay({'undo':self.overlay_undo,'redo':self.overlay_redo})
            state['selected'] = list(self.selected)
            state['valid_values'] = {key:value.get() for key,value in self.valid_values.items()}
            state['search_message'] = self.search_message.get()
            state['connectivity_message'] = self.connectivity_message.get()
            write_state(path,state)
            self.storage_error.set("")
        except (OSError,ValueError,argparse.ArgumentTypeError) as error:
            self.storage_error.set(f"Could not save state: {error}")

    def choose_saved_state(self):
        if getattr(self,'overlay_busy',False):
            self.storage_error.set("Wait for the overlay analysis to finish before loading.")
            return
        folder = Path(__file__).resolve().parent / 'saved states' / self.STATE_PATH.stem
        paths = sorted(folder.glob('*.json'))
        if not paths:
            self.storage_error.set("No saved states for this grid yet.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Load state")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog,text="Saved state:").pack(anchor="w",padx=16,pady=(16,4))
        selection = ttk.Combobox(dialog,state="readonly",values=[path.stem for path in paths],width=40)
        selection.pack(padx=16,pady=4)
        selection.current(0)
        def load():
            if self.load_named_state(paths[selection.current()]):
                dialog.destroy()
        ttk.Button(dialog,text="Load",command=load).pack(padx=16,pady=16)

    def load_named_state(self, path):
        try:
            state = read_state(path)
            if state['size'] != self.SIZE or set(state['variables']) != set(self.variables):
                raise ValueError("Saved state has a different grid size or variable configuration.")
            snapshot = decode_overlay(state['overlay_snapshot'])
            required_snapshot = {'states','index','highest','base','tested','target','message','labels','palette'}
            if not isinstance(snapshot,dict) or not required_snapshot <= snapshot.keys():
                raise ValueError("Invalid saved overlay snapshot.")
            history = decode_overlay(state.get('overlay_history',encode_overlay({'undo':[],'redo':[]})))
            selected = state.get('selected',[0,0])
            if (not isinstance(selected,list) or len(selected) != 2
                    or any(type(value) is not int or not 0 <= value < self.SIZE for value in selected)):
                raise ValueError("Invalid selected cell.")
            analysis = state.get('analysis')
            assignments = None if analysis is None else [
                {name:None if value is None else Fraction(value) for name,value in item.items()}
                for item in analysis['assignments']]
            self.updating_candidates = True
            try:
                self.expressions = state['expressions']
                self.disabled_cells = set(state.get('disabled_cells',[]))
                for name,value in state['variables'].items(): self.variables[name].set(value)
                self.show_values.set(state.get('show_values',False))
                self.analytical_assignments = assignments
                self.analysis_steps = [] if analysis is None else analysis.get('steps',[])
                for name,label in self.valid_values.items(): label.set(state.get('valid_values',{}).get(name,'Not analyzed'))
                self.search_message.set(state.get('search_message',''))
                self.connectivity_message.set(state.get('connectivity_message',''))
                self.overlay_undo,self.overlay_redo = history['undo'],history['redo']
                self.update_display_button()
                self.select(*selected)
                self.restore_overlay(snapshot)
                self.storage_error.set("")
            finally:
                self.updating_candidates = False
            return True
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            self.storage_error.set(f"Could not load state: {error}")
            return False

    def reset_to_equations(self):
        self.clear_regions()
        self.overlay_target.set('Highest')
        self.overlay_index = 0
        self.overlay_highest = None
        self.overlay_base_labels = {}
        self.overlay_tested = 0
        self.disabled_cells.clear()
        self.connectivity_message.set("")
        self.show_values.set(False)
        self.update_display_button()
        self.refresh()
        self.save_state()

    def settings_changed(self, *_):
        if getattr(self, "updating_candidates", False):
            return
        if _:
            self.clear_regions()
        self.connectivity_message.set("")
        self.refresh()
        self.save_state()

    def apply_single_assignment(self):
        if self.analytical_assignments is None or len(self.analytical_assignments) != 1:
            return False
        changed = False
        self.updating_candidates = True
        try:
            for name, value in self.analytical_assignments[0].items():
                if value is not None and name in self.variables:
                    text = str(value)
                    if self.variables[name].get() != text:
                        self.variables[name].set(text)
                        changed = True
        finally:
            self.updating_candidates = False
        if changed:
            self.clear_regions()
            self.connectivity_message.set("")
            self.refresh()
        return changed

    def update_display_button(self):
        self.display_button.configure(text="Prioritize equations" if self.show_values.get()
                                      else "Prioritize values")

    def toggle_display(self):
        self.show_values.set(not self.show_values.get())
        self.update_display_button()
        self.refresh()
        self.save_state()

    def invalidate_search(self):
        self.analytical_assignments = None
        self.analysis_steps = []
        self.search_revision += 1
        for value in self.valid_values.values():
            value.set("Not computed")
        self.search_message.set("Grid changed. Analyze valid values again.")



    def analyze_valid_values(self):
        try:
            expressions = [cell for row in self.active_expressions() for cell in row if cell.strip()]
            for expression in expressions:
                clue_variables(expression, self.variables)
        except (ValueError, SyntaxError, ZeroDivisionError) as error:
            self.search_message.set(str(error))
            return
        self.invalidate_search()
        revision = self.search_revision
        self.analyze_button.configure(state="disabled")
        self.search_message.set("Analyzing included clues…")
        results = Queue()
        def work():
            try:
                results.put((analyze_clues(expressions, self.variables, max_region_size(self.SIZE)), None))
            except Exception as error:
                results.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try:
                result, error = results.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self.analyze_button.configure(state="normal")
            if revision != self.search_revision:
                return
            if error:
                self.search_message.set(f"Could not analyze: {error}")
                return
            self.analytical_assignments, self.analysis_steps = result
            self.apply_single_assignment()
            for name, label in self.valid_values.items():
                values = {assignment[name] for assignment in self.analytical_assignments}
                label.set("Unknown" if None in values else format_candidates(values))
            message = f"{len(self.analytical_assignments)} analytically valid partial assignments."
            if self.analytical_assignments:
                message += " Example: " + ", ".join(f"{name}: {'?' if value is None else value}"
                                                    for name,value in self.analytical_assignments[0].items()) + "."
            self.search_message.set(message)
            self.save_state()
        self.root.after(50, poll)



    def select(self, x, y):
        self.selected = (x, y)
        self.formula.set(self.expressions[y][x])
        self.selection_label.configure(text=f"Selected cell: row {y + 1}, column {x + 1}")
        self.refresh()

    def active_expressions(self):
        disabled = getattr(self, "disabled_cells", set())
        return [["" if row*self.SIZE+column in disabled else expression
                 for column, expression in enumerate(cells)]
                for row, cells in enumerate(self.expressions)]

    def toggle_cell(self, event):
        left, top, side = self.board.bounds
        if not side or not (left <= event.x < left+side and top <= event.y < top+side):
            return
        column = int((event.x-left)*self.SIZE/side)
        row = int((event.y-top)*self.SIZE/side)
        cell = row*self.SIZE+column
        if cell in self.disabled_cells:
            self.disabled_cells.remove(cell)
        else:
            self.disabled_cells.add(cell)
        self.clear_regions()
        self.connectivity_message.set("")
        self.invalidate_search()
        self.select(column, row)
        self.save_state()

    def set_all_included(self, included):
        self.disabled_cells = set() if included else {
            row*self.SIZE+column for row, cells in enumerate(self.expressions)
            for column, expression in enumerate(cells) if expression.strip()
        }
        self.clear_regions()
        self.connectivity_message.set("")
        self.invalidate_search()
        self.refresh()
        self.save_state()

    def apply(self):
        self.clear_regions()
        expression = self.formula.get().strip()
        x, y = self.selected
        self.expressions[y][x] = expression
        self.connectivity_message.set("")
        self.invalidate_search()
        self.refresh()
        self.save_state()

    def check_connectivity(self):
        expressions = self.active_expressions()
        try:
            variables = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
        except (ValueError, ZeroDivisionError):
            self.connectivity_message.set("Enter numeric candidate values.")
            return
        partials = None if self.analytical_assignments is None else [dict(item) for item in self.analytical_assignments]
        revision = self.search_revision
        self.connectivity_button.configure(state="disabled")
        self.connectivity_message.set("Checking connectivity…")
        results = Queue()
        def work():
            try:
                message = check_grid_connectivity(expressions, variables)[1]
                survivors = None
                if partials is not None:
                    survivors = []
                    for assignment in partials:
                        used = set().union(*(clue_variables(cell, self.variables) for row in expressions for cell in row if cell.strip()))
                        if any(assignment.get(name) is None for name in used):
                            raise ValueError("Analyze the included clues before filtering connectivity.")
                        known = {name:value for name,value in assignment.items() if value is not None}
                        if check_grid_connectivity(expressions, known)[0]:
                            survivors.append(assignment)
                results.put((message, survivors))
            except Exception as error:
                results.put((f"Could not finish connectivity check: {error}", None))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try:
                message, filtered = results.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self.connectivity_button.configure(state="normal")
            if revision != self.search_revision or expressions != self.active_expressions():
                self.connectivity_message.set("Grid or analysis changed. Check connectivity again.")
                return
            applied_assignment = False
            if filtered is not None:
                self.analytical_assignments = filtered
                applied_assignment = self.apply_single_assignment()
                for name, label in self.valid_values.items():
                    values = {assignment.get(name) for assignment in filtered}
                    label.set("Unknown" if None in values else format_candidates(values))
                self.search_message.set(f"{len(filtered)} analyzed assignments pass connectivity.")
                self.save_state()
            try:
                current = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
            except (ValueError, ZeroDivisionError):
                current = None
            if expressions != self.active_expressions() or (current != variables and not applied_assignment):
                message = "Candidates or grid changed. Check connectivity again."
            self.connectivity_message.set(message)
        self.root.after(50, poll)

    def clear_regions(self, reset_history=True):
        self.region_labels = {}
        self.region_palette = {}
        self.overlay_states = []
        self.overlay_message.set("")
        if hasattr(self,'region_elapsed'):
            self.region_elapsed.set("")
        if reset_history:
            self.overlay_undo.clear()
            self.overlay_redo.clear()
        if hasattr(self,"overlay_buttons"):
            self.update_overlay_buttons()

    def select_overlay_region(self, number):
        self.overlay_target.set(str(number))
        self.save_state()
        if self.overlay_states and number != self.overlay_highest:
            self.continue_overlay(number)
        else:
            self.overlay_regions()

    def set_overlay_buttons_enabled(self, enabled):
        self.overlay_busy = not enabled
        self.update_overlay_buttons()

    def overlay_snapshot(self):
        return deepcopy({
            'states':self.overlay_states,'index':self.overlay_index,
            'highest':getattr(self,'overlay_highest',None),
            'base':getattr(self,'overlay_base_labels',{}),
            'tested':getattr(self,'overlay_tested',0),
            'target':str(self.overlay_highest) if self.overlay_states else self.overlay_target.get(),
            'message':self.overlay_message.get(),
            'labels':self.region_labels,'palette':self.region_palette,
            'elapsed':self.region_elapsed.get() if hasattr(self,'region_elapsed') else ''})

    def record_overlay(self, previous):
        self.overlay_undo.append(previous)
        self.overlay_redo.clear()

    def restore_overlay(self, snapshot):
        snapshot = deepcopy(snapshot)
        self.overlay_states = snapshot['states']
        self.overlay_index = snapshot['index']
        self.overlay_highest = snapshot['highest']
        self.overlay_base_labels = snapshot['base']
        self.overlay_tested = snapshot['tested']
        self.overlay_target.set(snapshot['target'])
        self.region_labels = snapshot['labels']
        self.region_palette = snapshot['palette']
        self.overlay_message.set(snapshot['message'])
        if hasattr(self,'region_elapsed'):
            self.region_elapsed.set(snapshot.get('elapsed',''))
        self.update_overlay_buttons()
        self.refresh()
        self.save_state()

    def undo_overlay(self):
        if getattr(self,'overlay_busy',False) or not self.overlay_undo:
            return
        self.overlay_redo.append(self.overlay_snapshot())
        self.restore_overlay(self.overlay_undo.pop())

    def redo_overlay(self):
        if getattr(self,'overlay_busy',False) or not self.overlay_redo:
            return
        self.overlay_undo.append(self.overlay_snapshot())
        self.restore_overlay(self.overlay_redo.pop())

    def update_overlay_buttons(self):
        completed = set()
        if self.overlay_states:
            boards = []
            for state in self.overlay_states:
                board = dict(state.get('assumptions',self.overlay_base_labels))
                board.update({cell:self.overlay_highest for cell in state['cells']})
                boards.append(board)
            for number in range(1,len(self.overlay_buttons)+1):
                cells = frozenset(cell for cell,value in boards[0].items() if value == number)
                if len(cells) == number and all(
                        frozenset(cell for cell,value in board.items() if value == number) == cells
                        for board in boards[1:]):
                    completed.add(number)
        for number,button in enumerate(self.overlay_buttons,start=1):
            disabled = getattr(self,"overlay_busy",False) or number in completed
            button.configure(state="disabled" if disabled else "normal")
        if hasattr(self,'overlay_undo_button'):
            busy = getattr(self,'overlay_busy',False)
            self.overlay_undo_button.configure(state="normal" if self.overlay_undo and not busy else "disabled")
            self.overlay_redo_button.configure(state="normal" if self.overlay_redo and not busy else "disabled")
        if hasattr(self,'compare_button'):
            self.compare_button.configure(state="normal" if self.overlay_states and not getattr(self,'overlay_busy',False) else "disabled")
        if hasattr(self,'completion_button'):
            self.completion_button.configure(state="normal" if self.overlay_states and not getattr(self,'overlay_busy',False) else "disabled")

    def overlay_regions(self):
        expressions = self.active_expressions()
        selected = self.overlay_target.get()
        try:
            variables = {name:Fraction(value.get().strip()) for name,value in self.variables.items()}
            target = None if selected == "Highest" else int(selected)
        except (ValueError,ZeroDivisionError):
            self.overlay_message.set("Enter numeric candidate values first.")
            return
        previous = self.overlay_snapshot()
        started = perf_counter()
        self.set_overlay_buttons_enabled(False)
        self.overlay_message.set("Testing translated, reflected, and rotated overlays…")
        results = Queue()
        def work():
            try:
                results.put(('result',find_region_overlays(expressions,variables,
                    lambda tested,valid:results.put(('progress',(tested,valid))), region=target)))
            except Exception as error:
                results.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            self.region_elapsed.set(f"Time: {perf_counter()-started:.2f} seconds")
            final = None
            try:
                while True:
                    kind,data = results.get_nowait()
                    if kind == 'progress':
                        self.overlay_message.set(f"Tested {data[0]} placements; {data[1]} valid so far.")
                    else:
                        final = (kind,data)
                        break
            except Empty:
                pass
            if final is None:
                self.root.after(50,poll)
                return
            self.set_overlay_buttons_enabled(True)
            try:
                current = {name:Fraction(value.get().strip()) for name,value in self.variables.items()}
            except (ValueError,ZeroDivisionError): current = None
            if expressions != self.active_expressions() or current != variables or self.overlay_target.get() != selected:
                self.overlay_message.set("Grid or candidates changed. Overlay regions again.")
                return
            kind,data = final
            if kind == 'error':
                self.overlay_message.set(data)
                self.refresh()
                return
            self.record_overlay(previous)
            self.clear_regions(reset_history=False)
            self.region_elapsed.set(f"Time: {perf_counter()-started:.2f} seconds")
            self.overlay_highest,self.overlay_base_labels,self.overlay_states,self.overlay_tested = data
            self.overlay_index = 0
            if not self.overlay_states:
                self.overlay_message.set(f"No valid overlays among {self.overlay_tested} tested placements.")
                self.refresh()
                return
            self.show_overlay(0)
        self.root.after(50,poll)

    def show_overlay(self, step):
        if not self.overlay_states:
            return
        self.update_overlay_buttons()
        self.overlay_index = (self.overlay_index+step)%len(self.overlay_states)
        state = self.overlay_states[self.overlay_index]
        self.region_labels = dict(state.get('assumptions',self.overlay_base_labels))
        self.region_labels.update({cell:self.overlay_highest for cell in state['cells']})
        self.region_palette = region_colors(self.SIZE,self.region_labels)
        self.overlay_message.set(
            f"Overlay {self.overlay_index+1}/{len(self.overlay_states)} for region {self.overlay_highest}. "
            f"Row {state['row']+1}, column {state['column']+1}; rotation {state['rotation']*90}°"
            f"{' reflected' if state['reflected'] else ''}. "
            f"Minimum connected size: {state['minimum_size']}. {self.overlay_tested} placements tested.")
        if state.get('forced_cells'):
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['forced_cells'])} forced adjacent cells added.")
        if state.get('connection_cells'):
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['connection_cells'])} low-slack connection cells added.")
        if state.get('neighbor_growth'):
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['neighbor_growth'])} cells forced by bordering-region growth.")
        if state.get('growth_limited'):
            self.overlay_message.set(self.overlay_message.get()+" Growth limited: 3 rounds per region or more than 10 candidate cells.")
        if 'parent_index' in state:
            self.overlay_message.set(self.overlay_message.get()+f" From preceding overlay {state['parent_index']+1}.")
        if state.get('reverse_containment'):
            self.overlay_message.set(self.overlay_message.get()+f" Shape derived by removing one cell from region {self.overlay_highest+1}.")
        if 'comparison_growth' in state:
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['comparison_growth'])} cells forced by comparing incomplete regions.")
        if 'completion_growth' in state:
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['completion_growth'])} cells added by mirrored region completion.")
        self.refresh()

    def continue_overlay(self, region=None):
        if not self.overlay_states:
            self.overlay_message.set("Generate valid overlays first.")
            return
        states = self.overlay_states
        current = self.overlay_highest
        target = current+1 if region is None else region
        if target > max_region_size(self.SIZE):
            self.overlay_message.set("The next region exceeds max region size.")
            return
        previous = self.overlay_snapshot()
        started = perf_counter()
        self.set_overlay_buttons_enabled(False)
        self.overlay_message.set(f"Testing all {len(states)} preceding overlays for region {target}…")
        results = Queue()
        def work():
            try:
                result=continue_region_overlays(self.SIZE,self.overlay_base_labels,current,states,
                    lambda done,total,valid:results.put(('progress',(done,total,valid))),region=target)
                results.put(('result',result))
            except Exception as error:
                results.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            self.region_elapsed.set(f"Time: {perf_counter()-started:.2f} seconds")
            final=None
            try:
                while True:
                    kind,data=results.get_nowait()
                    if kind=='progress':
                        self.overlay_message.set(f"Checked {data[0]}/{data[1]} preceding overlays; {data[2]} valid continuations.")
                    else:
                        final=(kind,data)
                        break
            except Empty: pass
            if final is None:
                self.root.after(50,poll)
                return
            self.set_overlay_buttons_enabled(True)
            if self.overlay_states is not states:
                self.overlay_message.set("Grid or overlays changed. Generate overlays again.")
                return
            kind,data=final
            if kind=='error':
                self.overlay_message.set(data)
                return
            target,children,tested=data
            if not children:
                self.overlay_message.set(f"No valid region {target} continuations. Previous overlays retained.")
                return
            self.record_overlay(previous)
            self.overlay_highest=target
            self.overlay_states=children
            self.overlay_tested=tested
            self.overlay_target.set(str(target))
            self.overlay_index=0
            self.show_overlay(0)
            self.save_state()
        self.root.after(50,poll)

    def attempt_region_completion(self):
        self.compare_regions(completion=True)

    def compare_regions(self, completion=False):
        if not self.overlay_states or getattr(self,'overlay_busy',False):
            return
        states = self.overlay_states
        current,base = self.overlay_highest,self.overlay_base_labels
        previous = self.overlay_snapshot()
        started = perf_counter()
        self.set_overlay_buttons_enabled(False)
        self.overlay_message.set("Attempting region completions from smallest to largest…" if completion
                                 else "Comparing incomplete regions from largest to smallest…")
        results = Queue()
        def work():
            try:
                analyze = attempt_region_completions if completion else compare_incomplete_regions
                children = analyze(self.SIZE,base,current,states,
                    lambda done,total,valid:results.put(('progress',(done,total,valid))))
                results.put(('result',children))
            except Exception as error:
                results.put(('error',str(error)))
        threading.Thread(target=work,daemon=True).start()
        def poll():
            self.region_elapsed.set(f"Time: {perf_counter()-started:.2f} seconds")
            final = None
            try:
                while True:
                    kind,data = results.get_nowait()
                    if kind == 'progress':
                        self.overlay_message.set(f"Checked {data[0]}/{data[1]} overlays; {data[2]} surviving.")
                    else:
                        final = (kind,data)
                        break
            except Empty: pass
            if final is None:
                self.root.after(50,poll)
                return
            self.set_overlay_buttons_enabled(True)
            if self.overlay_states is not states:
                self.overlay_message.set("Grid or overlays changed. Compare again.")
                return
            kind,data = final
            if kind == 'error':
                self.overlay_message.set(data)
                return
            if not data:
                self.overlay_message.set("No overlays survive mirrored completion. Previous overlays retained." if completion
                                         else "No overlays survive incomplete-region comparison. Previous overlays retained.")
                return
            self.record_overlay(previous)
            self.overlay_states = data
            self.overlay_index = 0
            self.show_overlay(0)
            self.save_state()
        self.root.after(50,poll)

    def refresh(self):
        filled, errors = 0, 0
        cells = []
        variable_error = None
        try:
            values = {name: Fraction(variable.get().strip()) for name, variable in self.variables.items()}
        except (ValueError, ZeroDivisionError):
            variable_error = "Enter numeric values for all variables (for example 3 or 1/2)."
        selected_detail = "Empty cell. Enter an expression or a positive integer."
        for y, row in enumerate(self.active_expressions()):
            for x, expression in enumerate(row):
                text, color = expression, "#ffffff"
                detail = "Empty cell. Enter an expression or a positive integer."
                if expression:
                    filled += 1
                    try:
                        if variable_error:
                            raise ValueError(variable_error)
                        value = evaluate(expression, values)
                        value_text = str(value)
                        detail = f"{expression} = {value_text}"
                        if values:
                            detail += " with " + ", ".join(f"{name} = {value}" for name, value in values.items())
                        if value <= 0 or value.denominator != 1 or value > max_region_size(self.SIZE):
                            color = "#fff1d6"
                            detail += f" • Result must be an integer from 1 to {max_region_size(self.SIZE)}."
                        if self.show_values.get():
                            text = value_text
                    except (ValueError, SyntaxError, ArithmeticError, RecursionError) as error:
                        errors += 1
                        color = "#ffe0e0"
                        detail = f"Cannot calculate {expression}: {error}"
                selected = (x, y) == self.selected
                region = self.region_labels.get(y*self.SIZE+x)
                if region is not None:
                    color = self.region_palette[region]
                    text = str(region) if self.show_values.get() or not expression else expression
                    if not expression:
                        detail = f"Forced cell in region {region}."
                if y*self.SIZE+x in getattr(self, "disabled_cells", set()):
                    color = "#e5e5e5"
                    text = self.expressions[y][x] or text
                    detail = "Equation disabled. Right-click to enable it again."
                cells.append((x, y, text, color))
                if selected:
                    selected_detail = detail
        self.detail.set(selected_detail)
        self.board.cells = cells
        self.board.selection = self.selected
        self.board.draw()
        self.status.set(variable_error or
                        f"{filled}/{self.SIZE ** 2} cells filled • {errors} expression errors. "
                        "Amber cells are outside the allowed integer region sizes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open a named expression grid.")
    parser.add_argument("name", nargs="?", default="example", type=grid_name,
                        help="Grid name (default: example). New names prompt for a size.")
    args = parser.parse_args()
    window = tk.Tk()
    window.withdraw()
    try:
        state_path = prepare_grid(window, args.name)
        if state_path is not None:
            PuzzleApp(window, args.name, state_path)
            window.deiconify()
            window.mainloop()
        else:
            window.destroy()
    except (OSError, ValueError) as error:
        messagebox.showerror("Could not open grid", str(error), parent=window)
        window.destroy()
