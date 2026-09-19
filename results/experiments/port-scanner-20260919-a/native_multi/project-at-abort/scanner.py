#!/usr/bin/env python3
"""A simple, bounded TCP connect port scanner.

This module scans a single IPv4 host for open TCP ports. It uses only the
Python standard library and limits the number of concurrent connection
attempts so it does not spawn one thread per port.

Importing this module does not start a scan or parse command-line arguments;
that only happens when the module is run as a script.
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

MIN_PORT = 1
MAX_PORT = 65535
DEFAULT_TIMEOUT = 0.5
DEFAULT_WORKERS = 32
MIN_WORKERS = 1
MAX_WORKERS = 256


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_port_spec(spec):
    """Parse a comma-separated port specification into a sorted unique list.

    The spec is a mix of individual ports and inclusive ranges, e.g.
    "22,80,8000-8002". Whitespace is trimmed, entries are deduplicated and
    the result is sorted ascending.

    Raises argparse.ArgumentTypeError for empty/malformed entries, reversed
    ranges and out-of-range ports.
    """
    if spec is None:
        raise argparse.ArgumentTypeError("port specification is required")

    ports = set()
    for raw_entry in spec.split(","):
        entry = raw_entry.strip()
        if not entry:
            raise argparse.ArgumentTypeError(
                "empty entry in port specification"
            )

        if "-" in entry:
            parts = entry.split("-")
            if len(parts) != 2:
                raise argparse.ArgumentTypeError(
                    "malformed range: {!r}".format(entry)
                )
            start_str, end_str = parts[0].strip(), parts[1].strip()
            if not start_str or not end_str:
                raise argparse.ArgumentTypeError(
                    "malformed range: {!r}".format(entry)
                )
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                raise argparse.ArgumentTypeError(
                    "invalid port in range: {!r}".format(entry)
                )
            if start > end:
                raise argparse.ArgumentTypeError(
                    "reversed range: {!r}".format(entry)
                )
            if start < MIN_PORT or end > MAX_PORT:
                raise argparse.ArgumentTypeError(
                    "port out of range in {!r} (valid: {}-{})".format(
                        entry, MIN_PORT, MAX_PORT
                    )
                )
            for port in range(start, end + 1):
                ports.add(port)
        else:
            try:
                port = int(entry)
            except ValueError:
                raise argparse.ArgumentTypeError(
                    "invalid port: {!r}".format(entry)
                )
            if port < MIN_PORT or port > MAX_PORT:
                raise argparse.ArgumentTypeError(
                    "port out of range: {} (valid: {}-{})".format(
                        port, MIN_PORT, MAX_PORT
                    )
                )
            ports.add(port)

    if not ports:
        raise argparse.ArgumentTypeError("no valid ports in specification")

    return sorted(ports)


def _parse_host(value):
    """Validate that value is a single IPv4 literal and return it as a string."""
    try:
        addr = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise argparse.ArgumentTypeError(
            "host must be a single IPv4 literal, got {!r}".format(value)
        )
    return str(addr)


def _parse_timeout(value):
    """Validate a finite, positive timeout in seconds."""
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            "timeout must be a number, got {!r}".format(value)
        )
    if timeout <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be greater than zero, got {}".format(timeout)
        )
    if timeout == float("inf") or timeout != timeout:  # inf or NaN
        raise argparse.ArgumentTypeError(
            "timeout must be finite, got {!r}".format(value)
        )
    return timeout


def _parse_workers(value):
    """Validate an integer worker count in the range 1..256."""
    try:
        workers = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(
            "workers must be an integer, got {!r}".format(value)
        )
    if workers < MIN_WORKERS or workers > MAX_WORKERS:
        raise argparse.ArgumentTypeError(
            "workers must be between {} and {}, got {}".format(
                MIN_WORKERS, MAX_WORKERS, workers
            )
        )
    return workers


def build_parser():
    """Build and return the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="scanner.py",
        description="Scan a single IPv4 host for open TCP ports.",
        epilog=(
            "Only use this tool on systems you are authorized to scan. "
            "It supports TCP only and a single IPv4 host."
        ),
    )
    parser.add_argument(
        "--host",
        required=True,
        type=_parse_host,
        help="Single IPv4 literal to scan (e.g. 127.0.0.1).",
    )
    parser.add_argument(
        "--ports",
        required=True,
        type=_parse_port_spec,
        help=(
            "Comma-separated ports and inclusive ranges, e.g. "
            "22,80,8000-8002."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=_parse_timeout,
        default=DEFAULT_TIMEOUT,
        help="Connection timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--workers",
        type=_parse_workers,
        default=DEFAULT_WORKERS,
        help=(
            "Maximum concurrent connection attempts, 1-256 "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output a single JSON object to stdout.",
    )
    return parser


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _probe_port(host, port, timeout):
    """Attempt a TCP connection to host:port.

    Returns True if the port is open (connection established), False
    otherwise. The socket is always closed.
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


def scan_ports(host, ports, timeout=DEFAULT_TIMEOUT, workers=DEFAULT_WORKERS):
    """Scan the given ports on host and return a sorted list of open ports.

    Uses a bounded thread pool so at most ``workers`` connection attempts run
    concurrently. Closed/unreachable ports are treated as normal results.
    """
    open_ports = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_port = {
            executor.submit(_probe_port, host, port, timeout): port
            for port in ports
        }
        for future in as_completed(future_to_port):
            port = future_to_port[future]
            try:
                if future.result():
                    open_ports.append(port)
            except Exception:
                # A failed probe is a closed/unreachable port, not fatal.
                continue
    return sorted(open_ports)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def format_report(host, open_ports):
    """Return a human-readable report string."""
    lines = ["Scan of {} (TCP)".format(host)]
    if open_ports:
        lines.append("Open ports:")
        for port in open_ports:
            lines.append("  {}/tcp".format(port))
    else:
        lines.append("No open TCP ports found.")
    return "\n".join(lines)


def main(argv=None):
    """Entry point for the CLI. Returns an exit code."""
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
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Scan interrupted.", file=sys.stderr)
        sys.exit(130)
