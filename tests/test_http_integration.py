"""Actual loopback HTTP process smoke test, never connects to MT5."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def test_loopback_uvicorn_health_and_fail_closed_score():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.pop("SG_ARTIFACT", None)
    env.pop("SG_APPROVAL", None)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scalping_gold.service:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(process.communicate()[1].decode())
            try:
                health = httpx.get(url + "/health", timeout=0.3)
                break
            except httpx.TransportError:
                time.sleep(0.05)
        else:
            raise AssertionError("service did not start within bounded smoke-test wait")
        assert health.status_code == 200 and health.json()["approved"] is False
        assert httpx.post(url + "/score", json={}, timeout=1).status_code == 422
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
