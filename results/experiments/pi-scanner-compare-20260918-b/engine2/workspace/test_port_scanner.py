#!/usr/bin/env python3
"""Unit tests for port_scanner.py.

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

import port_scanner

WORKDIR = Path(__file__).resolve().parent
SCANNER = WORKDIR / "port_scanner.py"


class PortSpecTests(unittest.TestCase):
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
        self.assertEqual(port_scanner.parse_port_spec(" 80 , 443-444 "), [80, 443, 444])

    def test_invalid_port(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("abc")

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("0")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("65536")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("1-65536")

    def test_reversed_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("8000-7999")

    def test_malformed_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("80-")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("-80")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("80-90-100")

    def test_empty_spec(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec("")
        with self.assertRaises(ValueError):
            port_scanner.parse_port_spec(",")


class LoopbackListener:
    """A temporary TCP listener bound to 127.0.0.1 on an ephemeral port."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()

    def _accept_loop(self):
        self.sock.settimeout(0.2)
        while not self.stop_event.is_set():
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def close(self):
        self.stop_event.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self.thread.join(timeout=1)


def find_unused_loopback_port():
    """Bind a socket to 127.0.0.1:0, get the port, then close it.

    The port is guaranteed to be non-listening at the moment of the scan
    because no listener is started on it.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ScannerFunctionTests(unittest.TestCase):
    def test_open_and_closed_detection(self):
        listener = LoopbackListener()
        try:
            closed_port = find_unused_loopback_port()
            open_ports, closed_ports = port_scanner.scan_ports(
                "127.0.0.1", [listener.port, closed_port], timeout=0.5, workers=2
            )
            self.assertEqual(open_ports, [listener.port])
            self.assertEqual(closed_ports, [closed_port])
        finally:
            listener.close()

    def test_connection_refused_and_timeout_count_as_closed(self):
        listener = LoopbackListener()
        try:
            # A bound but non-listening port should produce connection refused.
            closed_port = find_unused_loopback_port()
            open_ports, closed_ports = port_scanner.scan_ports(
                "127.0.0.1", [closed_port], timeout=0.5, workers=1
            )
            self.assertEqual(open_ports, [])
            self.assertEqual(closed_ports, [closed_port])
        finally:
            listener.close()


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
        self.assertIn("usage:", result.stdout)
        self.assertIn("--host", result.stdout)
        self.assertIn("--ports", result.stdout)
        self.assertIn("--timeout", result.stdout)
        self.assertIn("--workers", result.stdout)

    def test_cli_open_and_closed_detection(self):
        listener = LoopbackListener()
        try:
            closed_port = find_unused_loopback_port()
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
            listener.close()

    def test_cli_mixed_ranges_and_duplicates(self):
        listener = LoopbackListener()
        try:
            closed1 = find_unused_loopback_port()
            closed2 = find_unused_loopback_port()
            while closed2 == closed1:
                closed2 = find_unused_loopback_port()
            spec = (
                f"{listener.port},{closed1},{closed2},"
                f"{listener.port}-{listener.port},{closed1}"
            )
            result = self.run_cli(
                [
                    "--host", "127.0.0.1",
                    "--ports", spec,
                    "--timeout", "0.5",
                    "--workers", "3",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["open_ports"], [listener.port])
            self.assertEqual(data["closed_ports"], sorted([closed1, closed2]))
        finally:
            listener.close()

    def test_cli_invalid_port_spec(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "abc", "--timeout", "0.5", "--workers", "1"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)

    def test_cli_reversed_range(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "8000-7999", "--timeout", "0.5", "--workers", "1"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)

    def test_cli_invalid_timeout(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "0", "--workers", "1"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)

    def test_cli_invalid_workers(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "0.5", "--workers", "0"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)

    def test_cli_dns_error(self):
        result = self.run_cli(
            ["--host", "definitely-not-a-real-host.invalid", "--ports", "80", "--timeout", "0.5", "--workers", "1"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
