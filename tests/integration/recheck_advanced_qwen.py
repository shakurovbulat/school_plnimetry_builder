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
from test_advanced_constructions import TASKS as TEXTS
from test_advanced_constructions import verify_source

from backend.history import History
from backend.main import app

TASKS = [dict(number=i, problem_id="advanced-" + str(i), text=t) for i, t in enumerate(TEXTS, 1)]


def main():
    out = ROOT / "artifacts/advanced-20-qwen"
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as temp:
        history = History("sqlite:///" + str(Path(temp) / "history.sqlite3"))
        with patch("backend.main.history_store", return_value=history), TestClient(app) as client:
            for task in TASKS:
                started = time.perf_counter()
                response = client.post(
                    "/solve",
                    json={
                        "text": task["text"],
                        "parser_mode": "ollama",
                        "model": "hf.co/Qwen/Qwen3-14B-GGUF:Q5_K_M",
                    },
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
                        verify_source(task["number"], body)
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
