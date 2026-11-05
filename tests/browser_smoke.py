"""Real Chrome e2e; install the optional requirements-dev.txt dependencies."""

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
from playwright.sync_api import sync_playwright


def main():
    children = []
    env = {**os.environ, "PARSER_MODE": "rules"}
    try:
        for cmd in [
            ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "18001"],
            [
                "-m",
                "streamlit",
                "run",
                "frontend/app.py",
                "--server.address",
                "127.0.0.1",
                "--server.port",
                "18503",
                "--server.headless",
                "true",
            ],
        ]:
            children.append(
                subprocess.Popen(
                    [sys.executable, *cmd],
                    cwd=ROOT,
                    env={**env, "GEOMETRY_API_URL": "http://127.0.0.1:18001"},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        for port, path in [(18001, "health"), (18503, "_stcore/health")]:
            for _ in range(100):
                try:
                    if requests.get(f"http://127.0.0.1:{port}/{path}", timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Server not ready")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
            page.goto("http://127.0.0.1:18503")
            page.get_by_role("textbox", name="Условие задачи").fill(
                "В треугольнике ABC AB = 3, BC = 4, AC = 5."
            )
            page.get_by_role("button", name="Сгенерировать чертёж", exact=True).click()
            iframe = page.locator('iframe[title="geometry_canvas.geometry_canvas"]').first
            # Streamlit may expose the declared component under a qualified name.
            if not iframe.count():
                iframe = page.locator("iframe").first
            iframe.wait_for(timeout=30000)
            frame = iframe.element_handle().content_frame()
            frame.locator("#c").wait_for()
            frame.wait_for_function('typeof sol !== "undefined" && sol !== null')
            initial = frame.evaluate("scale")
            box = frame.locator("#c").bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 200)
            page.mouse.wheel(0, -150)
            page.wait_for_timeout(300)
            assert frame.evaluate("scale") > initial, "Wheel zoom failed"
            frame.locator("#reset").click()
            assert abs(frame.evaluate("scale") - initial) < 0.01, "Reset failed"
            before = frame.evaluate("({ox,oy})")
            page.mouse.move(box["x"] + 15, box["y"] + 15)
            page.mouse.down()
            page.mouse.move(box["x"] + 65, box["y"] + 45, steps=5)
            page.mouse.up()
            after = frame.evaluate("({ox,oy})")
            assert abs(after["ox"] - before["ox"]) > 20, "Pan failed"
            frame.locator("#reset").click()
            # Capture the actual API edit, not only a frontend event.
            point = frame.evaluate("screen(points.C)")
            css = frame.evaluate("({w:canvas.width,h:canvas.height})")
            x = box["x"] + point[0] * box["width"] / css["w"]
            y = box["y"] + point[1] * box["height"] / css["h"]
            old_sol = frame.evaluate("JSON.stringify(sol.points)")
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 25, y - 20, steps=8)
            page.mouse.up()
            # Streamlit calls the API server-side, so there is no browser fetch to observe.
            page.wait_for_timeout(1500)
            iframe = page.locator("iframe").first
            frame = iframe.element_handle().content_frame()
            frame.wait_for_function("sol !== null")
            assert frame.evaluate("JSON.stringify(sol.points)") != old_sol, (
                "Server recomputation did not reach the canvas"
            )
            assert not page.get_by_text("Перемещение отклонено", exact=False).count(), (
                "Edit was rejected"
            )
            accepted = frame.evaluate("JSON.stringify(sol.points)")
            frame.evaluate(
                "send('streamlit:setComponentValue',{value:{id:Date.now(),point_name:'C',new_coords:[2000000,0]}})"
            )
            page.get_by_text("Перемещение отклонено", exact=False).wait_for(timeout=15000)
            assert frame.evaluate("JSON.stringify(points)") == accepted, (
                "Rejected edit changed coordinates"
            )
            with page.expect_download() as download:
                page.get_by_role("button", name="Скачать PNG", exact=True).click()
            assert Path(download.value.path()).read_bytes().startswith(b"\x89PNG")
            browser.close()
            print(
                "PASS: real Chrome generation, wheel zoom, reset, pan, server drag, rejected-edit rollback, PNG download"
            )
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
