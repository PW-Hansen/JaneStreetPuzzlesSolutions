"""Safe expression evaluation and analytical variable solving."""

import ast
import operator
import re
from decimal import Decimal, localcontext
from fractions import Fraction
from math import isqrt


def variable_name(index):
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("a") + remainder) + name
    return name


def clue_variables(expression, names):
    tree = ast.parse(expression.replace("^", "**"), mode="eval")
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in names:
                used.add(node.id)
            elif node.id.startswith("log_") and node.id[4:] in names:
                used.add(node.id[4:])
            elif node.id not in ("sqrt", "cbrt") and not re.fullmatch(r"log_\d+", node.id):
                raise ValueError(f"Unknown variable: {node.id}")
    return used


def solve_rational_clue(expression, unknown, known, limit):
    """Solve a univariate rational expression for each permitted cell integer.

    Return None for forms requiring the bounded per-clue fallback.
    """
    tree = ast.parse(expression.replace('^', '**'), mode='eval').body
    def square_root(node):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'sqrt' and len(node.args) == 1 and not node.keywords)
    if square_root(tree) or (isinstance(tree, ast.BinOp) and isinstance(tree.op, ast.Div)
                             and (square_root(tree.left) or square_root(tree.right))):
        solutions = set()
        for target in range(1, limit+1):
            if square_root(tree):
                equation = f'({ast.unparse(tree.args[0])})-({target}^2)'
            elif square_root(tree.left):
                equation = f'({ast.unparse(tree.left.args[0])})-({target}^2)*({ast.unparse(tree.right)})^2'
            else:
                equation = f'({ast.unparse(tree.left)})^2-({target}^2)*({ast.unparse(tree.right.args[0])})'
            roots = solve_rational_clue(f'({equation})+1', unknown, known, 1)
            if roots is None:
                return None
            for root in roots:
                try:
                    if evaluate(expression, dict(known, **{unknown:root})) == target:
                        solutions.add(root)
                except (ValueError, ArithmeticError):
                    pass
        return solutions
    def add(a, b, sign=1):
        result = dict(a)
        for degree, coefficient in b.items():
            result[degree] = result.get(degree, 0) + sign*coefficient
        return {degree: coefficient for degree, coefficient in result.items() if coefficient}
    def multiply(a, b):
        result = {}
        for i, x in a.items():
            for j, y in b.items():
                if i+j > 40:
                    raise ValueError("Polynomial degree too large")
                result[i+j] = result.get(i+j, 0)+x*y
        return {degree: coefficient for degree, coefficient in result.items() if coefficient}
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return {0: Fraction(str(node.value))}, {0: Fraction(1)}
        if isinstance(node, ast.Name):
            if node.id == unknown:
                return {1: Fraction(1)}, {0: Fraction(1)}
            return {0: Fraction(known[node.id])}, {0: Fraction(1)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            numerator, denominator = visit(node.operand)
            return ({degree: -value for degree, value in numerator.items()}
                    if isinstance(node.op, ast.USub) else numerator), denominator
        if not isinstance(node, ast.BinOp):
            raise ValueError("Unsupported symbolic form")
        if isinstance(node.op, ast.Pow):
            exponent = evaluate(ast.unparse(node.right), known)
            if exponent.denominator != 1 or abs(exponent) > 20:
                raise ValueError("Unsupported symbolic power")
            numerator, denominator = visit(node.left)
            if exponent < 0:
                numerator, denominator = denominator, numerator
            result_n, result_d = {0: Fraction(1)}, {0: Fraction(1)}
            for _ in range(abs(int(exponent))):
                result_n, result_d = multiply(result_n, numerator), multiply(result_d, denominator)
            return result_n, result_d
        a, b = visit(node.left)
        c, d = visit(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            return add(multiply(a, d), multiply(c, b), -1 if isinstance(node.op, ast.Sub) else 1), multiply(b, d)
        if isinstance(node.op, ast.Mult):
            return multiply(a, c), multiply(b, d)
        if isinstance(node.op, ast.Div):
            return multiply(a, d), multiply(b, c)
        raise ValueError("Unsupported symbolic operator")
    try:
        numerator, denominator = visit(ast.parse(expression.replace('^', '**'), mode='eval').body)
        solutions = set()
        for target in range(1, limit+1):
            polynomial = add(numerator, {degree: target*value for degree, value in denominator.items()}, -1)
            degree = max(polynomial, default=-1)
            if degree < 0 or degree > 2:
                return None
            if degree == 0:
                continue
            if degree == 1:
                solutions.add(-polynomial.get(0, 0)/polynomial[1])
            else:
                a, b, c = polynomial[2], polynomial.get(1, 0), polynomial.get(0, 0)
                discriminant = b*b-4*a*c
                if discriminant < 0:
                    continue
                n, d = isqrt(discriminant.numerator), isqrt(discriminant.denominator)
                if n*n == discriminant.numerator and d*d == discriminant.denominator:
                    root = Fraction(n, d)
                    solutions.update(((-b-root)/(2*a), (-b+root)/(2*a)))
        return solutions
    except (ValueError, KeyError, ArithmeticError):
        return None


def inferred_integer_variables(expression, known):
    """An integral sum/difference with an integral operand forces the other operand integral."""
    inferred = set()
    tree = ast.parse(expression.replace('^', '**'), mode='eval').body
    def integer(node):
        try:
            return evaluate(ast.unparse(node), known).denominator == 1
        except (ValueError, ArithmeticError):
            return False
    def require_integer(node):
        if isinstance(node, ast.Name):
            inferred.add(node.id)
        elif isinstance(node, ast.UnaryOp):
            require_integer(node.operand)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            if integer(node.left): require_integer(node.right)
            if integer(node.right): require_integer(node.left)
    require_integer(tree)
    return inferred


def analyze_clues(expressions, names, limit):
    """Solve included clues in variable-count order, without bounded enumeration."""
    names = list(names)
    clues = sorted([(expression, clue_variables(expression, names)) for expression in expressions],
                   key=lambda clue: len(clue[1]))
    assignments = [{name: None for name in names}]
    notes = []
    pending = list(clues)
    while pending and assignments:
        ready = None
        for i, (clue, used) in enumerate(pending):
            solvable = True
            for assignment in assignments:
                unknowns = [name for name in used if assignment[name] is None]
                if len(unknowns) > 1:
                    solvable = False
                    break
                if unknowns:
                    known = {name:value for name,value in assignment.items() if value is not None}
                    if solve_rational_clue(clue, unknowns[0], known, limit) is None:
                        solvable = False
                        break
            if solvable:
                ready = i
                break
        if ready is None:
            raise ValueError('More information is needed to solve these coupled clues analytically: ' +
                             ', '.join(expression for expression, _ in pending))
        expression, used = pending.pop(ready)
        survivors = {}
        for assignment in assignments:
            unknowns = [name for name in used if assignment[name] is None]
            unknown = unknowns[0] if unknowns else None
            known = {name:value for name,value in assignment.items() if value is not None}
            integer_required = inferred_integer_variables(expression, known)
            candidates = [None] if unknown is None else solve_rational_clue(expression, unknown, known, limit)
            if candidates is None:
                raise ValueError(f'Cannot yet solve {expression} analytically; no brute-force fallback is used.')
            for candidate in sorted(candidates) if unknown is not None else candidates:
                updated = dict(assignment)
                if unknown is not None:
                    if unknown in integer_required and Fraction(candidate).denominator != 1:
                        continue
                    updated[unknown] = Fraction(candidate)
                try:
                    value = evaluate(expression, {name:value for name,value in updated.items() if value is not None})
                    if value.denominator != 1 or not 1 <= value <= limit:
                        continue
                except (ValueError, ArithmeticError):
                    continue
                survivors[tuple(updated.items())] = updated
        assignments = list(survivors.values())
        inferred = sorted(set().union(*(inferred_integer_variables(expression, {
            name:value for name,value in assignment.items() if value is not None}) for assignment in assignments)))
        notes.append(f'{expression}: {len(assignments)} partial assignments (solved analytically)' +
                     (f"; integer rule: {', '.join(inferred)}" if inferred else ''))
    return assignments, notes


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def evaluate(expression, variables):
    """Evaluate arithmetic only, keeping rational results exact."""
    if len(expression) > 200:
        raise ValueError("Expression is too long")
    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown variable: {node.id}")
            return Fraction(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "cbrt" and len(node.args) == 1 and not node.keywords):
            value = visit(node.args[0])
            if isinstance(value, Fraction):
                def integer_cube_root(number):
                    low, high = 0, 1 << ((number.bit_length()+2)//3)
                    while low < high:
                        middle = (low+high+1)//2
                        if middle**3 <= number:
                            low = middle
                        else:
                            high = middle-1
                    return low
                numerator = integer_cube_root(abs(value.numerator))
                denominator = integer_cube_root(value.denominator)
                if numerator**3 == abs(value.numerator) and denominator**3 == value.denominator:
                    return Fraction(numerator if value >= 0 else -numerator, denominator)
            with localcontext() as context:
                context.prec = 80
                decimal = Decimal(value.numerator)/Decimal(value.denominator) if isinstance(value, Fraction) else value
                if not decimal:
                    return Fraction(0)
                root = (abs(decimal).ln()/Decimal(3)).exp()
                return root if decimal > 0 else -root
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and re.fullmatch(r"log_([a-z]+|\d+)", node.func.id)
                and len(node.args) == 1 and not node.keywords):
            base_name = node.func.id[4:]
            if base_name.isdigit():
                base = Fraction(int(base_name))
            elif base_name in variables:
                base = Fraction(variables[base_name])
            else:
                raise ValueError(f"Unknown logarithm base variable: {base_name}")
            argument = visit(node.args[0])
            if base <= 0 or base == 1 or argument <= 0:
                raise ValueError("Logarithms require a positive argument and a positive base different from 1")
            with localcontext() as context:
                context.prec = 80
                base_decimal = Decimal(base.numerator)/Decimal(base.denominator)
                argument_decimal = Decimal(argument.numerator)/Decimal(argument.denominator) if isinstance(argument, Fraction) else argument
                return argument_decimal.ln()/base_decimal.ln()
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords):
            value = visit(node.args[0])
            if value < 0:
                raise ValueError("sqrt requires a nonnegative argument")
            if isinstance(value, Fraction):
                numerator, denominator = isqrt(value.numerator), isqrt(value.denominator)
                if numerator*numerator == value.numerator and denominator*denominator == value.denominator:
                    return Fraction(numerator, denominator)
            with localcontext() as context:
                context.prec = 80
                decimal = (Decimal(value.numerator)/Decimal(value.denominator)
                           if isinstance(value, Fraction) else value)
                return decimal.sqrt()
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if right != int(right) or abs(right) > 20:
                    raise ValueError("Powers require an integer exponent from -20 to 20")
                right = int(right)
            if isinstance(left, Decimal) or isinstance(right, Decimal):
                with localcontext() as context:
                    context.prec = 80
                    left = Decimal(left.numerator)/Decimal(left.denominator) if isinstance(left, Fraction) else left
                    right = Decimal(right.numerator)/Decimal(right.denominator) if isinstance(right, Fraction) else right
                    result = OPERATORS[type(node.op)](left, right)
            else:
                result = OPERATORS[type(node.op)](left, right)
            if isinstance(result, Decimal):
                return result
            result = Fraction(result)
            if result.numerator.bit_length() > 4096 or result.denominator.bit_length() > 4096:
                raise ValueError("Result is too large")
            return result
        raise ValueError("Use numbers, defined variables, parentheses, and arithmetic operators only")

    with localcontext() as context:
        context.prec = 80
        result = visit(tree.body)
        if isinstance(result, Decimal):
            nearest = result.to_integral_value()
            if abs(result - nearest) < Decimal("1e-60"):
                return Fraction(int(nearest))
            return Fraction(result)
        return result
