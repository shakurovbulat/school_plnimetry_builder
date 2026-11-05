from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.llm_parser import parse_hybrid
from backend.sympy_solver import SympyGeometrySolver

EXERCISES_PATH = ROOT_DIR / "tests/fixtures/textbook.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def load_exercises() -> list[str]:
    if not EXERCISES_PATH.exists():
        print(f"Файл не найден: {EXERCISES_PATH}")
        return []

    with EXERCISES_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data.get("exercises", [])


def run_tests(limit: int | None = None, mode: str = "rules") -> None:
    exercises = load_exercises()
    if limit:
        exercises = exercises[:limit]

    print(f"End-to-End Solver test: {len(exercises)} exercises")
    print("=" * 80)

    success_count = 0
    for index, text in enumerate(exercises, 1):
        try:
            schema, _ = parse_hybrid(text, mode=mode)
            solver = SympyGeometrySolver(schema)
            res = solver.solve()
            success_count += 1
            print(f"\n#{index}: {text[:120]}...")
            print(f"  Points ({len(res['points'])}): {list(res['points'].keys())}")
            print(f"  Lines ({len(res['lines'])}): {res['lines']}")
            print(
                f"  Constraints ({res['diagnostics']['constraints_count']}), Loss: {res['diagnostics']['loss']}"
            )
        except (ValueError, RuntimeError) as e:
            print(f"\n#{index}: ERROR - {e}")

    print("=" * 80)
    print(f"Summary: {success_count}/{len(exercises)} tasks parsed and solved successfully.")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--limit", type=int, default=10)
    arg_parser.add_argument("--mode", choices=["rules", "ollama"], default="rules")
    args = arg_parser.parse_args()
    run_tests(limit=args.limit, mode=args.mode)
