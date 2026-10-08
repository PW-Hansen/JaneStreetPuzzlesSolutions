"""Keep shared code independent of root entry points and their GUI setup."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest


class ImportStructureTests(unittest.TestCase):
    def test_project_import_graph_has_no_cycles(self):
        root = Path(__file__).resolve().parents[1]
        paths = list(root.glob('*.py')) + list((root / 'functions').glob('*.py'))
        modules = {'.'.join(path.relative_to(root).with_suffix('').parts): path
                   for path in paths}
        graph = {}
        for module, path in modules.items():
            imports = set()
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imports.add(node.module)
            graph[module] = imports.intersection(modules)
        visited = set()

        def visit(module, chain):
            self.assertNotIn(module, chain, ' -> '.join(chain + [module]))
            if module in visited:
                return
            for imported in sorted(graph[module]):
                visit(imported, chain + [module])
            visited.add(module)

        for module in graph:
            visit(module, [])

    def test_constant_paths_still_point_at_project_root(self):
        from functions import constants
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(constants.DEFAULT_STATE, root / 'puzzle_state.json')
        self.assertEqual(constants.DATA_DIRECTORY, root / 'grids')
        self.assertEqual(constants.SOLUTION_ORDER_PATH, root / 'solution_clue_analysis_order.json')
        self.assertEqual(constants.SAVED_STATES_DIRECTORY, root / 'saved states')

    def test_function_modules_do_not_import_root_modules(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = {path.stem for path in root.glob('*.py')}
        for path in (root / 'functions').glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name.split('.')[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imported = [(node.module or '').split('.')[0]]
                else:
                    continue
                with self.subTest(module=path.name, line=node.lineno):
                    self.assertFalse(forbidden.intersection(imported))

    def test_search_modules_import_without_loading_gui(self):
        root = Path(__file__).resolve().parents[1]
        script = (
            'import sys; '
            'import functions.incremental_analysis, functions.greedy_analysis, '
            'functions.local_conditionals, functions.solver_analysis; '
            'assert "puzzle_gui" not in sys.modules; '
            'assert "solve_puzzle" not in sys.modules; '
            'assert "tkinter" not in sys.modules'
        )
        result = subprocess.run([sys.executable, '-c', script], cwd=root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
