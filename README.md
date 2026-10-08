# Jane Street May 2026 puzzle: Arch Madness — Python solver

A Python solver and interactive Tkinter editor for [Arch Madness](https://www.janestreet.com/puzzles/arch-madness-index/), Jane Street's May 2026 monthly puzzle.

This project is practice with AI-assisted software development through iterative collaboration with an AI coding assistant.

## Getting started

Requires Python with Tkinter and Pillow. Install the dependency, then open the editor:

```sh
python -m pip install -r requirements.txt
python puzzle_gui.py
```

The launcher asks for a puzzle name and grid size. Enter `9` for a square or `8x12` for eight rows and twelve columns. The name identifies the saved grid; reopen it with `python puzzle_gui.py example`. Grid dimensions are fixed after creation.

To open or solve the supplied puzzle:

```sh
python puzzle_gui.py full_puzzle
python solve_puzzle.py full_puzzle
python solve_puzzle.py full_puzzle -greedy
```

The solver requires and preserves `saved states/<name>/initial_state.json`. It defaults to dynamic ordering with weights **0.8, 0.5, 0.75**. Use `--set` for the puzzle's order in `solution_clue_analysis_order.json`, or `--custom-weights` to enter weights in a popup. These flags are mutually exclusive; either works with `-greedy`.

```sh
python solve_puzzle.py full_puzzle --set -greedy
python solve_puzzle.py full_puzzle --custom-weights
```

On my PC, the full puzzle takes approximately **25 seconds with dynamic ordering and `-greedy`**, **3 seconds with set ordering and `-greedy`**, and **500 seconds non-greedily**. Timings vary with the machine and settings.

## Puzzle rules

Place at most one unit-radius, 90-degree arc in each white cell, connecting opposite corners. Green cells cannot contain arcs. The arcs and grid boundary divide the board into regions. Every region must have integer area, and the two sides of each arc must belong to different regions.

A region's score is its area multiplied by the number of distinct continuously differentiable, or **smooth**, pieces in its perimeter. A clue specifies the score of the region containing at least half of its cell. Different clues can share a region only when their values agree.

After completing the grid, fill every unnumbered cell with its majority region's score. **Compute answer key** validates the grid, displays those scores, and calculates the sum of the squares of the row sums **plus** the sum of the squares of the column sums. The command-line solver also prints the answer when it verifies a completed grid.

## Editing the grid

The editor opens in selection mode. Use the toolbar or these shortcuts:

| Shortcut | Mode | Action |
| --- | --- | --- |
| Ctrl+0 | Select | Select cells without changing marks. |
| Ctrl+1 | Green cells | Click to toggle a green cell. |
| Ctrl+2 | Digits | Select a cell and type its clue. |
| Ctrl+3 | Arcs | Click to cycle through four arc orientations, then no arc. |
| Ctrl+4 | Map | Inspect and edit permitted arc configurations. |

Pressing the shortcut for the current editing mode returns to selection mode. Escape clears the selection; arrow keys move it. Backspace edits a clue. Right-click or Delete clears the current mode's mark. Digits and arcs can coexist; making a cell green removes its arc.

Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z. Ctrl+S saves the grid.

Map mode shows four arcs and a central no-arc option. Toggle possibilities using the checkboxes or right-clicking the miniatures; at least one must remain. Future searches respect these exclusions and existing marks.

## Clue analysis and deductions

**Factorization** lists possible area × perimeter-piece combinations. **Analyze selected clue** grows its region, rejecting contradictions and area or confirmed perimeter discontinuities incompatible with those factors. Completed candidates require integer area, the correct score, and compatible clues.

Search stops after finding more than 25 accepted states, or when aborted. Completed searches apply a unique state or configurations shared by all states, retaining proven exclusions. Untested cells outside a candidate region remain unrestricted.

The analysis options are:

- **Simplify arcs:** reduce five choices to three in undecided non-clue cells, initially counting them as half a cell. Fixed arcs retain exact area; completed candidates are resolved and checked with actual arcs. Growth beyond the second-highest permitted area switches back to regular arcs.
- **Prioritize cells:** favor constrained frontier cells, with bonuses for neighboring green cells, neighboring clues, the grid edge, and each adjacent cell already in the partial region.
- **Check other clues:** run bounded searches using simplified arcs when another clue becomes sufficiently constrained. Cutoffs do not prove contradictions.

Completed searches with multiple states run sanity checks on neighboring clues, with a separate 2,500-branch limit per check. Cutoffs retain candidates; single-state results skip these checks.

**Scan local conditionals (3 cells)** finds nearby incompatibilities and cascading implications, shown for the selected cell in the right-hand panel. **Wipe local conditionals** removes rules while preserving arcs and exclusions.

Completed searches with fewer than 25 states save their candidates. Blue rings identify clues with multiple saved states. Selecting one loads its candidates at **State 0 — confirmed grid**; Previous/Next previews blue speculative arcs over black confirmed arcs. Incompatible placed arcs invalidate saved candidates.

**Abort analysis** stops the search. Timers remain visible after completion. The console reports clue starts, rejected candidates, and separate main-search and sanity-check timings and branch counts.

## Greedy search

The greedy search adds two restrictions:

1. **Every region has at least three distinct continuously differentiable perimeter pieces.** I am quite confident this restriction is true, but cannot prove it conclusively. It rules out factorizations with fewer than three pieces: for example, a 25-clue cannot grow beyond area 5 under this assumption.
2. **A region has only one uninterrupted connection with the grid edge.** This is not universally true, but is a useful assumption, especially for smaller regions. Grid corners do not interrupt that connection.

At the boundary, greedy search tries the longest permitted contact with an even number of unit cell borders, then shorter contacts if needed. It adds whole-cell area for claimed no-arc cells and respects exclusions for terminating arcs, grouping equivalent arcs when simplification is enabled.

**Analyze selected clue (greedy)** previews candidates without committing deductions. The command-line `-greedy` option permits provisional deductions throughout a solve.

If greedy search fails, the solver retries that clue and future clues non-greedily. Further failure restores the state before the latest successful greedy search and retries from there, cascading backward if necessary. Completed grids must pass region and clue verification.

## Analyzing all clues

Both batch buttons start by scanning local conditionals:

- **Analyze all clues (dynamic order)** asks for weights per nearby conditional, grid-edge contact, and adjacent green cell or being green. Defaults are **0.8, 0.5, 0.75**. Multiply the clue value by applicable weights; lower scores go first. Recompute after each analysis.
- **Analyze all clues (set order)** reads the current puzzle's entry in `solution_clue_analysis_order.json`: one-based `row`, `column`, and expected `clue`. The supplied order starts with the edge 9s, beginning at r3c9. Edit this file to change or add orders.

Passes repeat until the grid is complete or a pass places no new arcs. Total time freezes at completion and is printed to the console.

## Region operations

- **Check smooth arcs** colors arcs that join smoothly together, separating non-smooth connections.
- **Determine regions** colors separated regions. A region containing both sides of an arc is left uncolored.
- **Compute region areas** displays exact areas inside the grid. Each region counts whole cells, arc insides of area π/4, and arc outsides of area 1−π/4. Equal inside and outside counts give integer area without floating-point comparisons.
- **Compute scores** displays area × smooth perimeter-piece count.
- **Verify regions** colors valid regions green and invalid regions grey, checking arc separation, integer area, and clue scores.
- **Clear colors** removes analysis colors and labels.

## Saving, exporting, and resetting

Named grids autosave to `grids/<name>.json`. **Save state** creates a named snapshot in `saved states/<name>/`; **Load state** restores a snapshot for that puzzle. Snapshots preserve deductions, saved candidates, and editor state as well as the grid.

**Print state** asks for a name and exports a PNG in the project root, plus a matching saved-state snapshot.

The command-line solver writes progress to `saved states/<name>/checkpoint_state.json`. Only a complete, validated grid is written to `saved states/<name>/solved_state.json`. Both can be loaded through the GUI. Greedy checkpoints may contain provisional deductions.

**Reset arcs** removes arcs and clears learned exclusions, conditionals, and saved analysis candidates while preserving clues and green cells.

## Code organization and tests

- `puzzle_gui.py`: Tkinter interface, grid geometry, regions, rendering, persistence, and shared puzzle utilities.
- `solve_puzzle.py`: command-line solving, ordering, reporting, and checkpoint output.
- `solution_clue_analysis_order.json`: named fixed clue orders.
- `functions/`: incremental and greedy searches, conditional propagation, local scans, sanity checks, and greedy rollback scheduling.
- `tests/`: automated regression tests.
- `grids/` and `saved states/`: working grids and named snapshots.

Run the test suite from the project root:

```sh
python -m unittest discover -s tests
```
