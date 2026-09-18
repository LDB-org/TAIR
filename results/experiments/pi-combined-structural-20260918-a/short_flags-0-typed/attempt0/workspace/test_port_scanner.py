#!/usr/bin/env python3
"""Unit tests for port_scanner.py.

All network tests stay on 127.0.0.1. They use temporary loopback TCP
listeners and guaranteed non-listening bound ports.
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

# Make the scanner module importable from the same directory as this test.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import port_scanner  # noqa: E402

WORKDIR = Path(__file__).resolve().parent
SCANNER = WORKDIR / "port_scanner.py"


class TemporaryListener:
    """A temporary TCP listener bound to 127.0.0.1 on an ephemeral port."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        self.sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def find_non_listening_port() -> int:
    """Find a port that is bound but not listening.

    Binding a socket to an ephemeral port and keeping it bound without
    calling listen() guarantees that connect() to that port is refused.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    # Keep the socket open so the port remains bound and non-listening.
    # The caller is responsible for closing it.
    return sock, port


class ParsePortSpecTests(unittest.TestCase):
    def test_mixed_ranges_and_duplicates(self):
        self.assertEqual(
            port_scanner.parse_port_spec("80,443,8000-8002,80,443,8001"),
            [80, 443, 8000, 8001, 8002],
        )

    def test_single_port(self):
        self.assertEqual(port_scanner.parse_port_spec("22"), [22])

    def test_range(self):
        self.assertEqual(port_scanner.parse_port_spec("1000-1003"), [1000, 1001, 1002, 1003])

    def test_whitespace(self):
        self.assertEqual(port_scanner.parse_port_spec(" 80 , 443 , 8000 - 8001 "), [80, 443, 8000, 8001])

    def test_empty_spec_rejected(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("")

    def test_malformed_item_rejected(self):
        for spec in ["abc", "80,", ",80", "80,,443", "80-", "-80", "80-90-100"]:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    port_scanner.parse_port_spec(spec)

    def test_out_of_range_rejected(self):
        for spec in ["0", "65536", "1-0", "0-10", "10-65536", "1-70000"]:
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    port_scanner.parse_port_spec(spec)

    def test_reversed_range_rejected(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("8000-7999")


class ScannerFunctionTests(unittest.TestCase):
    def test_open_and_closed_detection(self):
        with TemporaryListener() as listener:
            closed_sock, closed_port = find_non_listening_port()
            try:
                open_ports, closed_ports = port_scanner.scan_ports(
                    "127.0.0.1", [listener.port, closed_port], timeout=0.5, workers=2
                )
                self.assertEqual(open_ports, [listener.port])
                self.assertEqual(closed_ports, [closed_port])
            finally:
                closed_sock.close()

    def test_dns_error_raises(self):
        with self.assertRaises(ValueError):
            port_scanner.scan_ports(
                "definitely-not-a-real-host.invalid", [80], timeout=0.5, workers=1
            )


class CliTests(unittest.TestCase):
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
        self.assertIn("usage:", result.stdout.lower())
        self.assertIn("--host", result.stdout)
        self.assertIn("--ports", result.stdout)
        self.assertIn("--timeout", result.stdout)
        self.assertIn("--workers", result.stdout)

    def test_cli_open_and_closed_detection(self):
        with TemporaryListener() as listener:
            closed_sock, closed_port = find_non_listening_port()
            try:
                result = self.run_cli(
                    [
                        "--host", "127.0.0.1",
                        "--ports", f"{listener.port},{closed_port}",
                        "--timeout", "0.5",
                        "--workers", "2",
                    ]
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data["host"], "127.0.0.1")
                self.assertEqual(data["open_ports"], [listener.port])
                self.assertEqual(data["closed_ports"], [closed_port])
            finally:
                closed_sock.close()

    def test_cli_mixed_ranges_duplicates(self):
        with TemporaryListener() as listener:
            closed_sock, closed_port = find_non_listening_port()
            try:
                spec = (
                    f"{listener.port},{closed_port},"
                    f"{listener.port}-{listener.port},"
                    f"{closed_port}-{closed_port}"
                )
                result = self.run_cli(
                    [
                        "--host", "127.0.0.1",
                        "--ports", spec,
                        "--timeout", "0.5",
                        "--workers", "2",
                    ]
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data["open_ports"], [listener.port])
                self.assertEqual(data["closed_ports"], [closed_port])
            finally:
                closed_sock.close()

    def test_cli_invalid_ports(self):
        for spec in ["0", "65536", "80-", "80-70", "abc", "80,,443"]:
            with self.subTest(spec=spec):
                result = self.run_cli(
                    ["--host", "127.0.0.1", "--ports", spec, "--timeout", "0.5", "--workers", "1"]
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_cli_invalid_timeout(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "0", "--workers", "1"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_cli_invalid_workers(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "0.5", "--workers", "0"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_cli_dns_error(self):
        result = self.run_cli(
            [
                "--host", "definitely-not-a-real-host.invalid",
                "--ports", "80",
                "--timeout", "0.5",
                "--workers", "1",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
