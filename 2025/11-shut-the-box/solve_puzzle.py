"""Command-line entry point for the shared named-puzzle solver workflow."""
import argparse
from pathlib import Path
from functions.storage import Storage
from functions.solver import solve_named_puzzle


def main():
    parser = argparse.ArgumentParser(description='Solve a named puzzle from its initial state.')
    parser.add_argument('name', help='Named puzzle, e.g. puzzle')
    parser.add_argument('row', nargs='?', type=int, help='One-based anchor row')
    parser.add_argument('column', nargs='?', type=int, help='One-based anchor column')
    args = parser.parse_args()
    if (args.row is None) != (args.column is None):
        parser.error('Supply both anchor row and column, or neither.')
    coordinates = None if args.row is None else (args.row, args.column)
    try:
        result = solve_named_puzzle(Storage(Path(__file__).resolve().parent), args.name,
                                    anchor_coordinates=coordinates)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f'Solve failed: {exc}\n')
    except KeyboardInterrupt:
        parser.exit(130, 'Solve interrupted.\n')
    return 0 if result.status == 'solved' else 2


if __name__ == '__main__':
    raise SystemExit(main())
