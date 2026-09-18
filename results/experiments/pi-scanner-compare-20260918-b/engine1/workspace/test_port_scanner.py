#!/usr/bin/env python3
"""Unit and subprocess tests for port_scanner.py.

All network tests use 127.0.0.1 only.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent
SCANNER = WORKDIR / "port_scanner.py"


def find_free_port() -> int:
    """Return a currently free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_listener(port: int, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            try:
                s.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.02)
    raise RuntimeError(f"listener on port {port} did not become ready")


class PortSpecTests(unittest.TestCase):
    def test_mixed_ranges_and_duplicates(self):
        import port_scanner

        self.assertEqual(
            port_scanner.parse_port_spec("80,443,8000-8002,80,443,8001"),
            [80, 443, 8000, 8001, 8002],
        )

    def test_single_port(self):
        import port_scanner

        self.assertEqual(port_scanner.parse_port_spec("22"), [22])

    def test_invalid_empty(self):
        import port_scanner

        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("")

    def test_invalid_non_numeric(self):
        import port_scanner

        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("abc")

    def test_invalid_out_of_range(self):
        import port_scanner

        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("0")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("65536")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("1-70000")

    def test_invalid_reversed_range(self):
        import port_scanner

        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("8000-80")

    def test_invalid_malformed_range(self):
        import port_scanner

        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("80-")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("-80")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("80-90-100")


class ScanFunctionTests(unittest.TestCase):
    def test_open_and_closed_detection(self):
        import port_scanner

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        port = listener.getsockname()[1]
        stop = threading.Event()

        def accept_loop():
            listener.settimeout(0.2)
            while not stop.is_set():
                try:
                    conn, _ = listener.accept()
                    conn.close()
                except socket.timeout:
                    continue
                except OSError:
                    break

        thread = threading.Thread(target=accept_loop, daemon=True)
        thread.start()
        try:
            wait_for_listener(port)
            closed_port = find_free_port()
            open_ports, closed_ports = port_scanner.scan_ports(
                "127.0.0.1", [port, closed_port], timeout=0.2, workers=2
            )
            self.assertEqual(open_ports, [port])
            self.assertEqual(closed_ports, [closed_port])
        finally:
            stop.set()
            thread.join(timeout=1)
            listener.close()


class SubprocessCliTests(unittest.TestCase):
    def run_cli(self, args, timeout=10):
        return subprocess.run(
            [sys.executable, str(SCANNER)] + args,
            cwd=str(WORKDIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_help(self):
        result = self.run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
        self.assertIn("--host", result.stdout)
        self.assertIn("--ports", result.stdout)
        self.assertIn("--timeout", result.stdout)
        self.assertIn("--workers", result.stdout)

    def test_cli_open_and_closed_detection(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        port = listener.getsockname()[1]
        stop = threading.Event()

        def accept_loop():
            listener.settimeout(0.2)
            while not stop.is_set():
                try:
                    conn, _ = listener.accept()
                    conn.close()
                except socket.timeout:
                    continue
                except OSError:
                    break

        thread = threading.Thread(target=accept_loop, daemon=True)
        thread.start()
        try:
            wait_for_listener(port)
            closed_port = find_free_port()
            result = self.run_cli(
                [
                    "--host",
                    "127.0.0.1",
                    "--ports",
                    f"{port},{closed_port}",
                    "--timeout",
                    "0.2",
                    "--workers",
                    "2",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["host"], "127.0.0.1")
            self.assertEqual(data["open_ports"], [port])
            self.assertEqual(data["closed_ports"], [closed_port])
        finally:
            stop.set()
            thread.join(timeout=1)
            listener.close()

    def test_cli_mixed_ranges_duplicates(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        port = listener.getsockname()[1]
        stop = threading.Event()

        def accept_loop():
            listener.settimeout(0.2)
            while not stop.is_set():
                try:
                    conn, _ = listener.accept()
                    conn.close()
                except socket.timeout:
                    continue
                except OSError:
                    break

        thread = threading.Thread(target=accept_loop, daemon=True)
        thread.start()
        try:
            wait_for_listener(port)
            closed1 = find_free_port()
            closed2 = find_free_port()
            while closed2 == port or closed2 == closed1:
                closed2 = find_free_port()
            spec = f"{port},{port},{closed1}-{closed1},{closed2},{closed1}"
            result = self.run_cli(
                [
                    "--host",
                    "127.0.0.1",
                    "--ports",
                    spec,
                    "--timeout",
                    "0.2",
                    "--workers",
                    "3",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["open_ports"], [port])
            self.assertEqual(data["closed_ports"], sorted([closed1, closed2]))
        finally:
            stop.set()
            thread.join(timeout=1)
            listener.close()

    def test_invalid_input_nonzero(self):
        cases = [
            ["--host", "127.0.0.1", "--ports", "0"],
            ["--host", "127.0.0.1", "--ports", "65536"],
            ["--host", "127.0.0.1", "--ports", "80-"],
            ["--host", "127.0.0.1", "--ports", "80-70"],
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "0"],
            ["--host", "127.0.0.1", "--ports", "80", "--workers", "0"],
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "-1"],
            ["--host", "127.0.0.1", "--ports", "80", "--workers", "-1"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_cli(args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("error:", result.stderr)

    def test_dns_error_nonzero(self):
        result = self.run_cli(
            [
                "--host",
                "definitely-not-a-real-host.invalid",
                "--ports",
                "80",
                "--timeout",
                "0.2",
                "--workers",
                "1",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
