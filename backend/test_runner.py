from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from backend.parser import parse_geometry_text
except ModuleNotFoundError:
    from parser import parse_geometry_text


ROOT_DIR = Path(__file__).resolve().parents[1]
EXERCISES_PATH = ROOT_DIR / "exercises.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def load_exercises() -> list[str]:
    if not EXERCISES_PATH.exists():
        print(f"Файл не найден: {EXERCISES_PATH}")
        return []

    with EXERCISES_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data.get("exercises", [])


def run_tests(limit: int | None = None) -> None:
    exercises = load_exercises()
    if limit:
        exercises = exercises[:limit]

    print(f"Parser smoke test: {len(exercises)} exercises")
    print("=" * 80)

    for index, text in enumerate(exercises, 1):
        result = parse_geometry_text(text)
        print(f"\n#{index}: {text[:180]}")
        print(
            json.dumps(
                {
                    "points": result["points"],
                    "lines": result["lines"],
                    "figures": result["figures"],
                    "constraints_count": len(result["constraints"]),
                    "targets": result["targets"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--limit", type=int, default=10)
    args = arg_parser.parse_args()
    run_tests(limit=args.limit)
