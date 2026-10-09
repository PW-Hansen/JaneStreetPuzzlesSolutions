# Universal GUI requirements

These requirements establish the common GUI behavior for grid-based Jane Street puzzle projects. Puzzle-specific cell contents, editing modes, deductions, and solving rules are defined separately.

## Grid and layout

- Use a Python Tkinter GUI with the puzzle grid as the primary workspace.
- Draw a thick black outer grid border and clearly visible internal cell boundaries. Support puzzle-specific borders and markings where required.
- Read grid dimensions from the named puzzle's data. Ask for dimensions when creating a new puzzle; do not expose resizing as an ordinary editing control.
- Give cells a minimum readable size. Keep labels, symbols, and markings legible and aligned with their cells.
- Keep the grid and controls visible at the initial window size. Wrap or scroll supporting text as needed so growing status messages do not shrink the grid or hide controls.
- Group controls by purpose. Put general save/load and reset controls below the grid, and analysis controls and details in a separate area beside it.
- Distinguish selected cells, confirmed contents, speculative previews, and analysis highlights visually. Changing a display preference must preserve unrelated markings and colors.

## Named puzzles and launch behavior

- Running `python puzzle_gui.py` opens a launcher for creating a named puzzle or opening an existing puzzle or saved state.
- Creating a puzzle asks for its name and dimensions.
- Running `python puzzle_gui.py <name>` opens that named puzzle directly.
- Use the selected puzzle name consistently for data, saved states, and configuration. Opening an existing puzzle restores its stored setup without asking for it again.

## Selection and interaction modes

- Provide explicit modes that determine how mouse and keyboard interaction affects a cell. The available editing modes depend on the puzzle.
- Always provide a null mode, labeled **Select**, that allows selecting and inspecting cells without changing their contents. Open the GUI in this mode.
- Show the active mode clearly and provide visible controls for changing it.
- Use `Ctrl+0` for Select mode and `Ctrl+1`, `Ctrl+2`, and subsequent numbered shortcuts for editing modes. Activating the current editing mode again returns to Select mode.
- Keep selection separate from editing. Highlight the selected cell, use arrow keys to move selection, and use Escape to clear it.
- Define left-click, right-click, typing, Backspace, and Delete behavior for each editing mode. Clearing or toggling actions affect only the content associated with that mode unless puzzle rules require another change.
- In Select mode, right-click, typing, Backspace, and Delete must not edit the puzzle.
- Allow different kinds of cell content to coexist where the puzzle permits it. Selecting one editing mode must not implicitly erase another kind of content.

## Persistence and saved states

- Automatically save edits to the named working puzzle and restore them when it is reopened.
- Store working puzzles under `grids/<name>.json` and named snapshots under `saved states/<name>/`.
- Provide **Save state** and **Load state** controls. Saving asks for a snapshot name; loading presents saved states belonging to the current puzzle.
- Save enough information to resume the same work, including puzzle data, confirmed edits, deductions, analysis candidates, preview selection, and undo/redo history where applicable.
- Keep named snapshots separate from the automatically saved working puzzle.
- Report load and save failures clearly without replacing the current state with a partial or invalid load.
- Provide **Print state** to export the displayed grid as a PNG and save a matching snapshot using the same entered name. Place the PNG in the project root.

## Undo, redo, and reset

- Provide undo and redo for manual edits and analysis operations that change puzzle state.
- Support `Ctrl+Z` for undo and `Ctrl+Y` or `Ctrl+Shift+Z` for redo.
- Treat a user action and its resulting deductions as one coherent operation. Undo must restore the associated data and analysis state, not just the visible grid.
- Making a new change after undo clears the redo history.
- Provide clearly labeled reset actions appropriate to the puzzle. Preserve the puzzle's identity, dimensions, and original clues while clearing the edits or derived information named by the action.
- Invalidate or recompute derived information when an edit makes it incompatible with the current puzzle.

## Analysis and feedback

- Keep the GUI responsive during long operations and provide an **Abort** control.
- Show which operation or cell is being analyzed and display elapsed time during the operation. Keep the final elapsed time visible and stop the timer when the operation finishes or is aborted.
- Present completion, failure, cancellation, and search-limit outcomes distinctly. An incomplete search must not be presented as a conclusive result.
- Where an operation produces alternative candidates, provide Previous/Next navigation and a confirmed-state view with no speculative additions.
- Previewing a candidate must not commit it to the puzzle. Keep speculative contents visually distinct from confirmed contents.
- Display concise status messages near the relevant controls. Console reporting should summarize useful progress and outcomes without flooding the output with individual internal checks.

## Documentation and verification

- Document the available modes, shortcuts, launch commands, storage locations, and the scope of reset actions.
- Verify that reopening and snapshot loading restore the intended state, and that undo/redo works across both edits and analysis changes.
- Inspect the actual GUI and exported PNGs for readability, clipping, alignment, and correct rendering.

# Puzzle-specific GUI requirements

## Modes

- **Score:** Allow entering a score value into a cell. Accept integers only.
- **Cell border drawing:** Clicking an edge shared by two orthogonally adjacent cells toggles that border between thin and thick. Thick cell borders use the same thickness as the outer grid border.
- **Visit number:** Allow entering a visit number into a cell. Accept integers only. Store this value separately from the cell's score so both can coexist.
- **Tower:** Allow marking or unmarking a cell as a tower. Each region requires exactly one tower, as specified in `docs/rules.md`; do not permit placing a second tower in a region that already has one. Tower markings coexist with scores and visit numbers.
- In Tower mode, upper-half clicks retain the tower toggle behavior; lower-half clicks toggle a non-tower designation. Right-click clears the designation associated with that half.

## Cell contents

- Unless otherwise specified, display the score in the middle of the cell and the visit number as a smaller number in the top right corner.
- While Visit number mode is active, display the visit number in the middle of the cell and the score as a smaller number in the top left corner.
- Switching modes changes the placement and size of the displayed values without changing the values themselves.
- Mark each tower with a thin black horizontal bar at the top of its cell, just below its northern border. The bar remains visible in every mode and is distinct from the cell border.
- Mark each confirmed non-tower with a thin black horizontal line near the bottom of the cell, visible in every mode.

## Tower-mode shading

- Determine regions using orthogonal cell connectivity, with thick internal borders separating regions and the outer grid border enclosing the board.
- Only while Tower mode is active, shade cells as follows:
  - **Blue:** the cell contains a tower.
  - **Light green:** the cell's region has no tower, so the cell could contain that region's tower.
  - **Light grey:** the cell does not contain a tower, but its region already contains one.
  - Explicitly designated or deduced non-towers are also light grey, even when their region's tower has not yet been located.
- Give blue shading precedence for tower cells within a region that has a tower.
- Recompute tower-mode shading when tower markings or region borders change.
- Leaving Tower mode removes this mode's shading while preserving tower bars, cell values, borders, and unrelated visual markings.

## Tower deductions

- Designating a tower immediately marks all other cells in its region as non-towers.
- If all but one cell of a region are non-towers, designate the remaining cell as its tower.
- Apply these deductions through shared backend operations for manual edits and analysis alike. Save the resulting markings and include the initiating action and its deductions in one undo operation.
- Reject contradictions without partially changing the grid. Recompute deductions when explicit markings or borders change.

## Retained continuation paths

- Retain multiple valid paths found by Continue path while applying their shared deductions.
- Check retained alternatives after grid edits. When only one is still possible, automatically apply its scores, visit numbers, and tower information in the same undoable action.
- After eliminating alternatives, also apply any new deductions shared by every remaining path, even when more than one path remains.
- Display remaining alternative counts and report when no retained alternative remains possible.
- Preserve alternatives in autosaves, snapshots, and undo/redo. Resetting visits clears them.

## Valid path combinations

- Add **Find valid combinations** beneath Continue path. Check combinations choosing one alternative from every retained group, independent of the selected cell.
- Reject conflicting cell visits or values, incompatible tower states, multiple towers in a region, and combinations leaving all cells in a region as non-towers. A shared endpoint with the same visit, score, and tower state represents one visit and is permitted.
- Report the number of valid combinations, retain them together for later checks, and apply deductions shared by all combinations as one undoable, automatically saved action.
- Allow aborting without applying partial results. Reject stale results. If no combination is valid, report it and leave the grid and retained paths unchanged.
- When a combination supplies a continuous path from visit 0 through its current endpoint, also require that the path can continue to visit every region's tower. Check legal knight moves, integer arithmetic, known cell information, and the prohibition on revisiting cells. Separate fragments do not establish the current endpoint and must not be rejected as completed paths.

## Attempt tower placements

- Add **attempt tower placements** beneath Find valid combinations, independent of the selected cell.
- In each region without a confirmed tower, temporarily assert each unknown cell as a tower. Check whether at least one combination of all retained path groups remains valid, including visit conflicts and region tower constraints.
- Mark impossible placements as non-towers and apply resulting tower/path deductions in one undoable, automatically saved action. Leave possible placements unknown unless deductions confirm them.
- Report candidate counts and rejected cells. Allow aborting without applying partial results and reject stale results or an already inconsistent set of retained paths.
- Without retained paths, check region constraints only. A surviving trial establishes compatibility with the retained information, rather than proving a full puzzle solution.
