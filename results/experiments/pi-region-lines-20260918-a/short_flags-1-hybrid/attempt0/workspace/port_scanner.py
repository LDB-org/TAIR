#!/usr/bin/env python3
"""TCP connect port scanner using only the Python 3 standard library."""

import argparse
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, List, Optional, Sequence, Set, Tuple


def parse_port_spec(spec: str) -> List[int]:
    """Parse a comma-separated port specification.

    Accepts individual ports and inclusive ranges (e.g. 80,443,8000-8010).
    Returns a sorted, de-duplicated list of ports. Raises ValueError for
    malformed input, out-of-range values, or reversed ranges.
    """
    if not spec or not spec.strip():
        raise ValueError("port specification must not be empty")

    ports: Set[int] = set()
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError(f"empty port item in specification: {spec!r}")

        if "-" in part:
            if part.count("-") != 1:
                raise ValueError(f"malformed port range: {part!r}")
            left, right = part.split("-", 1)
            left = left.strip()
            right = right.strip()
            if not left or not right:
                raise ValueError(f"malformed port range: {part!r}")
            try:
                start = int(left, 10)
                end = int(right, 10)
            except ValueError:
                raise ValueError(f"invalid port range: {part!r}") from None
            if not (1 <= start <= 65535 and 1 <= end <= 65535):
                raise ValueError(f"port out of range 1..65535: {part!r}")
            if start > end:
                raise ValueError(f"reversed port range: {part!r}")
            ports.update(range(start, end + 1))
        else:
            try:
                port = int(part, 10)
            except ValueError:
                raise ValueError(f"invalid port: {part!r}") from None
            if not (1 <= port <= 65535):
                raise ValueError(f"port out of range 1..65535: {part!r}")
            ports.add(port)

    if not ports:
        raise ValueError("port specification produced no ports")
    return sorted(ports)


def scan_port(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        return result == 0
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def scan_ports(
    host: str,
    ports: Sequence[int],
    timeout: float,
    workers: int,
) -> Tuple[List[int], List[int]]:
    """Scan ports with a bounded thread pool.

    Connection refusal and timeout are treated as closed. DNS resolution is
    performed before scanning so a DNS error is reported as a failure.
    """
    # Resolve hostname before scanning. This also validates that the host is
    # resolvable and lets us use the resolved IP for all connection attempts.
    try:
        resolved = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"could not resolve host {host!r}: {exc}") from exc
    if not resolved:
        raise ValueError(f"could not resolve host {host!r}")

    # Use the first IPv4 address. This keeps all tests on 127.0.0.1 and avoids
    # unpredictable behavior from multiple addresses.
    ip = resolved[0][4][0]

    open_ports: List[int] = []
    closed_ports: List[int] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_port = {
            executor.submit(scan_port, ip, port, timeout): port for port in ports
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

    open_ports.sort()
    closed_ports.sort()
    return open_ports, closed_ports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TCP connect port scanner using only the Python standard library."
    )
    parser.add_argument("--host", "-H", required=True, help="Hostname or IP address to scan")
    parser.add_argument(
        "--ports",
        required=True,
        help="Comma-separated ports and inclusive ranges, e.g. 80,443,8000-8010",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Connection timeout in seconds (positive number)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Maximum number of parallel workers (positive integer)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")

    try:
        ports = parse_port_spec(args.ports)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        open_ports, closed_ports = scan_ports(args.host, ports, args.timeout, args.workers)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result = {
        "host": args.host,
        "open_ports": open_ports,
        "closed_ports": closed_ports,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
