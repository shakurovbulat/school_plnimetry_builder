"""Bounded arithmetic normalization and separation of givens from proof targets.

Never executes input: only decimal literals, sqrt, + - * / and parentheses.
"""

import ast
import math
import operator
import re

_LABEL_MAP = str.maketrans("АВЕКМНОРСТХУ", "ABEKMHOPCTXY")
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def numeric_expression(source):
    if len(source) > 120:
        raise ValueError("Слишком длинное числовое выражение")
    tree = ast.parse(source.replace(",", "."), mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 40:
        raise ValueError("Слишком сложное числовое выражение")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(node.value)
        elif isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            value = _OPS[type(node.op)](visit(node.left), visit(node.right))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sqrt"
            and len(node.args) == 1
            and not node.keywords
        ):
            value = math.sqrt(visit(node.args[0]))
        else:
            raise ValueError("Недопустимое числовое выражение")
        if not math.isfinite(value) or abs(value) > 1e9:
            raise ValueError("Число вне допустимого диапазона")
        return value

    try:
        return visit(tree)
    except (ArithmeticError, OverflowError) as exc:
        raise ValueError("Некорректное числовое выражение") from exc


def normalize_text(text):
    text = text.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    text = re.sub(r"\b([A-ZАВЕКМНОРСТХУ])_(\d{1,3})", r"\1\2", text)
    text = text.replace("\u00ad", "").replace("−", "-").replace("\\angle", "∠")
    # Translate only label-like tokens, never Russian prose.
    text = re.sub(
        r"(?<![а-яёa-z])[A-ZАВЕКМНОРСТХУ]+(?:_?\d+)?(?![а-яёa-z])",
        lambda m: m[0].translate(_LABEL_MAP),
        text,
    )
    text = re.sub(r"\b([A-Z])\s+([A-Z])(?=\s*(?:=|,|\.|$|\bрав))", r"\1\2", text)
    text = re.sub(r"√\s*(\d+(?:[.,]\d+)?)", r"sqrt(\1)", text)
    text = re.sub(r"(\d)\s*(?=sqrt\()", r"\1*", text)
    text = re.sub(r"\bсинус\b", "sin", text, flags=re.I)
    text = re.sub(r"\bкосинус\b", "cos", text, flags=re.I)
    text = re.sub(r"\bтангенс\b", "tg", text, flags=re.I)
    # Match an entire arithmetic token, not the leading numerator of a fraction.
    pattern = r"(?<![\w.])(?:\d+(?:[.,]\d+)?|sqrt\(\s*\d+(?:[.,]\d+)?\s*\))(?:\s*[*/]\s*(?:\d+(?:[.,]\d+)?|sqrt\(\s*\d+(?:[.,]\d+)?\s*\)))+"
    text = re.sub(pattern, lambda m: format(numeric_expression(m[0]), ".15g"), text)
    text = re.sub(
        r"sqrt\(\s*\d+(?:[.,]\d+)?\s*\)", lambda m: format(numeric_expression(m[0]), ".15g"), text
    )
    return re.sub(r"\s+", " ", text).strip()


def given_text(text):
    """Remove proof requests, retaining the numeric givens following part б)."""
    text = normalize_text(text)
    text = re.sub(r"докажите\b.*?(?=(?:б\)|найдите|вычислите)|$)", "", text, flags=re.I)
    return text
