"""Region algorithms independent of the GUI."""

from .cancellation import (
    _region_work,
    RegionOperationAborted,
    check_region_abort
)

from .connectivity import (
    max_region_size,
    minimum_region_size,
    can_connect_region,
    check_grid_connectivity
)

from .shapes import (
    shape_orientations,
    reverse_overlay_orientations,
    canonical_shape,
)

from .overlays import (
    InvalidOverlay,
    force_overlay_neighbors,
    bordering_regions_reachable,
    force_bordering_growth,
    low_slack_connections,
    find_region_overlays,
    compare_incomplete_regions,
    attempt_region_completions,
    continue_region_overlays
)
