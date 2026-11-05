"""Safe highlighting of explicitly recognised labels and numeric tokens."""

import html
import re


def highlight_condition(text, schema):
    names = set(schema.get("points", []))
    numbers = set()
    for constraint in schema.get("constraints", []):
        value = constraint.get("value")
        if value is None:
            continue
        for number in value if isinstance(value, list) else [value]:
            numbers.add(float(number))
    parts = []
    offset = 0
    for match in re.finditer(r"(?:[A-Z](?:_?[0-9₀₁₂₃₄₅₆₇₈₉]{1,3})?)+|\d+(?:[.,]\d+)?", text):
        token = match.group()
        if token[0].isalpha():
            normalized = token.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).replace("_", "")
            labels = re.findall(r"[A-Z](?:\d{1,3})?", normalized)
            recognised = bool(labels) and all(label in names for label in labels)
        else:
            recognised = float(token.replace(",", ".")) in numbers
        parts.append(html.escape(text[offset : match.start()]))
        safe = html.escape(token)
        parts.append(f"<mark>{safe}</mark>" if recognised else safe)
        offset = match.end()
    parts.append(html.escape(text[offset:]))
    return "".join(parts).replace("\n", "<br>")
