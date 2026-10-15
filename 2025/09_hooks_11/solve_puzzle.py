"""Run the three analyses on a named puzzle's initial_state and export solved_state."""
import argparse
from pathlib import Path

from functions.solver import solve_named_puzzle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', help='Named puzzle, e.g. full_puzzle')
    args = parser.parse_args(argv)
    try:
        result = solve_named_puzzle(Path(__file__).resolve().parent, args.name)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.exit(1, f'Solve failed: {exc}\n')
    except KeyboardInterrupt:
        parser.exit(130, 'Solve interrupted.\n')
    return 0 if result.status == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
