"""Run updated API in-process against real Ollama without restarting services.

Uses isolated history; never changes the user's application database.
"""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from fastapi.testclient import TestClient
from test_variant_93751277 import TASKS, verify_case

from backend.history import History
from backend.main import app
from backend.models import GeometrySchema


def main():
    out = ROOT / "artifacts/ege-93751277-revised"
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as temp:
        history = History("sqlite:///" + str(Path(temp) / "history.sqlite3"))
        with patch("backend.main.history_store", return_value=history), TestClient(app) as client:
            for task in TASKS:
                started = time.perf_counter()
                response = client.post(
                    "/solve", json={"text": task["text"], "parser_mode": "ollama"}
                )
                body = response.json()
                row = {
                    **task,
                    "http_status": response.status_code,
                    "seconds": round(time.perf_counter() - started, 3),
                    "response": body,
                }
                if response.status_code == 200:
                    try:
                        verify_case(
                            task["number"], GeometrySchema.model_validate(body["schema"]), body
                        )
                        row["independent_check"] = "pass"
                    except Exception as exc:
                        row["independent_check"] = "FAIL: " + str(exc)
                    payload = {"schema_data": body["schema"], "points": body["points"]}
                    for fmt in ["svg", "png"]:
                        exported = client.post("/export/" + fmt, json=payload)
                        row[fmt + "_status"] = exported.status_code
                        if exported.status_code == 200:
                            (out / f"{task['number']:02d}-{task['problem_id']}.{fmt}").write_bytes(
                                exported.content
                            )
                results.append(row)
                (out / "results.json").write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    task["number"],
                    response.status_code,
                    row.get("independent_check", str(body.get("detail", ""))[:150]),
                    flush=True,
                )
        history.engine.dispose()
    passed = sum(r.get("independent_check") == "pass" for r in results)
    failed = sum(r["http_status"] == 200 and r.get("independent_check") != "pass" for r in results)
    print(
        "Verified:",
        passed,
        "False successes:",
        failed,
        "Refusals:",
        sum(r["http_status"] != 200 for r in results),
    )


if __name__ == "__main__":
    main()
