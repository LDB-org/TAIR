#!/usr/bin/env python3
"""A small, standard-library-only TCP connect port scanner.

Usage:
    python scanner.py --host IPV4 --ports SPEC [--timeout SECONDS] [--workers N] [--json]

Only a single IPv4 literal host is accepted (no hostnames, CIDR, or IPv6).
Ports are given as a comma-separated mix of individual ports and inclusive
ranges, e.g. ``22,80,8000-8002``.

Importing this module does not start a scan or parse CLI arguments.
"""

import argparse
import ipaddress
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 0.5
DEFAULT_WORKERS = 32
MIN_PORT = 1
MAX_PORT = 65535
MIN_WORKERS = 1
MAX_WORKERS = 256


# ---------------------------------------------------------------------------
# Port specification parsing
# ---------------------------------------------------------------------------

def parse_ports(spec):
    """Parse a port specification into a sorted, de-duplicated list of ports.

    ``spec`` is a comma-separated mix of individual ports and inclusive ranges
    (e.g. ``"22,80,8000-8002"``). Whitespace is trimmed. Valid ports are
    1..65535. Empty/malformed entries, reversed ranges and invalid ports raise
    ``ValueError``.
    """
    if spec is None:
        raise ValueError("no port specification given")

    ports = set()
    for raw in spec.split(","):
        token = raw.strip()
        if not token:
            raise ValueError("empty port entry in specification")

        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2:
                raise ValueError("malformed range: %r" % token)
            lo_s, hi_s = parts[0].strip(), parts[1].strip()
            if not lo_s or not hi_s:
                raise ValueError("malformed range: %r" % token)
            try:
                lo = int(lo_s)
                hi = int(hi_s)
            except ValueError:
                raise ValueError("non-integer port in range: %r" % token)
            if lo > hi:
                raise ValueError("reversed range: %r" % token)
            if lo < MIN_PORT or hi > MAX_PORT:
                raise ValueError("port out of range in %r" % token)
            for p in range(lo, hi + 1):
                ports.add(p)
        else:
            try:
                p = int(token)
            except ValueError:
                raise ValueError("non-integer port: %r" % token)
            if p < MIN_PORT or p > MAX_PORT:
                raise ValueError("port out of range: %r" % token)
            ports.add(p)

    if not ports:
        raise ValueError("no valid ports in specification")

    return sorted(ports)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _probe(host, port, timeout):
    """Attempt a single TCP connect to ``host:port``.

    Returns ``True`` if the port is open, ``False`` otherwise. The socket is
    always closed. Connection errors are treated as "not open" (normal).
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


def scan(host, ports, timeout=DEFAULT_TIMEOUT, workers=DEFAULT_WORKERS):
    """Scan ``ports`` on ``host`` using a bounded thread pool.

    Returns a sorted list of open ports. The number of concurrent connection
    attempts is bounded by ``workers`` (no thread is spawned per port).
    """
    open_ports = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_probe, host, port, timeout): port for port in ports
        }
        for future in as_completed(futures):
            port = futures[future]
            try:
                if future.result():
                    open_ports.append(port)
            except Exception:
                # A probe failure is a normal "not open" result.
                pass
    return sorted(open_ports)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="scanner.py",
        description="TCP connect port scanner for a single IPv4 host.",
    )
    parser.add_argument(
        "--host",
        required=True,
        help="IPv4 literal address to scan (e.g. 127.0.0.1).",
    )
    parser.add_argument(
        "--ports",
        required=True,
        help="Comma-separated ports and inclusive ranges, e.g. 22,80,8000-8002.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Connection timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Maximum concurrent connection attempts (default: %(default)s).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object on stdout.",
    )
    return parser


def _validate_host(host):
    """Validate that ``host`` is a single IPv4 literal. Returns the string."""
    try:
        addr = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        raise argparse.ArgumentTypeError(
            "host must be a single IPv4 literal (no hostname, CIDR, or IPv6)"
        )
    return str(addr)


def _validate_timeout(value):
    if value is None or value != value:  # NaN check
        raise argparse.ArgumentTypeError("timeout must be a finite number")
    if value <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return value


def _validate_workers(value):
    if value < MIN_WORKERS or value > MAX_WORKERS:
        raise argparse.ArgumentTypeError(
            "workers must be an integer from %d through %d" % (MIN_WORKERS, MAX_WORKERS)
        )
    return value


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate host.
    try:
        host = _validate_host(args.host)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    # Validate timeout.
    try:
        timeout = _validate_timeout(args.timeout)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    # Validate workers.
    try:
        workers = _validate_workers(args.workers)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    # Parse ports (raises ValueError -> exit code 2).
    try:
        ports = parse_ports(args.ports)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        open_ports = scan(host, ports, timeout=timeout, workers=workers)
    except KeyboardInterrupt:
        print("\nScan interrupted.", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps({"host": host, "open_ports": open_ports}))
    else:
        if open_ports:
            print("Open ports on %s:" % host)
            for port in open_ports:
                print("  %d/tcp open" % port)
        else:
            print("No open ports found on %s." % host)

    return 0


if __name__ == "__main__":
    sys.exit(main())
