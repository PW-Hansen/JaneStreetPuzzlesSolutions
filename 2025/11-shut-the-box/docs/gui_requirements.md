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
- Undo/redo history should be wiped when the GUI is closed.

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

- **Digit Entering**: Allow for centering digits into cells.
- **Arrow Entering**: Allow for arrows to be placed (or removed, if alreadyu placed) into cells. There should be up to four arrows in a box, pointing in each cardinal direction. Which arrow is placed into a cell when clicking should depend on where the cell is clicked. If it would be sliced into quarters along the two diagonals, clicking on the north-facing slice should place (or remove) a north-facing arrow.
- **Circle/Square**: Clicking on a cell in this mode should cycle between blank, a grey circle, and a grey square. Use the same shade of grey for the two.
- **Shading**: Clicking on a cell in this mode should cycle between no shading, light grey shading, and light green shading.

It should not be possible to enter arrows into a cell that already has a digit, a circle, or a square. However, digit can coexist with a square or a circle, but the digit should be displayed on top if so. Shading should be compatible with all other input, but should be the lowest layer. Furthermore, the grey used for the shading should be lighter than the grey used for circles/squares.
