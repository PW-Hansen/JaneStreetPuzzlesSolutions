"""Region size limits, exact connection feasibility, and clue checks."""

from collections import deque
from heapq import heapify, heappop, heappush
from math import isqrt
from equations_functions import evaluate
from .cancellation import check_region_abort


def max_region_size(grid_size):
    """Largest n with triangular number n(n + 1)/2 <= grid area."""
    return (isqrt(8 * grid_size * grid_size + 1) - 1) // 2


def minimum_region_size(size, labels, number, terminals):
    """Exact graph Steiner-tree size using terminal-subset dynamic programming."""
    check_region_abort()
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
        check_region_abort()
        if mask & (mask-1) == 0:
            index = mask.bit_length()-1
            dp[mask] = {cell:cost for cell,cost in distances[index].items() if cost <= budget}
            continue
        best = {}
        sub = (mask-1)&mask
        while sub:
            check_region_abort()
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
            check_region_abort()
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
