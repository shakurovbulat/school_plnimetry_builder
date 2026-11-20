"""Offline regressions for external LLM failures and streaming recognition."""

import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException
from streamlit.testing.v1 import AppTest
from urllib3.exceptions import ReadTimeoutError

from backend.config import Settings
from backend.main import TaskRequest, parse_geometry_task, solve_geometry_task


LONG_TASK = (
    "В треугольнике ABC со сторонами AB = 5, AC = 6, BC = 7 проведена "
    "медиана AM. Из B на прямую AC опущен перпендикуляр BH, а из C "
    "на прямую AB — перпендикуляр CK. На отрезке AM отмечена её "
    "середина N. Постройте отрезки BH, CK, BN, CN и окружность, "
    "описанную около треугольника ABC. Укажите на чертеже все названные точки."
)


def sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\r\n\r\n".encode("utf-8")


def delta(content=None, finish_reason=None, **extra):
    return {"choices": [{
        "index": 0,
        "delta": {"content": content, **extra},
        "finish_reason": finish_reason,
    }]}


class ProviderErrorTests(unittest.TestCase):
    def setUp(self):
        config = patch(
            "backend.llm_parser.settings",
            Settings(api_url="http://127.0.0.1:1/v1", api_key="dummy", model="test-model", stream=True),
        )
        transport = patch("backend.llm_parser.requests.post")
        config.start()
        self.post = transport.start()
        self.addCleanup(config.stop)
        self.addCleanup(transport.stop)
        self.response = self.post.return_value.__enter__.return_value
        self.response.headers = {}
        self.task = TaskRequest(text=LONG_TASK)

    def mock_stream(self, *chunks):
        self.response.status_code = 200
        self.response.headers = {"Content-Type": "text/event-stream; charset=utf-8"}
        self.response.iter_content.side_effect = lambda **_: iter(chunks)

    def assert_route_error(self, status: int, detail: str):
        for route in (parse_geometry_task, solve_geometry_task):
            with self.subTest(route=route.__name__):
                with self.assertRaises(HTTPException) as error:
                    route(self.task)
                self.assertEqual(error.exception.status_code, status)
                self.assertIn(detail, error.exception.detail)
                self.assertNotIn("not for display", error.exception.detail)

    def test_gateway_timeout(self):
        self.response.status_code = 504
        self.assert_route_error(504, "Шлюз внешнего API вернул HTTP 504")
        self.response.json.assert_not_called()
        self.response.iter_content.assert_not_called()
        self.assertEqual(self.post.return_value.__exit__.call_count, 2)

    def test_read_timeout(self):
        self.post.side_effect = requests.ReadTimeout("not for display")
        self.assert_route_error(504, "Приложение не дождалось ответа внешнего API")

    def test_stream_read_timeout(self):
        self.mock_stream()

        def stalled(**_):
            yield sse(delta('{"status":'))
            raise requests.ConnectionError(ReadTimeoutError(None, None, "not for display"))

        self.response.iter_content.side_effect = stalled
        self.assert_route_error(504, "Приложение не дождалось ответа внешнего API")

    def test_connect_timeout(self):
        self.post.side_effect = requests.ConnectTimeout("not for display")
        self.assert_route_error(504, "Не удалось подключиться к внешнему API")

    def test_gateway_unavailable(self):
        self.response.status_code = 503
        self.assert_route_error(503, "Внешний API временно недоступен (HTTP 503")

    def test_token_limit_is_not_a_connectivity_error(self):
        self.mock_stream(sse(delta('{"status":', "length")))
        self.assert_route_error(502, "Ответ модели оборвался на лимите токенов")

    def test_incomplete_stream_never_reaches_solver(self):
        content = '{"status":"ok","message":"","geometry":{"points":["A","B","C"]}}'
        self.mock_stream(sse(delta(content)), b"data: [DONE]\n\n")
        with patch("backend.main.SympyGeometrySolver") as solver:
            self.assert_route_error(502, "до получения полного ответа")
            solver.assert_not_called()

    def test_stream_connection_cut_is_not_a_validation_error(self):
        self.mock_stream()
        self.response.iter_content.side_effect = requests.exceptions.ChunkedEncodingError(
            "not for display"
        )
        self.assert_route_error(502, "Соединение с внешним API оборвалось")

    def test_error_event_does_not_leak_provider_body(self):
        self.mock_stream(sse({"error": {"message": "not for display"}, "choices": []}))
        self.assert_route_error(502, "ошибку или некорректные данные в потоке")

    def test_invalid_geometry_is_still_rejected(self):
        content = '{"status":"ok","message":"","geometry":{"points":["A"],"lines":[["A","B"]]}}'
        self.mock_stream(sse(delta(content, "stop")))
        self.assert_route_error(422, "некорректный JSON или геометрическую схему")

    def test_buffered_json_remains_supported(self):
        self.response.status_code = 200
        self.response.headers = {"Content-Type": "application/json"}
        self.response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "status": "ok", "message": "", "geometry": {"points": ["A", "B", "C"]},
            })}}],
        }
        self.assertEqual(parse_geometry_task(self.task)["status"], "success")
        self.assertTrue(self.post.call_args.kwargs["json"]["stream"])
        with patch("backend.llm_parser.settings", Settings(
            api_url="http://127.0.0.1:1/v1", api_key="dummy", stream=False,
        )):
            self.assertEqual(parse_geometry_task(self.task)["status"], "success")
            self.assertFalse(self.post.call_args.kwargs["json"]["stream"])


class ProviderTransportTests(unittest.TestCase):
    def test_long_task_passes_gateway_and_builds_from_sse(self):
        warning = "Тестовое предупреждение"
        content = json.dumps({
            "status": "ok", "message": "", "warnings": [warning],
            "geometry": {
                "points": ["A", "B", "C", "M", "N", "H", "K", "O"],
                "lines": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"],
                          ["B", "H"], ["C", "K"], ["B", "N"], ["C", "N"]],
                "constraints": [
                    {"type": "distance", "args": ["A", "B"], "value": 5},
                    {"type": "distance", "args": ["A", "C"], "value": 6},
                    {"type": "distance", "args": ["B", "C"], "value": 7},
                    {"type": "midpoint", "args": ["M", "B", "C"]},
                    {"type": "midpoint", "args": ["N", "A", "M"]},
                    {"type": "projection", "args": ["H", "B", "A", "C"]},
                    {"type": "projection", "args": ["K", "C", "A", "B"]},
                    {"type": "circumscribed_circle", "args": ["O", "A", "B", "C"]},
                ],
                "circles": [{"center": "O", "passing_through": ["A", "B", "C"]}],
            },
        }, ensure_ascii=False)
        wire = (
            b": keep-alive\r\n\r\n"
            + sse(delta(reasoning_content="not part of the schema"))
            + sse(delta(content[:80])) + sse(delta(content[80:]))
            + sse(delta(finish_reason="stop")) + b"data: [DONE]\r\n\r\n"
        )
        # Force arbitrary network splits, including a split UTF-8 character and CRLF.
        utf8_split = wire.index("Т".encode()) + 1
        crlf_split = wire.index(b"\r\n") + 1
        chunks = [wire[:crlf_split], wire[crlf_split:utf8_split], wire[utf8_split:]]
        received = []

        class Gateway(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(payload)
                if payload.get("stream") is not True:
                    # Simulate the provider's gateway timing out on a buffered reply.
                    self.send_response(504)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                for chunk in chunks:
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")

        self.assertGreater(len(LONG_TASK), 300)
        task = TaskRequest(text=LONG_TASK)
        with ThreadingHTTPServer(("127.0.0.1", 0), Gateway) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/v1"
                with patch("backend.llm_parser.settings", Settings(
                    api_url=url, api_key="dummy", stream=False, timeout=5,
                )):
                    with self.assertRaises(HTTPException) as error:
                        parse_geometry_task(task)
                    self.assertEqual(error.exception.status_code, 504)
                with patch("backend.llm_parser.settings", Settings(
                    api_url=url, api_key="dummy", stream=True, timeout=5,
                )), patch("backend.main.history_store", return_value=Mock()):
                    result = solve_geometry_task(task)
            finally:
                server.shutdown()
                thread.join()
        self.assertEqual([p["stream"] for p in received], [False, True])
        self.assertTrue(all(p["messages"][-1]["content"] == LONG_TASK for p in received))
        self.assertEqual(result["status"], "success")
        self.assertEqual(set(result["points"]), set("ABCMNHKO"))
        self.assertEqual(len(result["circles"]), 1)
        self.assertIn(warning, result["warnings"])


class InterfaceErrorTests(unittest.TestCase):
    def test_non_json_gateway_timeout(self):
        app_path = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
        app = AppTest.from_file(str(app_path)).run()
        app.text_area[0].set_value("Постройте треугольник ABC.")
        button = next(b for b in app.button if b.label == "Построить")
        with patch("requests.post") as post:
            post.return_value.ok = False
            post.return_value.status_code = 504
            post.return_value.json.side_effect = ValueError("HTML, not JSON")
            button.click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("Сервер построения вернул HTTP 504" in e.value for e in app.error))
