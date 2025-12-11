from __future__ import annotations

import asyncio
import json
import traceback
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities import SessionResult, TestItem, TestResult

try:
    from websockets.asyncio.server import serve as ws_serve
    from websockets.http11 import Request, Response
    from websockets.sync.client import connect as ws_connect
except ImportError as err:
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


async def _ws_handler(websocket: Any) -> None:
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

    if request.path == "/" or request.path == "/index.html":
        html_path = ASSETS_DIR / "index.html"
        if html_path.exists():
            body = html_path.read_bytes()
            from websockets.datastructures import Headers

            headers = Headers(
                [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ]
            )
            return Response(HTTPStatus.OK, "OK", headers, body)

    from websockets.datastructures import Headers

    return Response(HTTPStatus.NOT_FOUND, "Not Found", Headers(), b"Not Found")


def run_live_server(port: int = DEFAULT_PORT) -> None:
    async def serve() -> None:
        async with ws_serve(
            _ws_handler,
            "",
            port,
            process_request=_process_request,
        ):
            print(f"Live reporter running at http://localhost:{port}")
            print("Press Ctrl+C to stop")
            await asyncio.get_running_loop().create_future()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("\nStopped")


class WebReporter(PluginBase):
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self._port = port
        self._ws: Any = None
        self._total_tests = 0
        self._session_target: str = ""

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

    def on_session_start(self) -> None:
        try:
            self._ws = ws_connect(f"ws://localhost:{self._port}/ws")
            print(f"Connected to live reporter at http://localhost:{self._port}")
        except Exception:
            print(f"Live reporter not running. Start with: protest live")
            self._ws = None

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        self._total_tests = len(items)
        self._send(
            "SESSION_START",
            {"target": self._session_target, "totalTests": self._total_tests},
        )
        return items

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
        if include_error and result.error:
            payload["message"] = str(result.error)
            payload["traceback"] = _format_traceback(result.error)
        return payload
