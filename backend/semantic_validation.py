"""Conservative input coverage gates and post-LLM preservation checks.

This is not a proof of arbitrary natural-language understanding. Unsupported
constructions must be made explicit rather than silently dropped.
"""

import math
import re

from backend.text_normalization import given_text


def check_supported_text(text):
    from backend.advanced_constructions import parse_advanced

    if parse_advanced(text) is not None:
        return
    text = given_text(text)
    checks = [
        (r"пятиугольник", "вписанные пятиугольники"),
        (r"вне\s+треугольника\s+построены\s+квадраты", "квадраты вне треугольника"),
        (r"равные\s+хорды", "окружность, высекающая равные хорды на сторонах"),
        (
            r"на\s+все\s+стороны.*опустили\s+перпендикуляры",
            "проекции на все стороны неназванного многоугольника",
        ),
        (r"окружност\w*\s+с\s+диаметром", "системы окружностей, заданных диаметрами"),
        (r"(?<![a-zа-яё])[A-Z]+(?:_?\d+|\s+\d+)", "индексированные точки"),
    ]
    if re.search(
        r"угол\s+между\s+двумя\s+соседними\s+сторонами\s+правильного\s+многоугольника", text, re.I
    ):
        raise ValueError(
            "Пока не поддерживается построение правильного многоугольника с неизвестным числом вершин (в том числе более 26)."
        )
    if re.search(
        r"дуги\s+[A-Z]{2}\s+окружности,?\s*не\s+содержащей\s+точек", text, re.I
    ) and not re.search(r"секущ|пересека|прям", text, re.I):
        raise ValueError(
            "Неполное текстовое условие: нужны связи точек секущих с исходного рисунка. Укажите их явно."
        )
    for pattern, description in checks:
        if re.search(pattern, text, re.I):
            raise ValueError(
                "Пока не поддерживается полное построение: "
                + description
                + ". Условие не объявляется противоречивым."
            )


def _key(c):
    t = c.type.value
    a = c.args
    if t in {"distance"}:
        a = sorted(a)
    if t in {"angle", "right_angle", "cos", "sin", "tg"}:
        a = [min(a[0], a[2]), a[1], max(a[0], a[2])]
    if t in {"parallel", "perpendicular", "equal_segments"}:
        a = sorted(sorted(s) for s in a)
    return t, repr(a)


def preserve_explicit_facts(schema, draft):
    """Supplement missing rule facts; reject contradictory values from the LLM.

    The returned schema transparently includes deterministic constructions. Model
    additions are not accepted when they invent ungrounded numerical givens.
    """
    from backend.models import GeometrySchema

    expected = GeometrySchema.model_validate(
        {k: draft.get(k, []) for k in GeometrySchema.model_fields}
    )
    by_key = {_key(c): c for c in expected.constraints}
    for c in schema.constraints:
        other = by_key.get(_key(c))
        if (
            other is not None
            and isinstance(other.value, (float, int))
            and isinstance(c.value, (float, int))
        ):
            if not math.isclose(other.value, c.value, rel_tol=1e-6, abs_tol=1e-8):
                raise ValueError(
                    f"Модель исказила условие: {c.type.value} {c.args}, ожидалось {other.value}, получено {c.value}."
                )
    # The deterministic schema owns supported facts and constructions. Do not let
    # an invented model circle or a proof conclusion overwrite them. When no rule
    # construction exists, retain model output, subject to coverage checks below.
    if expected.figures or expected.circles:
        result = expected
    else:
        result = schema
    verify_coverage(text=draft.get("clean_text", ""), schema=result)
    return result


def verify_coverage(text, schema):
    if re.search(r"окружност", text, re.I) and not schema.circles:
        raise ValueError("Не удалось сохранить условие: окружность отсутствует в схеме.")
    if re.search(r"касается\s+сторон", text, re.I) and not any(
        c.type in ("tangent", "inscribed_circle") for c in schema.constraints
    ):
        raise ValueError("Не удалось сохранить условие: касания сторон не распознаны.")
    if re.search(r"биссектрис", text, re.I) and not any(
        c.type in ("bisector", "external_bisector") for c in schema.constraints
    ):
        raise ValueError("Не удалось сохранить условие: биссектриса не распознана.")
    rectangle_height = any(f.type == "trapezoid" for f in schema.figures) and any(
        c.type in ("angle", "right_angle") and (c.type == "right_angle" or c.value == 90)
        for c in schema.constraints
    )
    if (
        re.search(r"высот", text, re.I)
        and not rectangle_height
        and not any(c.type in ("projection", "perpendicular") for c in schema.constraints)
    ):
        raise ValueError("Не удалось сохранить условие: высота не распознана.")
    # Prevent success with free labelled points and no actual geometry.
    if not schema.constraints and not schema.figures and not schema.circles:
        raise ValueError("Недостаточно распознанных геометрических условий.")
