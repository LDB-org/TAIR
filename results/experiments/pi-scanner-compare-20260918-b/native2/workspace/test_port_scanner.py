#!/usr/bin/env python3
"""Unit tests for port_scanner.py.

All network tests stay on 127.0.0.1 (loopback). We use temporary loopback TCP
listeners for open ports and guaranteed non-listening bound ports for closed
ports. We also test the actual subprocess CLI behavior.
"""

import json
import socket
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager

import port_scanner


def get_free_port():
    """Bind a socket to an ephemeral port on loopback, then close it.

    The port is guaranteed to be non-listening after we close the socket.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextmanager
def listening_server(port):
    """Start a TCP listener on 127.0.0.1:port that accepts and closes connections."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(5)
    server.settimeout(0.1)

    stop = threading.Event()

    def accept_loop():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        stop.set()
        try:
            server.close()
        except OSError:
            pass
        thread.join(timeout=1.0)


class ParsePortsTests(unittest.TestCase):
    def test_single_ports(self):
        self.assertEqual(port_scanner.parse_ports("80"), [80])
        self.assertEqual(port_scanner.parse_ports("80,443"), [80, 443])

    def test_ranges(self):
        self.assertEqual(port_scanner.parse_ports("8000-8003"), [8000, 8001, 8002, 8003])

    def test_mixed_ranges_and_duplicates(self):
        self.assertEqual(
            port_scanner.parse_ports("80,443,8000-8002,80,443,8001"),
            [80, 443, 8000, 8001, 8002],
        )

    def test_dedup_sorted(self):
        self.assertEqual(port_scanner.parse_ports("5,3,1,3,5"), [1, 3, 5])

    def test_boundaries(self):
        self.assertEqual(port_scanner.parse_ports("1"), [1])
        self.assertEqual(port_scanner.parse_ports("65535"), [65535])
        self.assertEqual(port_scanner.parse_ports("1-65535")[0], 1)
        self.assertEqual(port_scanner.parse_ports("1-65535")[-1], 65535)

    def test_invalid_port_zero(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("0")

    def test_invalid_port_too_high(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("65536")

    def test_malformed_non_numeric(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("abc")

    def test_malformed_empty_element(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("80,,443")

    def test_reversed_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("8000-7000")

    def test_malformed_range(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("80-90-100")

    def test_empty_spec(self):
        with self.assertRaises(ValueError):
            port_scanner.parse_ports("")


class ScanFunctionTests(unittest.TestCase):
    def test_open_and_closed_detection(self):
        open_port = get_free_port()
        closed_port = get_free_port()
        with listening_server(open_port):
            open_ports, closed_ports = port_scanner.scan(
                "127.0.0.1", [open_port, closed_port], timeout=1.0, workers=2
            )
        self.assertEqual(open_ports, [open_port])
        self.assertEqual(closed_ports, [closed_port])

    def test_all_closed(self):
        p1 = get_free_port()
        p2 = get_free_port()
        open_ports, closed_ports = port_scanner.scan(
            "127.0.0.1", [p1, p2], timeout=0.5, workers=2
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
        open_port = get_free_port()
        closed_port = get_free_port()
        with listening_server(open_port):
            result = self.run_cli(
                [
                    "--host", "127.0.0.1",
                    "--ports", "%d,%d" % (open_port, closed_port),
                    "--timeout", "1.0",
                    "--workers", "2",
                ]
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["host"], "127.0.0.1")
        self.assertEqual(data["open_ports"], [open_port])
        self.assertEqual(data["closed_ports"], [closed_port])

    def test_cli_mixed_ranges_duplicates(self):
        open_port = get_free_port()
        closed_port = get_free_port()
        with listening_server(open_port):
            result = self.run_cli(
                [
                    "--host", "127.0.0.1",
                    "--ports",
                    "%d,%d,%d-%d,%d" % (open_port, closed_port, open_port, open_port, closed_port),
                    "--timeout", "1.0",
                    "--workers", "2",
                ]
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["open_ports"], [open_port])
        self.assertEqual(data["closed_ports"], [closed_port])

    def test_cli_dns_error(self):
        result = self.run_cli(
            [
                "--host", "nonexistent.invalid.example",
                "--ports", "80",
                "--timeout", "1.0",
                "--workers", "2",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_cli_invalid_ports(self):
        result = self.run_cli(
            [
                "--host", "127.0.0.1",
                "--ports", "8000-7000",
                "--timeout", "1.0",
                "--workers", "2",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_cli_invalid_timeout(self):
        result = self.run_cli(
            [
                "--host", "127.0.0.1",
                "--ports", "80",
                "--timeout", "0",
                "--workers", "2",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_cli_invalid_workers(self):
        result = self.run_cli(
            [
                "--host", "127.0.0.1",
                "--ports", "80",
                "--timeout", "1.0",
                "--workers", "0",
            ]
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
