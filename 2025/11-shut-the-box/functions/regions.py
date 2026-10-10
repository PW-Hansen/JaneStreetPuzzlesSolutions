"""Connect confirmed box cells and exclude unreachable unknown pockets."""


def orthogonal_neighbors(index, rows, columns):
    row, column = divmod(index, columns)
    if row: yield index - columns
    if column + 1 < columns: yield index + 1
    if row + 1 < rows: yield index + columns
    if column: yield index - 1


def propagate_regions(boxes, sources, rows, columns, conflicts):
    """Force connectors and exclude cells outside the possible-box component.

    Unknown and yes cells are traversable; no cells are walls. An iterative
    depth-first traversal tracks whether removing a vertex separates a subtree
    containing a confirmed box cell from the confirmed root. Unknown dead ends
    without confirmed greens do not require growth. Unknown components unreachable
    from any confirmed green cannot belong to the connected box.
    """
    if conflicts:
        return False
    greens = [index for index, box in enumerate(boxes) if box is True]
    if not greens:
        return False
    root = greens[0]
    discovered = {root: 0}
    low = {root: 0}
    terminals = {root: 1}
    parents = {root: None}
    stack = [(root, iter(orthogonal_neighbors(root, rows, columns)))]
    required = set()
    while stack:
        vertex, neighbors = stack[-1]
        neighbor = next(neighbors, None)
        if neighbor is not None:
            if boxes[neighbor] is False or neighbor == parents[vertex]:
                continue
            if neighbor in discovered:
                low[vertex] = min(low[vertex], discovered[neighbor])
            else:
                parents[neighbor] = vertex
                discovered[neighbor] = low[neighbor] = len(discovered)
                terminals[neighbor] = int(boxes[neighbor] is True)
                stack.append((neighbor, iter(orthogonal_neighbors(neighbor, rows, columns))))
        else:
            stack.pop()
            parent = parents[vertex]
            if parent is not None:
                # The root itself is confirmed green, so a separated green
                # subtree always has another green outside it.
                if boxes[parent] is None and low[vertex] >= discovered[parent] and terminals[vertex]:
                    required.add(parent)
                low[parent] = min(low[parent], low[vertex])
                terminals[parent] += terminals[vertex]
    disconnected = [index for index in greens if index not in discovered]
    if disconnected:
        row, column = divmod(disconnected[0], columns)
        conflicts.append(f'R{row + 1}C{column + 1}: box region cannot connect to all other box cells '
                         'through unknown cells; non-box cells block every path.')
        return False
    for index in required:
        boxes[index] = True
        sources[index] = 'region rules'
    excluded = [index for index, box in enumerate(boxes) if box is None and index not in discovered]
    for index in excluded:
        boxes[index] = False
        sources[index] = 'region rules'
    return bool(required or excluded)


def propagate_exterior(boxes, sources, rows, columns, conflicts):
    """Connect every non-box cell to a common exterior around the grid.

    Invert box membership and surround the board with a connected ring of
    confirmed exterior cells. The same connectivity rule then finds necessary
    non-box escape cells and unknown pockets that cannot be non-box at all.
    """
    if conflicts:
        return False
    padded_rows, padded_columns = rows + 2, columns + 2
    exterior = [True] * (padded_rows * padded_columns)
    mapping = []
    for index, box in enumerate(boxes):
        row, column = divmod(index, columns)
        padded_index = (row + 1) * padded_columns + column + 1
        mapping.append(padded_index)
        exterior[padded_index] = None if box is None else not box
    exterior_sources = ['unknown' if box is None else 'clue' for box in exterior]
    exterior_conflicts = []
    propagate_regions(exterior, exterior_sources, padded_rows, padded_columns, exterior_conflicts)
    if exterior_conflicts:
        conflicts.append('Non-box region cannot reach the grid edge: '
                         'confirmed box cells block every possible path through non-box or unknown cells.')
        return False
    changed = False
    for index, padded_index in enumerate(mapping):
        if boxes[index] is None and exterior[padded_index] is not None:
            boxes[index] = not exterior[padded_index]
            sources[index] = 'region rules'
            changed = True
    return changed
