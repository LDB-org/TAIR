#!/usr/bin/env python3
"""A simple, bounded-concurrency TCP connect port scanner.

This module scans a single IPv4 host for open TCP ports using the standard
library only. It is intended for use on systems you are authorized to scan.

Importing this module does NOT start a scan or parse command-line arguments;
that only happens when the module is run as ``__main__``.
"""

import argparse
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_TIMEOUT = 0.5
DEFAULT_WORKERS = 32
MAX_WORKERS = 256


# ---------------------------------------------------------------------------
# Argument parsing / validation
# ---------------------------------------------------------------------------

class ScannerArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 2 on error (argparse default)."""


def _parse_port_token(token):
    """Parse a single port token (either a port or an inclusive range).

    Returns a list of ports. Raises ValueError on malformed input, invalid
    ports, or reversed ranges.
    """
    token = token.strip()
    if not token:
        raise ValueError("empty port entry")

    if "-" in token:
        parts = token.split("-")
        if len(parts) != 2:
            raise ValueError("malformed range: %r" % token)
        start_s, end_s = parts[0].strip(), parts[1].strip()
        if not start_s or not end_s:
            raise ValueError("malformed range: %r" % token)
        try:
            start = int(start_s)
            end = int(end_s)
        except ValueError:
            raise ValueError("non-integer port in range: %r" % token)
        if not (MIN_PORT <= start <= MAX_PORT and MIN_PORT <= end <= MAX_PORT):
            raise ValueError("port out of range in %r" % token)
        if start > end:
            raise ValueError("reversed range: %r" % token)
        return list(range(start, end + 1))
    else:
        try:
            port = int(token)
        except ValueError:
            raise ValueError("non-integer port: %r" % token)
        if not (MIN_PORT <= port <= MAX_PORT):
            raise ValueError("port out of range: %r" % token)
        return [port]


def parse_ports(spec):
    """Parse a comma-separated port specification.

    Returns a sorted, de-duplicated list of ports. Raises ValueError on any
    empty, malformed, out-of-range, or reversed entry.
    """
    if spec is None:
        raise ValueError("no port specification given")

    ports = []
    for raw in spec.split(","):
        ports.extend(_parse_port_token(raw))

    if not ports:
        raise ValueError("no ports specified")

    # De-duplicate and sort.
    return sorted(set(ports))


def _positive_float(value):
    """argparse type: a finite float greater than zero."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("timeout must be a number")
    if f != f or f in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("timeout must be finite")
    if f <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return f


def _worker_count(value):
    """argparse type: an integer from 1 through 256."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("workers must be an integer")
    if not (1 <= n <= MAX_WORKERS):
        raise argparse.ArgumentTypeError(
            "workers must be an integer from 1 through %d" % MAX_WORKERS
        )
    return n


def _ipv4_literal(value):
    """argparse type: a single IPv4 literal (no hostname, CIDR, or IPv6)."""
    if "/" in value:
        raise argparse.ArgumentTypeError("CIDR notation is not supported")
    if ":" in value:
        raise argparse.ArgumentTypeError("IPv6 addresses are not supported")
    parts = value.split(".")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected a single IPv4 address")
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError("expected a single IPv4 address")
    if any(o < 0 or o > 255 for o in octets):
        raise argparse.ArgumentTypeError("expected a single IPv4 address")
    return value


def build_parser():
    """Build and return the argument parser (does not parse anything)."""
    parser = ScannerArgumentParser(
        prog="scanner.py",
        description="Scan a single IPv4 host for open TCP ports.",
    )
    parser.add_argument(
        "--host",
        required=True,
        type=_ipv4_literal,
        help="IPv4 address to scan (e.g. 127.0.0.1)",
    )
    parser.add_argument(
        "--ports",
        required=True,
        type=parse_ports,
        help="Comma-separated ports and inclusive ranges, e.g. 22,80,8000-8002",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT,
        help="Connection timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--workers",
        type=_worker_count,
        default=DEFAULT_WORKERS,
        help="Number of concurrent workers, 1-%d (default: %s)"
        % (MAX_WORKERS, DEFAULT_WORKERS),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as a single JSON object on stdout",
    )
    return parser


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _check_port(host, port, timeout):
    """Attempt a TCP connect to ``host:port``.

    Returns True if the port is open, False otherwise. Every socket is closed.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except OSError:
        return False
    finally:
        sock.close()


def scan_ports(host, ports, timeout=DEFAULT_TIMEOUT, workers=DEFAULT_WORKERS):
    """Scan ``ports`` on ``host`` using a bounded thread pool.

    Returns a sorted list of open ports. Closed/unreachable ports are treated
    as normal results and are simply omitted.
    """
    open_ports = []
    unique_ports = sorted(set(ports))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_port = {
            executor.submit(_check_port, host, port, timeout): port
            for port in unique_ports
        }
        for future in as_completed(future_to_port):
            port = future_to_port[future]
            try:
                if future.result():
                    open_ports.append(port)
            except Exception:
                # Any unexpected error means the port is not reachable.
                continue
    return sorted(open_ports)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def format_report(host, open_ports):
    """Return a human-readable report string."""
    lines = ["Scan of %s" % host]
    if open_ports:
        lines.append("Open TCP ports:")
        for port in open_ports:
            lines.append("  %d/tcp open" % port)
    else:
        lines.append("No open TCP ports found.")
    return "\n".join(lines)


def main(argv=None):
    """Entry point. Returns an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        open_ports = scan_ports(
            args.host, args.ports, timeout=args.timeout, workers=args.workers
        )
    except KeyboardInterrupt:
        print("Scan interrupted.", file=sys.stderr)
        return 130

    if args.json:
        payload = {"host": args.host, "open_ports": open_ports}
        print(json.dumps(payload))
    else:
        print(format_report(args.host, open_ports))

    return 0


if __name__ == "__main__":
    sys.exit(main())
