"""Pure, shared deletion preview used by the inspector and API."""

import re

from backend.models import GeometrySchema, POINT_NAME_RE

CIRCLE_CONSTRAINTS = {
    "circle_center", "circle_radius", "point_on_circle", "circumscribed_circle",
    "inscribed_circle", "inscribed_polygon", "tangent", "external_tangency",
}


def delete_point_schema(schema: GeometrySchema, point_name: str):
    if point_name not in schema.points:
        raise ValueError("Неизвестная точка")
    if len(schema.points) == 1:
        raise ValueError("Нельзя удалить последнюю точку чертежа")

    data = schema.model_dump(mode="json")
    removed = {key: [] for key in ("lines", "figures", "circles", "constraints", "givens", "targets")}
    data["points"].remove(point_name)

    def filter_items(key, predicate):
        kept = []
        for item in data[key]:
            (removed[key] if predicate(item) else kept).append(item)
        data[key] = kept

    filter_items("lines", lambda line: point_name in line)
    filter_items("figures", lambda f: point_name in f["points"] or f.get("center") == point_name)
    filter_items("circles", lambda c: c["center"] == point_name or point_name in c["passing_through"])
    removed_centers = {c["center"] for c in removed["circles"]}
    filter_items("figures", lambda f: f["type"] == "circle" and (
        f.get("center") in removed_centers or
        f["name"] in {c["name"] for c in removed["circles"]}
    ))
    # A circle figure can also refer to its center without a Circle record.
    removed_centers.update(f["center"] for f in removed["figures"] if f.get("center"))

    def references(value):
        if isinstance(value, list):
            return {ref for item in value for ref in references(item)}
        return {value} if isinstance(value, str) else set()

    filter_items("constraints", lambda c: point_name in references(c["args"]) or (
        c["type"] in CIRCLE_CONSTRAINTS and bool(references(c["args"]) & removed_centers)
    ))
    # Raw facts/targets may contain compact object names such as AM or A1BC.
    removed_names = {item["name"] for key in ("figures", "circles") for item in removed[key]}

    def mentions_removed(value):
        if isinstance(value, dict):
            return any(mentions_removed(v) for v in value.values())
        if isinstance(value, list):
            return any(mentions_removed(v) for v in value)
        if not isinstance(value, str):
            return False
        if value in removed_names:
            return True
        objects = re.findall(r"(?<![A-Za-z0-9])(?:" + POINT_NAME_RE + r")+(?![A-Za-z0-9])", value)
        return any(point_name in re.findall(POINT_NAME_RE, obj) for obj in objects)

    filter_items("givens", mentions_removed)
    filter_items("targets", mentions_removed)
    return GeometrySchema.model_validate(data), removed
