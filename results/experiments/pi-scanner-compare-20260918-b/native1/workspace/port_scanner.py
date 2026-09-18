#!/usr/bin/env python3
"""A simple TCP connect port scanner using only the Python 3 standard library.

Usage:
    python3 port_scanner.py --host HOST --ports SPEC --timeout SECONDS --workers N

SPEC accepts comma-separated ports and inclusive ranges (e.g. "80,443,8000-8100").
Ports are deduplicated and validated to be in the range 1..65535.
"""

import argparse
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed


def parse_ports(spec):
    """Parse a port specification string into a sorted, deduplicated list of ports.

    Raises ValueError on malformed input, out-of-range ports, or reversed ranges.
    """
    if spec is None:
        raise ValueError("ports specification is required")

    ports = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            raise ValueError("empty port token in specification")

        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2:
                raise ValueError("malformed range: %r" % token)
            start_str, end_str = parts[0].strip(), parts[1].strip()
            if not start_str.isdigit() or not end_str.isdigit():
                raise ValueError("malformed range: %r" % token)
            start, end = int(start_str), int(end_str)
            if start > end:
                raise ValueError("reversed range: %r" % token)
            if start < 1 or end > 65535:
                raise ValueError("port out of range in: %r" % token)
            for p in range(start, end + 1):
                ports.add(p)
        else:
            if not token.isdigit():
                raise ValueError("malformed port: %r" % token)
            port = int(token)
            if port < 1 or port > 65535:
                raise ValueError("port out of range: %r" % token)
            ports.add(port)

    if not ports:
        raise ValueError("no ports specified")

    return sorted(ports)


def scan_port(host, port, timeout):
    """Attempt a TCP connect to host:port.

    Returns True if the connection succeeds (port open), False otherwise.
    Connection refusal, timeout, and other errors all count as closed.
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="TCP connect port scanner (standard library only)."
    )
    parser.add_argument("--host", required=True, help="Hostname or IP address to scan")
    parser.add_argument(
        "--ports",
        required=True,
        help="Port specification, e.g. '80,443,8000-8100'",
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
    args = parser.parse_args(argv)

    # Validate timeout and workers.
    if args.timeout <= 0:
        print("error: timeout must be positive", file=sys.stderr)
        return 2
    if args.workers <= 0:
        print("error: workers must be positive", file=sys.stderr)
        return 2

    # Parse ports.
    try:
        ports = parse_ports(args.ports)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    # Resolve hostname. A DNS error exits nonzero without claiming a successful scan.
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
