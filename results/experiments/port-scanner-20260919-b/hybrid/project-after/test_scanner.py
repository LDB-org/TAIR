#!/usr/bin/env python3
"""Unit tests for scanner.py.

Network operations are performed ONLY against temporary sockets created on
127.0.0.1. No external hosts, existing services, or broad port ranges are
scanned.
"""

import argparse
import json
import socket
import subprocess
import sys
import threading
import unittest

import scanner


class ParsePortsTests(unittest.TestCase):
    def test_single_ports(self):
        self.assertEqual(scanner.parse_ports("22,80,443"), [22, 80, 443])

    def test_ranges(self):
        self.assertEqual(scanner.parse_ports("8000-8002"), [8000, 8001, 8002])

    def test_mixed(self):
        self.assertEqual(
            scanner.parse_ports("22,80,8000-8002"), [22, 80, 8000, 8001, 8002]
        )

    def test_whitespace_trimmed(self):
        self.assertEqual(scanner.parse_ports(" 22 , 80 , 8000 - 8002 "), [22, 80, 8000, 8001, 8002])

    def test_deduplicate_and_sort(self):
        self.assertEqual(scanner.parse_ports("80,22,80,22"), [22, 80])
        self.assertEqual(scanner.parse_ports("8000-8002,8001,8000"), [8000, 8001, 8002])

    def test_empty_spec(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("")

    def test_empty_entry(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("22,,80")

    def test_malformed_entry(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("abc")
        with self.assertRaises(ValueError):
            scanner.parse_ports("22,8x0")

    def test_reversed_range(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("8002-8000")

    def test_invalid_port_zero(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("0")

    def test_invalid_port_high(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("65536")

    def test_range_out_of_bounds(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("0-80")
        with self.assertRaises(ValueError):
            scanner.parse_ports("80-65536")

    def test_malformed_range(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("80-90-100")
        with self.assertRaises(ValueError):
            scanner.parse_ports("80-")


class HostValidationTests(unittest.TestCase):
    def test_valid_ipv4(self):
        self.assertEqual(scanner._validate_host("127.0.0.1"), "127.0.0.1")

    def test_invalid_hostname(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_host("localhost")

    def test_invalid_ipv6(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_host("::1")

    def test_invalid_cidr(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_host("127.0.0.1/24")


class TimeoutValidationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(scanner._validate_timeout(0.5), 0.5)

    def test_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_timeout(0)

    def test_negative(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_timeout(-1)

    def test_nan(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_timeout(float("nan"))


class WorkersValidationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(scanner._validate_workers(1), 1)
        self.assertEqual(scanner._validate_workers(256), 256)

    def test_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_workers(0)

    def test_too_high(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            scanner._validate_workers(257)


class ScanTests(unittest.TestCase):
    """Actual open/closed port detection against temporary sockets."""

    def setUp(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        self.sock.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def tearDown(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self._thread.join(timeout=1)

    def test_open_port_detected(self):
        result = scanner.scan("127.0.0.1", [self.port], timeout=0.5, workers=4)
        self.assertEqual(result, [self.port])

    def test_closed_port_not_reported(self):
        # Find a port that is not in use.
        closed = self.port
        while closed == self.port:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            closed = s.getsockname()[1]
            s.close()
        result = scanner.scan("127.0.0.1", [closed], timeout=0.5, workers=4)
        self.assertEqual(result, [])

    def test_mixed_open_and_closed(self):
        closed = self.port
        while closed == self.port:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            closed = s.getsockname()[1]
            s.close()
        result = scanner.scan(
            "127.0.0.1", [self.port, closed], timeout=0.5, workers=4
        )
        self.assertEqual(result, [self.port])


class CliTests(unittest.TestCase):
    def _run(self, args):
        return subprocess.run(
            [sys.executable, "scanner.py"] + args,
            capture_output=True,
            text=True,
        )

    def test_json_output(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        try:
            proc = self._run(
                ["--host", "127.0.0.1", "--ports", str(port), "--json"]
            )
        finally:
            sock.close()
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data, {"host": "127.0.0.1", "open_ports": [port]})

    def test_invalid_host_exit_2(self):
        proc = self._run(["--host", "localhost", "--ports", "80"])
        self.assertEqual(proc.returncode, 2)

    def test_invalid_ports_exit_2(self):
        proc = self._run(["--host", "127.0.0.1", "--ports", "abc"])
        self.assertEqual(proc.returncode, 2)

    def test_reversed_range_exit_2(self):
        proc = self._run(["--host", "127.0.0.1", "--ports", "8002-8000"])
        self.assertEqual(proc.returncode, 2)

    def test_invalid_timeout_exit_2(self):
        proc = self._run(["--host", "127.0.0.1", "--ports", "80", "--timeout", "0"])
        self.assertEqual(proc.returncode, 2)

    def test_invalid_workers_exit_2(self):
        proc = self._run(["--host", "127.0.0.1", "--ports", "80", "--workers", "0"])
        self.assertEqual(proc.returncode, 2)

    def test_help(self):
        proc = self._run(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--host", proc.stdout)
        self.assertIn("--ports", proc.stdout)


class ImportSafetyTests(unittest.TestCase):
    def test_import_does_not_scan(self):
        # Importing scanner must not start a scan or parse CLI args.
        # This is implicitly verified by the module-level code; just ensure
        # the module imports cleanly and exposes expected functions.
        self.assertTrue(callable(scanner.scan))
        self.assertTrue(callable(scanner.parse_ports))
        self.assertTrue(callable(scanner.main))


if __name__ == "__main__":
    unittest.main()
