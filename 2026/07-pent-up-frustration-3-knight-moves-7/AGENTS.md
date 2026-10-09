# Project rules

These rules apply throughout this repository. They describe how to organize and develop the project; they do not prescribe puzzle behavior or application features.

## File structure and responsibilities

- Keep automated tests in `tests/` and reusable application code in `functions/`.
- Keep executable entry points, such as `puzzle_gui.py` and command-line solver scripts, in the project root.
- Split modules in `functions/` by responsibility. Create a suitable module or subpackage when code does not fit an existing one.
- Keep `puzzle_gui.py` focused on GUI construction, user interaction, and calling shared functions. Do not implement backend functionality there: define it in an appropriate module under `functions/` and call it from the GUI.
- Put shared constants in `functions/constants.py`.

## Dependencies and shared logic

- Root entry points may import from `functions/`. Modules under `functions/` must not import root entry points or other project code outside `functions/`.
- Keep the project import graph free of mutual imports and longer import cycles. Moving an import inside a function does not make a cycle acceptable.
- Keep backend modules independent of GUI initialization so they can be used by command-line entry points and tests.
- Implement functionality shared by the GUI and command-line solver once, under `functions/`. This includes shared workflow and reporting logic.

## Configuration and generalization

- Keep puzzle-specific names, dimensions, and operation orders in input data or configuration rather than hard-coding them in GUI or shared application logic.
- Implement general rules rather than special cases tailored to an example supplied by the user.

## Development practices

- Keep changes within the requested scope and preserve existing behavior outside that scope.
- Respect deliberate reversions and prior user decisions. Do not reintroduce removed behavior without a new instruction to do so.
- Before claiming an optimization, compare representative workflows before and after the change. Consider runtime and added overhead, rather than relying only on fewer search branches or operations.
- Run checks appropriate to the change. For visual changes, inspect the resulting interface or exported artifact rather than relying only on code inspection.
- Do not remove any code unless instructed to do so. If a change renders existing code redundant, simply report it.
- Keep documentation concise and accurate. Update affected usage instructions, configuration descriptions, and measured runtime claims when relevant.
