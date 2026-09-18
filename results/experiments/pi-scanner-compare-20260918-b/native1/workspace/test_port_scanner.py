#!/usr/bin/env python3
"""Unit tests for port_scanner.py.

All network tests stay on 127.0.0.1 (loopback).
"""

import json
import socket
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import port_scanner


def find_free_port():
    """Find a guaranteed non-listening bound port on loopback."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class LoopbackListener:
    """A temporary TCP listener on 127.0.0.1 that accepts connections."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(128)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass
        self._thread.join(timeout=1.0)


class ParsePortsTests(unittest.TestCase):
    def test_single_ports(self):
        self.assertEqual(port_scanner.parse_ports("80"), [80])
        self.assertEqual(port_scanner.parse_ports("80,443"), [80, 443])

    def test_ranges(self):
        self.assertEqual(port_scanner.parse_ports("8000-8003"), [8000, 8001, 8002, 8003])

    def test_mixed_ranges_and_duplicates(self):
        self.assertEqual(
            port_scanner.parse_ports("80,443,8000-8002,443,80"),
            [80, 443, 8000, 8001, 8002],
        )

    def test_duplicates_deduplicated(self):
        self.assertEqual(port_scanner.parse_ports("80,80,80"), [80])

    def test_boundaries(self):
        self.assertEqual(port_scanner.parse_ports("1,65535"), [1, 65535])

    def test_malformed_port(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("abc")
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("80,abc")

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("0")
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("65536")
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("1-70000")

    def test_reversed_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("8000-7000")

    def test_malformed_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("80-")
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("-80")
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("80-90-100")

    def test_empty(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("")
        with self.assertRaises(ValueError):
            port_scanner.parse_ports(",")


class ScanFunctionTests(unittest.TestCase):
    def test_open_and_closed_detection(self):
        listener = LoopbackListener()
        try:
            closed_port = find_free_port()
            open_ports, closed_ports = port_scanner.scan(
                "127.0.0.1", [listener.port, closed_port], timeout=1.0, workers=4
            )
            self.assertEqual(open_ports, [listener.port])
            self.assertEqual(closed_ports, [closed_port])
        finally:
            listener.close()

    def test_all_closed(self):
        p1 = find_free_port()
        p2 = find_free_port()
        open_ports, closed_ports = port_scanner.scan(
            "127.0.0.1", [p1, p2], timeout=0.5, workers=4
        )
        self.assertEqual(open_ports, [])
        self.assertEqual(sorted(closed_ports), sorted([p1, p2]))


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        return subprocess.run(
            [sys.executable, "port_scanner.py"] + args,
            capture_output=True,
            text=True,
            cwd=".",
        )

    def test_help(self):
        result = self.run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--host", result.stdout)
        self.assertIn("--ports", result.stdout)
        self.assertIn("--timeout", result.stdout)
        self.assertIn("--workers", result.stdout)

    def test_cli_open_and_closed(self):
        listener = LoopbackListener()
        try:
            closed_port = find_free_port()
            result = self.run_cli(
                [
                    "--host", "127.0.0.1",
                    "--ports", "%d,%d" % (listener.port, closed_port),
                    "--timeout", "1.0",
                    "--workers", "4",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["host"], "127.0.0.1")
            self.assertEqual(data["open_ports"], [listener.port])
            self.assertEqual(data["closed_ports"], [closed_port])
        finally:
            listener.close()

    def test_cli_mixed_ranges_duplicates(self):
        listener = LoopbackListener()
        try:
            closed_port = find_free_port()
            spec = "%d,%d,%d-%d,%d" % (
                listener.port, closed_port, listener.port, listener.port, closed_port
            )
            result = self.run_cli(
                [
                    "--host", "127.0.0.1",
                    "--ports", spec,
                    "--timeout", "1.0",
                    "--workers", "4",
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["open_ports"], [listener.port])
            self.assertEqual(data["closed_ports"], [closed_port])
        finally:
            listener.close()

    def test_cli_invalid_ports(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "abc", "--timeout", "1", "--workers", "2"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_reversed_range(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "8000-7000", "--timeout", "1", "--workers", "2"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_out_of_range(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "70000", "--timeout", "1", "--workers", "2"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_bad_timeout(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "0", "--workers", "2"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_bad_workers(self):
        result = self.run_cli(
            ["--host", "127.0.0.1", "--ports", "80", "--timeout", "1", "--workers", "0"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_dns_error(self):
        result = self.run_cli(
            ["--host", "nonexistent.invalid", "--ports", "80", "--timeout", "1", "--workers", "2"]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
