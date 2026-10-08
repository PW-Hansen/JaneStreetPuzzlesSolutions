# Jane Street May 2026 puzzle: Arch Madness — Python solver

A Python solver and interactive Tkinter editor for [Arch Madness](https://www.janestreet.com/puzzles/arch-madness-index/), Jane Street's May 2026 monthly puzzle.

This project is intended as practice with AI-assisted software development: building, testing, and refining a puzzle solver through iterative collaboration with an AI coding assistant.

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

The command-line solver requires `saved states/<name>/initial_state.json`; it reports an error if that initial state is missing. It preserves the initial state. By default, it uses dynamic ordering with weights **0.8, 0.5, 0.75**. Add `--set` to use a specific clue analysis order determined in `solution_clue_analysis_order.json` or `--custom-weights` to enter dynamic weights in a popup window. These two ordering flags are mutually exclusive; either can be combined with `-greedy`.

```sh
python solve_puzzle.py full_puzzle --set -greedy
python solve_puzzle.py full_puzzle --custom-weights
```

On my PC, solving the full puzzle takes approximately **25 seconds with dynamic ordering and `-greedy`**, approximately **3 seconds with set ordering and `-greedy`**, and approximately **500 seconds with the non-greedy search**. These are observed timings for this puzzle and machine, rather than guarantees for other puzzles or settings.

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

Undo and redo are available through buttons, Ctrl+Z, Ctrl+Y, and Ctrl+Shift+Z. Ctrl+S saves the grid.

Map mode shows the four possible arcs and a central no-arc option. Toggle possibilities with the selected-cell checkboxes or by right-clicking their miniature representations. At least one option must remain. Drawn arcs and green cells constrain their cells; manual exclusions are considered by future searches.

## Clue analysis and deductions

**Factorization** lists the selected clue's possible area × perimeter-piece combinations. **Analyze selected clue** incrementally grows its partial region, rejecting contradictions, excessive area, and confirmed perimeter discontinuities that cannot fit any permitted factorization. Completed candidates must have exact integer area, the correct score, and compatible clues.

The search stops early after finding more than 25 accepted states, or when aborted. Completed searches apply a unique accepted state automatically; with multiple accepted states, they apply shared configurations and retain proven exclusions. Untested cells outside a candidate region are not treated as excluded configurations.

The analysis options are:

- **Simplify arcs:** group equivalent ways of extending a region through an undecided non-clue cell, reducing five choices to three. Such cells initially contribute half a cell; determined arcs retain their exact area. Completed candidates are resolved into actual arcs and checked. Growth beyond the second-highest permitted area switches back to regular arcs.
- **Prioritize cells:** favor constrained frontier cells, with bonuses for neighboring green cells, neighboring clues, the grid edge, and each adjacent cell already in the partial region.
- **Check other clues:** run bounded secondary searches when another clue becomes sufficiently constrained. These searches also use simplified arcs; an inconclusive cutoff does not prove a contradiction.

After a completed search with multiple accepted states, sanity checks test clues neighboring each candidate region. Each neighboring-clue check currently has its own 2,500-branch limit; reaching it retains the candidate. Sanity checks are skipped for a single accepted state. The console reports rejected candidates and separates main-search and sanity-check timings and branch counts.

**Scan local conditionals (3 cells)** looks for nearby incompatibilities and implications across the clues. Conditions cascade as configurations are excluded or fixed. The right-hand panel lists conditions involving the selected cell. **Wipe local conditionals** removes those rules while preserving arcs and excluded configurations.

Completed searches with fewer than 25 accepted states save their candidates. A small blue ring identifies clues with multiple saved states. Selecting one loads its candidates and first returns to **State 0 — confirmed grid**. Previous/Next previews alternatives with blue speculative arcs; confirmed arcs remain black. Placing an incompatible arc removes invalidated saved candidates.

**Abort analysis** stops the active search. Search and batch timers remain visible after completion. The console prints when each clue starts and how long its analysis took.

## Greedy search

The greedy search adds two restrictions:

1. **Every region has at least three distinct continuously differentiable perimeter pieces.** I am quite confident this restriction is true, but cannot prove it conclusively. It rules out factorizations with fewer than three pieces: for example, a 25-clue cannot grow beyond area 5 under this assumption.
2. **A region has only one uninterrupted connection with the grid edge.** This is not universally true, but is a useful assumption, especially for smaller regions. Grid corners do not interrupt that connection.

When a region reaches the boundary, the greedy search tries the longest permitted continuous contact first, requiring an even number of unit cell borders along the grid edge. It claims eligible no-arc boundary cells, including their whole-cell area, and tests terminating arcs against known exclusions. Disproved endpoints lead to shorter contacts. Equivalent endpoint arcs remain grouped when simplification is enabled.

The GUI's **Analyze selected clue (greedy)** button previews candidates under these assumptions without committing ordinary confirmed deductions. The command-line `-greedy` option instead permits provisional deductions throughout a solve.

If a greedy search fails, the solver retries that clue non-greedily and uses non-greedy searches thereafter. If that also fails, it restores the state before the most recent successful greedy search and retries from that clue. This rollback can cascade through earlier greedy decisions. A completed grid must still pass region and clue verification before being saved as solved.

## Analyzing all clues

Both batch buttons start by scanning local conditionals:

- **Analyze all clues (dynamic order)** asks for ordering weights: per nearby conditional, bordering the grid edge, and per adjacent green cell or being in a green cell. Defaults are **0.8, 0.5, 0.75**. A clue's value is multiplied by the applicable weights; lower scores go first. Scores are recomputed after each analysis.
- **Analyze all clues (set order)** loads the entry for the current puzzle name from `solution_clue_analysis_order.json`. Entries specify one-based `row`, `column`, and the expected `clue` value. The supplied `full_puzzle` order begins with the edge 9s, starting at r3c9. Edit the JSON file to change or add an order.

The command-line solver uses the same ordering choices. Passes repeat while new arcs are placed and the grid remains incomplete; a pass with no new arcs stops the process. Total elapsed time freezes when analysis ends and is printed to the console.

## Region operations

- **Check smooth arcs** colors arcs that join smoothly together, separating non-smooth connections.
- **Determine regions** colors separated regions. A region containing both sides of an arc is left uncolored.
- **Compute region areas** displays exact areas inside the grid. Each region counts whole cells, arc insides of area π/4, and arc outsides of area 1−π/4. Equal inside and outside counts give integer area without floating-point comparisons.
- **Compute scores** displays area × smooth perimeter-piece count.
- **Verify regions** colors valid regions green and invalid regions grey, checking arc separation, integer area, and clue scores.
- **Clear colors** removes analysis colors and labels.

## Saving, exporting, and resetting

Named grids autosave to `grids/<name>.json`. **Save state** creates a named snapshot in `saved states/<name>/`; **Load state** restores a snapshot for that puzzle. Snapshots preserve deductions, saved candidates, and editor state as well as the grid.

**Print state** asks for a file name and exports a PNG in the project root, along with a matching saved-state snapshot. Rendering uses Pillow rather than a screenshot of the window.

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
