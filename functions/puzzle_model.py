"""Grid geometry, exact region areas, perimeter scores, and answer calculation."""
import colorsys
from dataclasses import dataclass, field
from functions.constants import ARC_CYCLE, MINIMUM_REGION_PIECES


def allowed_arc_configurations(state, row, column):
    """Intersect the persistent master domain with explicit puzzle markings."""
    cell = state["cells"][row][column]
    domains = state.get("arc_domains")
    allowed = domains[row][column] if domains is not None else ARC_CYCLE
    if cell["green"]:
        return (None,) if None in allowed else ()
    if cell["arc"] is not None:
        return (cell["arc"],) if cell["arc"] in allowed else ()
    return tuple(orientation for orientation in ARC_CYCLE if orientation in allowed)



def clue_factorizations(state, selected):
    """Ordered area/perimeter factor pairs within conservative grid bounds.

    These are arithmetic candidates, not a claim that each pair is realizable.
    No factoring loop depends on the magnitude of the clue (only grid area).
    """
    r, c = selected
    clue = state["cells"][r][c]["number"]
    if clue is None or clue <= 0:
        return []
    max_area = state["rows"] * state["columns"]
    possible_arcs = sum(any(arc is not None for arc in allowed_arc_configurations(state, r, c))
                        for r in range(state["rows"]) for c in range(state["columns"]))
    max_pieces = possible_arcs + 2 * state["rows"] + 2 * state["columns"]
    return [(area, clue // area) for area in range(1, min(clue, max_area) + 1)
            if clue % area == 0 and MINIMUM_REGION_PIECES <= clue // area <= max_pieces]



def arc_endpoints(row, column, orientation):
    """Return exact grid corners and tangent vectors pointing into the arc."""
    return {
        "tl": (((row, column + 1), (0, 1)), ((row + 1, column), (1, 0))),
        "tr": (((row, column), (0, 1)), ((row + 1, column + 1), (-1, 0))),
        "br": (((row, column + 1), (-1, 0)), ((row + 1, column), (0, -1))),
        "bl": (((row, column), (1, 0)), ((row + 1, column + 1), (0, -1))),
    }[orientation]



def smooth_arc_groups(state):
    """Join arcs only when their inward tangents at a shared corner oppose."""
    corners, parent = {}, {}
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            if cell["arc"] is None:
                continue
            arc = (r, c)
            parent[arc] = arc
            for corner, tangent in arc_endpoints(r, c, cell["arc"]):
                corners.setdefault(corner, []).append((arc, tangent))

    def find(arc):
        while parent[arc] != arc:
            parent[arc] = parent[parent[arc]]
            arc = parent[arc]
        return arc

    for entries in corners.values():
        for i, (first, tangent) in enumerate(entries):
            for second, other in entries[i + 1:]:
                if tangent == (-other[0], -other[1]):
                    parent[find(second)] = find(first)
    roots = {}
    groups = {}
    for arc in parent:
        root = find(arc)
        groups[arc] = roots.setdefault(root, len(roots))
    neighbors = {group: set() for group in roots.values()}
    conflicts = set()
    for corner, entries in corners.items():
        for i, (first, tangent) in enumerate(entries):
            for second, other in entries[i + 1:]:
                if tangent == (-other[0], -other[1]):
                    continue
                a, b = groups[first], groups[second]
                if a == b:
                    # A smooth chain can return to its own end with a sharp join.
                    conflicts.add(corner)
                else:
                    neighbors[a].add(b)
                    neighbors[b].add(a)
    palette = ["#d62728", "#1769aa", "#8b35b5", "#008577", "#b56300",
               "#c1277b", "#596a15", "#5646a5"]
    assigned = {}
    for group in sorted(neighbors, key=lambda g: (-len(neighbors[g]), g)):
        forbidden = {assigned[n] for n in neighbors[group] if n in assigned}
        index = next(i for i in range(len(palette) + 1) if i not in forbidden)
        if index == len(palette):
            rgb = colorsys.hsv_to_rgb((index * .61803398875) % 1, .8, .65)
            palette.append("#" + "".join(f"{round(v * 255):02x}" for v in rgb))
        assigned[group] = index
    colors = {arc: palette[assigned[group]] for arc, group in groups.items()}
    return groups, colors, conflicts



def determine_regions(state):
    """Connect cell fragments across full edges, never through a corner alone.

    Fragment 0 is the quarter-disc (or an unsplit cell), fragment 1 its
    complement. An arc is dangling exactly when its fragments reconnect.
    """
    parent = {}
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            for side in range(2 if cell["arc"] else 1):
                parent[(r, c, side)] = (r, c, side)

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def edge_fragment(r, c, edge):
        arc = state["cells"][r][c]["arc"]
        inside_edges = {"tl": "NW", "tr": "NE", "br": "SE", "bl": "SW"}
        return (r, c, 0 if arc is None or edge in inside_edges[arc] else 1)

    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            if c + 1 < state["columns"]:
                parent[find(edge_fragment(r, c, "E"))] = find(edge_fragment(r, c + 1, "W"))
            if r + 1 < state["rows"]:
                parent[find(edge_fragment(r, c, "S"))] = find(edge_fragment(r + 1, c, "N"))
    roots, regions = {}, {}
    for fragment in parent:
        root = find(fragment)
        regions[fragment] = roots.setdefault(root, len(roots))
    adjacency = {region: set() for region in roots.values()}
    invalid_arcs = []
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            if cell["arc"]:
                a, b = regions[(r, c, 0)], regions[(r, c, 1)]
                if a == b:
                    invalid_arcs.append((r, c))
                else:
                    adjacency[a].add(b)
                    adjacency[b].add(a)
    palette = ["#f8d0d0", "#c9ddfa", "#f4dfb2", "#d9cdf4",
               "#c7e9df", "#f3cde7", "#e4e9bc", "#cce8ef"]
    assigned = {}
    for region in sorted(adjacency, key=lambda n: (-len(adjacency[n]), n)):
        used = {assigned[n] for n in adjacency[region] if n in assigned}
        index = next(i for i in range(len(palette) + 1) if i not in used)
        if index == len(palette):
            rgb = colorsys.hsv_to_rgb((index * .61803398875) % 1, .22, .97)
            palette.append("#" + "".join(f"{round(v * 255):02x}" for v in rgb))
        assigned[region] = index
    colors = {fragment: palette[assigned[region]] for fragment, region in regions.items()}
    fragments_by_region = {region: set() for region in adjacency}
    invalid_by_region = {region: set() for region in adjacency}
    for fragment, region in regions.items():
        fragments_by_region[region].add(fragment)
    for r, c in invalid_arcs:
        invalid_by_region[regions[(r, c, 0)]].add((r, c))
    objects = {region: Region.from_fragments(region, fragments, state,
                                            invalid_by_region[region])
               for region, fragments in fragments_by_region.items()}
    return {fragment: objects[region] for fragment, region in regions.items()}, colors, invalid_arcs



@dataclass(frozen=True)
class Region:
    """A connected region that computes and stores its exact area value."""

    id: int
    fragments: frozenset[tuple[int, int, int]]
    whole_cells: int = 0
    arc_insides: int = 0
    arc_outsides: int = 0
    invalid_arcs: frozenset[tuple[int, int]] = frozenset()
    area: int | str = field(init=False)
    smooth_pieces: int | None = field(init=False, default=None, compare=False)
    score: int | None = field(init=False, default=None, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "area", self.determine_area())

    @property
    def is_valid(self):
        return self.determine_validity()

    def has_valid_arc_separation(self):
        """Check only that the region does not contain both sides of an arc."""
        return not self.invalid_arcs and not any(
            side == 0 and (r, c, 1) in self.fragments
            for r, c, side in self.fragments)

    def invalidity_reasons(self):
        """Return reasons this region fails arc-separation or area rules."""
        reasons = []
        if not self.has_valid_arc_separation():
            reasons.append("The region contains both sides of an arc.")
        if not self.is_integer:
            reasons.append("The region has non-integer area: arc inside and outside counts differ.")
        return tuple(reasons)

    def determine_validity(self):
        """Check region geometry and exact area; clue scores are not checked."""
        return not self.invalidity_reasons()

    @property
    def constant(self):
        return self.whole_cells + self.arc_outsides

    @property
    def pi_quarters(self):
        return self.arc_insides - self.arc_outsides

    @property
    def is_integer(self):
        return self.arc_insides == self.arc_outsides

    @property
    def integer_area(self):
        return self.area if self.is_integer else None

    def determine_area(self):
        """Return an integer or an exact symbolic string, never a float."""
        if self.is_integer:
            return self.constant
        coefficient = abs(self.pi_quarters)
        term = "π/4" if coefficient == 1 else f"{coefficient}π/4"
        if self.constant == 0:
            return term if self.pi_quarters > 0 else f"−{term}"
        sign = "+" if self.pi_quarters > 0 else "−"
        return f"{self.constant} {sign} {term}"

    def determine_smooth_pieces(self, state):
        """Count smooth connected pieces of this region's entire perimeter."""
        boundary = []
        for r, c, side in sorted(self.fragments):
            cell = state["cells"][r][c]
            arc = cell["arc"]
            if arc and (r, c, 1 - side) not in self.fragments:
                boundary.append(arc_endpoints(r, c, arc))
            inside_edges = {"tl": "NW", "tr": "NE", "br": "SE", "bl": "SW"}
            for edge, on_border, endpoints in (
                ("N", r == 0, (((r, c), (1, 0)), ((r, c + 1), (-1, 0)))),
                ("S", r == state["rows"] - 1,
                 (((r + 1, c), (1, 0)), ((r + 1, c + 1), (-1, 0)))),
                ("W", c == 0, (((r, c), (0, 1)), ((r + 1, c), (0, -1)))),
                ("E", c == state["columns"] - 1,
                 (((r, c + 1), (0, 1)), ((r + 1, c + 1), (0, -1)))),
            ):
                owner = 0 if arc is None or edge in inside_edges[arc] else 1
                if on_border and side == owner:
                    boundary.append(endpoints)
        parent = list(range(len(boundary)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        corners = {}
        for index, endpoints in enumerate(boundary):
            for corner, tangent in endpoints:
                corners.setdefault(corner, []).append((index, tangent))
        for entries in corners.values():
            for i, (first, tangent) in enumerate(entries):
                for second, other in entries[i + 1:]:
                    if tangent == (-other[0], -other[1]):
                        parent[find(second)] = find(first)
        pieces = len({find(index) for index in range(len(boundary))})
        object.__setattr__(self, "smooth_pieces", pieces)
        return pieces

    def determine_score(self, state):
        """Store area times smooth perimeter pieces; invalid regions have no score."""
        pieces = self.determine_smooth_pieces(state)
        score = self.area * pieces if self.determine_validity() else None
        object.__setattr__(self, "score", score)
        return score

    def verify(self, state):
        """Verify separation, integer area, and every clue belonging to this region."""
        score = self.determine_score(state)
        if score is None:
            return False
        return all(state['cells'][r][c]['number'] in (None, score)
                   for r, c, side in self.fragments if side == 0)

    @classmethod
    def from_fragments(cls, region_id, fragments, state, invalid_arcs=()):
        fragments = frozenset(fragments)
        whole_cells = arc_insides = arc_outsides = 0
        for r, c, side in fragments:
            if state["cells"][r][c]["arc"] is None:
                whole_cells += 1
            elif side == 0:
                arc_insides += 1
            else:
                arc_outsides += 1
        return cls(region_id, fragments, whole_cells, arc_insides, arc_outsides,
                   frozenset(invalid_arcs))



def compute_answer_key(state):
    """Return majority-region scores and the sum of squared row/column sums."""
    regions = determine_regions(state)[0]
    unique = set(regions.values())
    invalid = [region for region in unique if not region.verify(state)]
    if invalid:
        raise ValueError(f'Cannot compute the answer: {len(invalid)} regions fail area, arc separation, or clue-score checks.')
    values = [[regions[(r, c, 0)].score for c in range(state['columns'])]
              for r in range(state['rows'])]
    rows = [sum(row) for row in values]
    columns = [sum(values[r][c] for r in range(state['rows'])) for c in range(state['columns'])]
    return {'values': values, 'row_sums': rows, 'column_sums': columns,
            'answer': sum(total * total for total in rows) + sum(total * total for total in columns)}



def determine_region_areas(state, regions=None):
    """Convenience view of the exact areas already stored on Region objects."""
    if regions is None:
        regions = determine_regions(state)[0]
    return {region.id: region.area for region in regions.values()}



def region_area_positions(state, regions):
    """Choose one interior label anchor per region, preferring roomy cells."""
    candidates = {}
    for (r, c, side), region in regions.items():
        cell = state["cells"][r][c]
        arc = cell["arc"]
        if arc is None:
            x, y, width, priority = .5, .5, .85, 3
            if cell["number"] is not None:
                y = .78
        else:
            # Reflect points from a top-left-centered quarter circle.
            offset = .30 if side == 0 else .86
            x = 1 - offset if arc in ("tr", "br") else offset
            y = 1 - offset if arc in ("bl", "br") else offset
            width, priority = (.55, 2) if side == 0 else (.26, 1)
        rank = (priority, cell["number"] is None)
        if region not in candidates or rank > candidates[region][0]:
            candidates[region] = (rank, (r, c, x, y, width))
    return {region: candidate[1] for region, candidate in candidates.items()}

