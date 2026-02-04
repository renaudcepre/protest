"""Test to reproduce blocking sync call - shared client closed by first test."""

import os
import threading
import time
from collections.abc import Generator
from typing import Annotated

from protest import ProTestSession, Use, fixture

session = ProTestSession()


# =============================================================================
# Simule @cached_provider + générateur qui ferme le client (comme weaviate)
# =============================================================================


class FakeClient:
    """Simule un client gRPC/weaviate qui bloque sur opérations si fermé."""

    def __init__(self):
        self._closed = False
        self._lock = threading.Lock()
        print(f"[FakeClient] Created id={id(self)}")

    def do_something(self):
        """Opération qui bloque indéfiniment si le client est fermé."""
        if self._closed:
            print(
                f"[FakeClient {id(self)}] Client is closed! Blocking forever (C code)...",
                flush=True,
            )
            # Simule un appel gRPC bloquant sur client fermé
            # os.read() sur un pipe vide bloque sans libérer le GIL

            r, _ = os.pipe()
            os.read(r, 1)  # Bloque indéfiniment, GIL non libéré
        return "OK"

    def close(self):
        print(f"[FakeClient {id(self)}] close() called")
        self._closed = True


# Singleton global (comme @cached_provider)
_cached_client: FakeClient | None = None
_cache_lock = threading.Lock()


def _get_cached_client() -> FakeClient:
    """Simule @cached_provider."""
    global _cached_client
    with _cache_lock:
        if _cached_client is None:
            _cached_client = FakeClient()
        return _cached_client


@fixture()
def client_override() -> Generator[FakeClient, None, None]:
    """Simule weaviate_client_override - LE PROBLÈME EST ICI!

    Le client est partagé via _get_cached_client() mais chaque test
    qui finit appelle close() dans finally!
    """
    client = _get_cached_client()
    print(f"[client_override] Yielding client id={id(client)}")
    try:
        yield client
    finally:
        # BUG: ferme le client partagé!
        print(f"[client_override] FINALLY - closing client id={id(client)}")
        client.close()


# =============================================================================
# Tests
# =============================================================================


@session.test()
def test_1(client: Annotated[FakeClient, Use(client_override)]):
    """Premier test - rapide."""
    print(f"[test_1] Using client id={id(client)}")
    result = client.do_something()
    print(f"[test_1] Got: {result}")
    time.sleep(0.3)
    print("[test_1] Done")


@session.test()
def test_2(client: Annotated[FakeClient, Use(client_override)]):
    """Deuxième test - plus lent, risque de bloquer."""
    print(f"[test_2] Using client id={id(client)}")
    time.sleep(0.5)  # Laisse le temps au test_1 de finir et fermer le client
    print("[test_2] Calling do_something()...")
    result = client.do_something()  # BLOQUE si client fermé!
    print(f"[test_2] Got: {result}")
    print("[test_2] Done")


@session.test()
def test_3(client: Annotated[FakeClient, Use(client_override)]):
    """Troisième test."""
    print(f"[test_3] Using client id={id(client)}")
    time.sleep(0.6)
    print("[test_3] Calling do_something()...")
    result = client.do_something()  # BLOQUE si client fermé!
    print(f"[test_3] Got: {result}")
    print("[test_3] Done")


@session.test()
def test_4(client: Annotated[FakeClient, Use(client_override)]):
    """Quatrième test."""
    print(f"[test_4] Using client id={id(client)}")
    time.sleep(0.7)
    result = client.do_something()
    print(f"[test_4] Got: {result}")
    print("[test_4] Done")


@session.test()
def test_5(client: Annotated[FakeClient, Use(client_override)]):
    """Cinquième test."""
    print(f"[test_5] Using client id={id(client)}")
    time.sleep(0.8)
    result = client.do_something()
    print(f"[test_5] Got: {result}")
    print("[test_5] Done")


if __name__ == "__main__":
    print("Run with: uv run protest run test_blocking:session -n 3 --no-capture")
