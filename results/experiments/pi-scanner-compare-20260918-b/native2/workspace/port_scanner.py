#!/usr/bin/env python3
"""A simple TCP connect port scanner using only the Python standard library.

Usage:
    python3 port_scanner.py --host HOST --ports SPEC --timeout SECONDS --workers N

SPEC accepts comma-separated ports and inclusive ranges (e.g. "80,443,8000-8100").
Ports are deduplicated, validated to be in 1..65535, and malformed or reversed
ranges are rejected.

Output is a single JSON object with keys:
    host        (string)
    open_ports  (sorted integer array)
    closed_ports(sorted integer array)
"""

import argparse
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

MIN_PORT = 1
MAX_PORT = 65535


def parse_ports(spec):
    """Parse a port specification string into a sorted, deduplicated list.

    Raises ValueError on malformed input, out-of-range ports, or reversed ranges.
    """
    if spec is None:
        raise ValueError("ports specification is required")

    ports = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty port specification element")

        if "-" in part:
            # Range
            if part.count("-") != 1:
                raise ValueError("malformed range: %r" % part)
            start_str, end_str = part.split("-")
            start_str = start_str.strip()
            end_str = end_str.strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise ValueError("malformed range: %r" % part)
            start = int(start_str)
            end = int(end_str)
            if start < MIN_PORT or end > MAX_PORT:
                raise ValueError("port out of range in %r" % part)
            if start > end:
                raise ValueError("reversed range: %r" % part)
            for p in range(start, end + 1):
                ports.add(p)
        else:
            # Single port
            if not part.isdigit():
                raise ValueError("malformed port: %r" % part)
            p = int(part)
            if p < MIN_PORT or p > MAX_PORT:
                raise ValueError("port out of range: %r" % part)
            ports.add(p)

    if not ports:
        raise ValueError("no valid ports specified")

    return sorted(ports)


def scan_port(host, port, timeout):
    """Attempt a TCP connect to host:port.

    Returns True if the connection succeeds (port open), False otherwise
    (connection refused, timeout, or any other error).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except socket.error:
        return False
    finally:
        try:
            sock.close()
        except socket.error:
            pass


def scan(host, ports, timeout, workers):
    """Scan the given ports on host using a bounded thread pool.

    Returns (open_ports, closed_ports) as sorted lists.
    """
    open_ports = []
    closed_ports = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_port = {
            executor.submit(scan_port, host, port, timeout): port for port in ports
        }
        for future in as_completed(future_to_port):
            port = future_to_port[future]
            try:
                is_open = future.result()
            except Exception:
                is_open = False
            if is_open:
                open_ports.append(port)
            else:
                closed_ports.append(port)

    return sorted(open_ports), sorted(closed_ports)


def build_parser():
    parser = argparse.ArgumentParser(
        description="TCP connect port scanner (standard library only)."
    )
    parser.add_argument("--host", required=True, help="Hostname or IP address to scan")
    parser.add_argument(
        "--ports",
        required=True,
        help="Comma-separated ports and inclusive ranges, e.g. 80,443,8000-8100",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Connection timeout in seconds (positive)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of parallel workers (positive)",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate timeout and workers.
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    if args.workers <= 0:
        print("error: --workers must be positive", file=sys.stderr)
        return 2

    # Parse ports.
    try:
        ports = parse_ports(args.ports)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    # Resolve hostname. A DNS error must exit nonzero without claiming success.
    try:
        resolved = socket.gethostbyname(args.host)
    except socket.gaierror as exc:
        print("error: could not resolve host %r: %s" % (args.host, exc), file=sys.stderr)
        return 1

    open_ports, closed_ports = scan(resolved, ports, args.timeout, args.workers)

    result = {
        "host": args.host,
        "open_ports": open_ports,
        "closed_ports": closed_ports,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
