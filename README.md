# Jane Street February 2026 puzzle: Subtiles 2 — Python solver

A programmatic solution to [Subtiles 2](https://www.janestreet.com/puzzles/subtiles-2-index/), Jane Street's February 2026 monthly puzzle, with an interactive Tkinter interface and an automated solver.

This project is explicitly intended as practice with AI-assisted software development: building, refining, and testing a solver through iterative collaboration with an AI coding assistant.

## Getting started

Run `python puzzle_gui.py` to open the launcher. Enter a grid name and square size, or select an existing grid or saved state. New grids ask for a variable count; names start at `a`. Run `python puzzle_gui.py example` to open a named grid directly.

Run `python solve_full_puzzle.py` to solve the supplied full puzzle. It analyzes variables, overlays regions 12–16, then 11 down to 1, skipping regions complete in every candidate. It finishes with incomplete-region comparison and region completion, then independently validates clue values, region sizes, connectivity, and shape containment.

The result is saved to `saved states/full_puzzle/solved-full-puzzle.json`, ready to load in the GUI. The input grid is preserved. Use `--input` and `--output` to select other paths.

## Editing and analysis

Select a cell, enter an expression, and click **Set cell**. Right-click to include or exclude an equation; excluded equations remain visible on a light grey background. **Exclude all** affects only cells containing expressions. **Include all** restores them. The display-priority button switches between equations and values while preserving region colors.

Expressions support arithmetic, powers, `sqrt(...)`, `cbrt(...)`, and variable-base logarithms such as `log_c(a)`. Fractions, roots, and powers receive mathematical formatting. Grid cells have a minimum size of 40×40 pixels.

**Analyze valid values** starts with included clues using the fewest variables. It solves supported equations for positive integer cell values up to **max region size**, retaining correlated partial assignments and exact fractional variable values. Integer requirements are inferred from addition and subtraction; an integral `6*c`, for example, does not imply an integral `c`.

The analyzer handles rational linear and quadratic equations and supported square-root expressions. Derived roots are checked against the original clue. Unsupported clues are deferred until their variables are known; if progress stops, analysis reports the limitation without a brute-force fallback. A single complete assignment is applied automatically. Assignments and per-clue steps are saved in the grid's `analysis` field, with unknown variables stored as `null`.

**Check connectivity** rejects values appearing too often, then checks whether each value N can connect through blank cells within N cells. Other values block its paths. This also filters analytical assignments and updates the variable lists. Regions are checked independently.

## Region operations

The **Regions** section has buttons from 1 through max region size. Clicking K tests translations, rotations, and reflections of the K−1 shape as candidates for K. If a complete K+1 shape is available, it instead derives K shapes by removing one cell without disconnecting that shape. Clue conflicts and candidates requiring more than K cells to connect are rejected.

Clicking another region continues from every surviving candidate and its inherited assumptions. Only branches with identical full assignments and constraints merge. Clicking the current region starts a fresh search from included clues. A failed search retains previous candidates; original equations remain unchanged.

Each overlay also applies these checks:

- **Forced target growth:** add a blank adjacent to at least two target cells if excluding it makes a size-bounded connection impossible.
- **Neighbor connectivity:** use Dijkstra's algorithm to check that neighboring clues can still reach one another within their size limit.
- **Low-slack connections:** examine every disconnected target piece. If its shortest connection leaves at most one spare cell, branch over connecting paths within the remaining budget.
- **Forced neighbor growth:** test whether bordering regions must take adjacent blanks to connect and reach their required size. Deductions can cascade between neighbors. Growth is capped at three rounds per region; frontiers exceeding 10 candidate blanks are skipped. Cutoffs retain deductions and are reported without declaring a contradiction.

These checks prune partial candidates; they do not prove that all regions can be completed together.

**Compare incomplete regions** works downward, comparing each incomplete region with the next larger shape. At most one larger-shape cell may be omitted. It tests placements, forces cells shared by every supported placement, and restarts when new deductions appear. Partial larger shapes are also used conservatively, and contradictory branches are rejected.

**Attempt region completion** works upward through regions missing exactly one cell. It branches over legal final cells and checks whether each completed shape can be contained in successive higher regions, allowing rotations and reflections.

**Previous** and **Next** preview candidates. **Undo** and **Redo** restore searches and assumptions; a new search after undo clears redo history. Editing clues or variable values clears overlay history. Messages and elapsed time appear below the region controls. **Abort** cancels an active region operation while retaining previous results.

## Saving and resetting

Grid edits and analysis are saved automatically in `grids/<name>.json`. Buttons below the grid provide additional controls:

- **Save state:** save a named snapshot in `saved states/<grid name>/`.
- **Load state:** restore equations, variable analysis, overlay candidates, preview selection, and Undo/Redo history from a snapshot.
- **Reset to equations:** clear variable assignments, analysis, region deductions, and overlay history; re-include equations and prioritize their display. Equations, grid size, and variable count remain.
- **Print state:** choose one name for a grid image (`<name>.png` in the project folder) and a matching snapshot. Image capture uses Windows APIs and standard Python libraries.

## Code organization

- `puzzle_gui.py`: interface, launcher, and dialogs.
- `solve_full_puzzle.py`: command-line entry point and puzzle operation order.
- `functions/display_functions.py`: math rendering, region colors, and PNG capture.
- `functions/equations_functions.py`: expression evaluation and analytical solving.
- `functions/persistence_functions.py`: JSON validation, serialization, and migration.
- `functions/solve_functions.py`: shared solver workflow, candidate handling, snapshots, timing, and background operations.
- `functions/region_functions/`: connectivity, shape transformations, overlays, and cancellation.
- `tests/`: automated tests.

Run tests with `python -m unittest discover -s tests -q`.
