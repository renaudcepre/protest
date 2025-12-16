from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
import warnings
from http import HTTPStatus
from logging import LogRecord
from pathlib import Path
from typing import TYPE_CHECKING, Any

from protest.execution.capture import add_log_callback, remove_log_callback
from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities import (
        SessionResult,
        TestItem,
        TestResult,
        TestStartInfo,
        TestTeardownInfo,
    )

try:
    from websockets.asyncio.server import (  # type: ignore[import-not-found]
        serve as ws_serve,
    )
    from websockets.datastructures import Headers  # type: ignore[import-not-found]
    from websockets.http11 import Request, Response  # type: ignore[import-not-found]
    from websockets.sync.client import (  # type: ignore[import-not-found]
        connect as ws_connect,
    )
except ImportError as err:  # pragma: no cover
    raise ImportError(
        "WebReporter requires 'websockets' package. "
        "Install with: pip install protest[web]"
    ) from err

ASSETS_DIR = Path(__file__).parent / "assets"
DEFAULT_PORT = 8765

_broadcast_clients: set[Any] = set()


def _format_traceback(error: Exception) -> str:
    lines = traceback.format_exception(type(error), error, error.__traceback__)
    return "".join(lines)


async def _ws_handler(websocket: Any) -> None:  # pragma: no cover
    _broadcast_clients.add(websocket)
    try:
        async for message in websocket:
            for client in list(_broadcast_clients):
                if client != websocket:
                    try:
                        await client.send(message)
                    except Exception:
                        _broadcast_clients.discard(client)
    finally:
        _broadcast_clients.discard(websocket)


def _process_request(connection: Any, request: Request) -> Response | None:
    if request.path == "/ws":
        return None

    if request.path in {"/", "/index.html"}:
        html_path = ASSETS_DIR / "index.html"
        if html_path.exists():
            body = html_path.read_bytes()
            headers = Headers(
                [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ]
            )
            return Response(HTTPStatus.OK, "OK", headers, body)

    return Response(HTTPStatus.NOT_FOUND, "Not Found", Headers(), b"Not Found")


def run_live_server(port: int = DEFAULT_PORT) -> None:  # pragma: no cover
    async def serve() -> None:
        async with ws_serve(
            _ws_handler,
            "",
            port,
            process_request=_process_request,
        ):
            print(f"Live reporter running at http://localhost:{port}")  # noqa: T201
            print("Press Ctrl+C to stop")  # noqa: T201
            await asyncio.get_running_loop().create_future()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("\nStopped")  # noqa: T201


class WebReporter(PluginBase):
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self._port = port
        self._ws: Any = None
        self._total_tests = 0
        self._session_target: str = ""
        self._test_logs: dict[str, list[str]] = {}

    def _send(self, msg_type: str, payload: dict[str, Any]) -> None:
        if not self._ws:
            return
        try:
            message = json.dumps({"type": msg_type, "payload": payload})
            self._ws.send(message)
        except Exception:
            self._ws = None

    def set_target(self, target: str) -> None:
        self._session_target = target

    def _on_log(self, node_id: str, record: LogRecord) -> None:
        if node_id not in self._test_logs:
            self._test_logs[node_id] = []
        level = logging.getLevelName(record.levelno)
        log_line = f"{level}:{record.name}:{record.getMessage()}"
        self._test_logs[node_id].append(log_line)

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        try:
            self._ws = ws_connect(f"ws://localhost:{self._port}/ws")
            time.sleep(0.05)  # Let server register the connection
        except Exception:
            warnings.warn(
                f"Cannot connect to live server on localhost:{self._port}. "
                "Start it first with: protest live",
                stacklevel=1,
            )
            self._ws = None
            return items

        add_log_callback(self._on_log)
        self._test_logs.clear()

        self._total_tests = len(items)
        tests = [
            {"nodeId": item.node_id, "suitePath": item.suite_path} for item in items
        ]
        self._send(
            "SESSION_START",
            {
                "target": self._session_target,
                "totalTests": self._total_tests,
                "tests": tests,
            },
        )
        return items

    def on_test_acquired(self, info: TestStartInfo) -> None:
        self._send("TEST_SETUP", {"nodeId": info.node_id})

    def on_test_setup_done(self, info: TestStartInfo) -> None:
        self._send("TEST_RUNNING", {"nodeId": info.node_id})

    def on_test_teardown_start(self, info: TestTeardownInfo) -> None:
        outcome = info.outcome.name.lower().removeprefix("test_")
        self._send("TEST_TEARDOWN", {"nodeId": info.node_id, "outcome": outcome})

    def on_test_pass(self, result: TestResult) -> None:
        self._send("TEST_PASS", self._result_payload(result))

    def on_test_fail(self, result: TestResult) -> None:
        self._send("TEST_FAIL", self._result_payload(result, include_error=True))

    def on_test_skip(self, result: TestResult) -> None:
        self._send(
            "TEST_SKIP",
            {
                "nodeId": result.node_id,
                "duration": result.duration,
                "message": result.skip_reason,
            },
        )

    def on_test_xfail(self, result: TestResult) -> None:
        self._send(
            "TEST_XFAIL",
            {
                "nodeId": result.node_id,
                "duration": result.duration,
                "message": result.xfail_reason,
            },
        )

    def on_session_complete(self, result: SessionResult) -> None:
        remove_log_callback(self._on_log)
        self._send("SESSION_END", {})
        if self._ws:
            self._ws.close()
            self._ws = None

    def _result_payload(
        self, result: TestResult, include_error: bool = False
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "nodeId": result.node_id,
            "duration": result.duration,
        }
        if result.output:
            payload["stdout"] = result.output
        logs = self._test_logs.pop(result.node_id, [])
        if logs:
            payload["logs"] = "\n".join(logs)
        if include_error and result.error:
            payload["message"] = str(result.error)
            payload["traceback"] = _format_traceback(result.error)
        return payload
