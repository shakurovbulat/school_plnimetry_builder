"""Start the local API and UI. Ctrl+C stops both services."""

import subprocess
import sys
from pathlib import Path


def main():
    cwd = Path(__file__).resolve().parent
    commands = [
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
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
            "8501",
            "--server.headless",
            "true",
        ],
    ]
    children = []
    try:
        for command in commands:
            children.append(subprocess.Popen(command, cwd=cwd))
        print("User UI: http://127.0.0.1:8501 | API: http://127.0.0.1:8000/docs")
        children[0].wait()
    except KeyboardInterrupt:
        pass
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
