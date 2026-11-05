"""Reproducible offline corpus check; writes a machine-readable report."""

import json
from pathlib import Path

from backend.llm_parser import parse_hybrid
from backend.sample_tasks import EXERCISES
from backend.sympy_solver import SympyGeometrySolver


def run_samples(mode="rules"):
    report = []
    for name, text in EXERCISES.items():
        try:
            schema, engine = parse_hybrid(text, mode=mode)
            solution = SympyGeometrySolver(schema).solve()
            report.append(
                {
                    "name": name,
                    "ok": True,
                    "engine": engine,
                    "schema": schema.model_dump(mode="json"),
                    "diagnostics": solution["diagnostics"],
                }
            )
        except (ValueError, RuntimeError) as exc:
            report.append({"name": name, "ok": False, "error": str(exc)})
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rules", "ollama"], default="rules")
    args = parser.parse_args()
    report = run_samples(args.mode)
    Path("artifacts").mkdir(exist_ok=True)
    Path(f"artifacts/samples-{args.mode}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for row in report:
        print("OK" if row["ok"] else "FAIL", row["name"], row.get("error", ""))
    raise SystemExit(0 if all(r["ok"] for r in report) else 1)
