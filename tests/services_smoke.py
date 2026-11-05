"""HTTP smoke for the API and UI on temporary, non-default ports."""

import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = [
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "18000",
        ],
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "frontend/app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "18501",
            "--server.headless",
            "true",
        ],
    ]
    children = []
    try:
        for command in commands:
            children.append(
                subprocess.Popen(
                    command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            )
        urls = ["http://127.0.0.1:18000/health", "http://127.0.0.1:18501/_stcore/health"]
        deadline = time.monotonic() + 30
        pending = set(urls)
        while pending and time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service exited before the smoke test completed")
            for url in list(pending):
                try:
                    response = requests.get(url, timeout=1)
                    if response.ok:
                        pending.remove(url)
                except requests.RequestException:
                    pass
            if pending:
                time.sleep(0.2)
        if pending:
            raise RuntimeError(f"Services not ready: {pending}")
        print("PASS: API and Streamlit respond to HTTP health checks")
        response = requests.post(
            "http://127.0.0.1:18000/solve",
            json={"text": "В треугольнике ABC AB = 3, BC = 4, AC = 5.", "parser_mode": "rules"},
            timeout=20,
        )
        response.raise_for_status()
        assert response.json()["diagnostics"]["status"] == "solved"
        print("PASS: actual HTTP parse/solve pipeline")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
