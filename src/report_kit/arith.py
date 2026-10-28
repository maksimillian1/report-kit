"""Arithmetic over named numbers: `+ - * /`, unary minus, numbers and names.

A `formula:` in `report-values.yaml` names values; one in `metrics.yaml` names
register refs and the dotted fields of a point record. Both are parsed and
evaluated here, so the two files cannot drift into two dialects.
"""

from __future__ import annotations

import ast
from typing import Callable

OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div)


class ArithError(ValueError):
    """A formula that is not one, or that cannot be evaluated."""


def parse(formula: object) -> ast.Expression:
    try:
        return ast.parse(str(formula), mode="eval")
    except SyntaxError as exc:
        raise ArithError(f"{formula!r} is not an expression ({exc.msg})") from exc


def dotted_name(node: ast.AST) -> str | None:
    """`a.b.c` for a chain of attributes ending in a name, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = dotted_name(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


def name_of(node: ast.AST, dotted: bool) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return dotted_name(node) if dotted and isinstance(node, ast.Attribute) else None


def names(tree: ast.AST, dotted: bool = False) -> list[str]:
    """The names a formula reads, in the order it reads them."""
    found = name_of(tree, dotted)
    if found is not None:
        return [found]
    return [name for child in ast.iter_child_nodes(tree)
            for name in names(child, dotted)]


def check(tree: ast.AST, dotted: bool = False) -> None:
    """Refuses what `evaluate` would refuse, without any value to hand."""
    if isinstance(tree, ast.Expression):
        check(tree.body, dotted)
    elif isinstance(tree, ast.Constant):
        number(tree.value)
    elif isinstance(tree, ast.UnaryOp) and isinstance(tree.op, ast.USub):
        check(tree.operand, dotted)
    elif isinstance(tree, ast.BinOp) and isinstance(tree.op, OPERATORS):
        check(tree.left, dotted)
        check(tree.right, dotted)
    elif name_of(tree, dotted) is None:
        raise ArithError(f"unsupported expression node {type(tree).__name__}")


def number(constant: object) -> float:
    if isinstance(constant, bool) or not isinstance(constant, (int, float)):
        raise ArithError(f"non-numeric constant {constant!r}")
    return float(constant)


def evaluate(tree: ast.AST, resolve: Callable[[str], object],
             dotted: bool = False) -> object:
    """The formula's number. `resolve` turns a name into a float, or into a
    marker that is not one — a pending value — which then becomes the
    result, whatever the arithmetic around it."""
    if isinstance(tree, ast.Expression):
        return evaluate(tree.body, resolve, dotted)
    name = name_of(tree, dotted)
    if name is not None:
        return resolve(name)
    if isinstance(tree, ast.Constant):
        return number(tree.value)
    if isinstance(tree, ast.UnaryOp) and isinstance(tree.op, ast.USub):
        operand = evaluate(tree.operand, resolve, dotted)
        return -operand if isinstance(operand, float) else operand
    if isinstance(tree, ast.BinOp) and isinstance(tree.op, OPERATORS):
        left = evaluate(tree.left, resolve, dotted)
        right = evaluate(tree.right, resolve, dotted)
        if not isinstance(left, float):
            return left
        if not isinstance(right, float):
            return right
        return combined(tree.op, left, right)
    raise ArithError(f"unsupported expression node {type(tree).__name__}")


def combined(op: ast.operator, left: float, right: float) -> float:
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if right == 0:
        raise ArithError("division by zero")
    return left / right
