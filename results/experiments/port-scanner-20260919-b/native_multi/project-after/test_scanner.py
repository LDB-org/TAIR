#!/usr/bin/env python3
"""Unit tests for scanner.py.

Network operations are performed ONLY against temporary sockets created on
127.0.0.1 within the test process. No external hosts, existing services, or
broad port ranges are scanned.
"""

import json
import socket
import subprocess
import sys
import threading
import unittest

import scanner


class ParsePortsTests(unittest.TestCase):
    """Tests for the port specification parser."""

    def test_single_ports(self):
        self.assertEqual(scanner.parse_ports("22"), [22])
        self.assertEqual(scanner.parse_ports("80,443"), [80, 443])

    def test_ranges(self):
        self.assertEqual(scanner.parse_ports("8000-8002"), [8000, 8001, 8002])

    def test_mixed(self):
        self.assertEqual(
            scanner.parse_ports("22,80,8000-8002"), [22, 80, 8000, 8001, 8002]
        )

    def test_whitespace_trimmed(self):
        self.assertEqual(scanner.parse_ports(" 22 , 80 , 8000 - 8002 "),
                         [22, 80, 8000, 8001, 8002])

    def test_deduplicated_and_sorted(self):
        self.assertEqual(
            scanner.parse_ports("80,22,80,22,8000-8001,8001"),
            [22, 80, 8000, 8001],
        )

    def test_boundaries(self):
        self.assertEqual(scanner.parse_ports("1"), [1])
        self.assertEqual(scanner.parse_ports("65535"), [65535])
        self.assertEqual(scanner.parse_ports("1-65535")[0], 1)
        self.assertEqual(scanner.parse_ports("1-65535")[-1], 65535)

    def test_empty_spec_rejected(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("")

    def test_empty_entry_rejected(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("22,,80")

    def test_malformed_entry_rejected(self):
        for spec in ("abc", "22,abc", "80-", "-80", "80-90-100", "22,  ,80"):
            with self.assertRaises(ValueError):
                scanner.parse_ports(spec)

    def test_reversed_range_rejected(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports("8002-8000")

    def test_out_of_range_rejected(self):
        for spec in ("0", "65536", "0-80", "80-65536", "-1"):
            with self.assertRaises(ValueError):
                scanner.parse_ports(spec)

    def test_none_rejected(self):
        with self.assertRaises(ValueError):
            scanner.parse_ports(None)


class ArgparseTests(unittest.TestCase):
    """Tests for CLI argument validation (exit code 2 on error)."""

    def _run(self, args):
        return subprocess.run(
            [sys.executable, "scanner.py"] + args,
            capture_output=True,
            text=True,
        )

    def test_valid_invocation_exits_zero(self):
        # Scan a single closed port on loopback; should still exit 0.
        result = self._run(["--host", "127.0.0.1", "--ports", "1"])
        self.assertEqual(result.returncode, 0)

    def test_missing_host_exits_2(self):
        result = self._run(["--ports", "80"])
        self.assertEqual(result.returncode, 2)

    def test_missing_ports_exits_2(self):
        result = self._run(["--host", "127.0.0.1"])
        self.assertEqual(result.returncode, 2)

    def test_invalid_host_exits_2(self):
        for host in ("notahost", "127.0.0.1/24", "::1", "999.1.1.1", "1.2.3"):
            result = self._run(["--host", host, "--ports", "80"])
            self.assertEqual(result.returncode, 2, host)

    def test_invalid_ports_exits_2(self):
        for ports in ("", "abc", "0", "65536", "80-70", "80-", "22,,80"):
            result = self._run(["--host", "127.0.0.1", "--ports", ports])
            self.assertEqual(result.returncode, 2, ports)

    def test_invalid_timeout_exits_2(self):
        for timeout in ("0", "-1", "abc", "inf", "nan"):
            result = self._run(
                ["--host", "127.0.0.1", "--ports", "80", "--timeout", timeout]
            )
            self.assertEqual(result.returncode, 2, timeout)

    def test_invalid_workers_exits_2(self):
        for workers in ("0", "257", "abc", "-1"):
            result = self._run(
                ["--host", "127.0.0.1", "--ports", "80", "--workers", workers]
            )
            self.assertEqual(result.returncode, 2, workers)

    def test_valid_workers_boundaries(self):
        for workers in ("1", "256"):
            result = self._run(
                ["--host", "127.0.0.1", "--ports", "80", "--workers", workers]
            )
            self.assertEqual(result.returncode, 0, workers)

    def test_json_output_shape(self):
        result = self._run(
            ["--host", "127.0.0.1", "--ports", "1", "--json"]
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["host"], "127.0.0.1")
        self.assertIn("open_ports", payload)
        self.assertIsInstance(payload["open_ports"], list)


class NetworkScanTests(unittest.TestCase):
    """Tests for actual open/closed port detection on temporary sockets."""

    def setUp(self):
        self._listener = None
        self._thread = None
        self._port = None

    def _start_listener(self):
        """Start a temporary listening socket on 127.0.0.1 and return its port."""
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(5)
        self._port = self._listener.getsockname()[1]

        def accept_loop():
            while True:
                try:
                    conn, _ = self._listener.accept()
                    conn.close()
                except OSError:
                    break

        self._thread = threading.Thread(target=accept_loop, daemon=True)
        self._thread.start()
        return self._port

    def tearDown(self):
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1)

    def test_open_port_detected(self):
        port = self._start_listener()
        self.assertTrue(scanner._check_port("127.0.0.1", port, 0.5))

    def test_closed_port_not_detected(self):
        # Bind a socket, note its port, then close it so nothing is listening.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
        s.close()
        self.assertFalse(scanner._check_port("127.0.0.1", closed_port, 0.5))

    def test_scan_ports_finds_open(self):
        port = self._start_listener()
        # Use a closed port too (bind then close).
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
        s.close()

        open_ports = scanner.scan_ports(
            "127.0.0.1", [port, closed_port], timeout=0.5, workers=4
        )
        self.assertEqual(open_ports, [port])

    def test_scan_ports_sorted_and_deduped(self):
        port = self._start_listener()
        open_ports = scanner.scan_ports(
            "127.0.0.1", [port, port, port], timeout=0.5, workers=4
        )
        self.assertEqual(open_ports, [port])

    def test_scan_no_open_returns_empty(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
        s.close()
        open_ports = scanner.scan_ports(
            "127.0.0.1", [closed_port], timeout=0.5, workers=4
        )
        self.assertEqual(open_ports, [])


class ImportSafetyTests(unittest.TestCase):
    """Importing scanner must not start a scan or parse CLI arguments."""

    def test_import_does_not_parse_args(self):
        # If importing parsed CLI args, this would raise SystemExit.
        import importlib
        mod = importlib.import_module("scanner")
        self.assertTrue(hasattr(mod, "main"))
        self.assertTrue(hasattr(mod, "scan_ports"))


if __name__ == "__main__":
    unittest.main()
