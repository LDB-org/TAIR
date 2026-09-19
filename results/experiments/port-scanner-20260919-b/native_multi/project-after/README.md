# TCP Port Scanner

A small, dependency-free Python 3 TCP **connect** port scanner built entirely
on the standard library. It scans a single IPv4 host for open TCP ports using
bounded concurrency.

> **⚠️ Authorized use only.** Only scan systems you own or have explicit
> permission to test. Port scanning can be considered intrusive and may be
> illegal on systems you are not authorized to assess.

## Features

- Single IPv4 host only (no hostnames, CIDR, or IPv6).
- Comma-separated port specification with inclusive ranges.
- Bounded concurrent connection attempts (thread pool, not one thread per port).
- Every socket is closed; no resource leaks.
- JSON output mode for machine-readable results.
- Graceful Ctrl-C handling (no traceback).
- Importing the module does not start a scan or parse CLI arguments.

## Requirements

- Python 3.7+ (standard library only; no third-party packages).

## Usage

```
python scanner.py --host IPV4 --ports SPEC [--timeout SECONDS] [--workers N] [--json]
```

### Arguments

| Argument      | Description                                                       | Default |
|---------------|-------------------------------------------------------------------|---------|
| `--host`      | IPv4 literal to scan (e.g. `127.0.0.1`). Required.                | —       |
| `--ports`     | Comma-separated ports and inclusive ranges, e.g. `22,80,8000-8002`. Required. | — |
| `--timeout`   | Connection timeout in seconds (finite, > 0).                      | `0.5`   |
| `--workers`   | Number of concurrent workers, integer 1–256.                      | `32`    |
| `--json`      | Emit a single JSON object on stdout.                              | off     |

### Examples

Scan a few ports on localhost:

```
python scanner.py --host 127.0.0.1 --ports 22,80,443
```

Scan a range with a custom timeout and worker count:

```
python scanner.py --host 192.168.1.10 --ports 1-1024 --timeout 1 --workers 64
```

Machine-readable output:

```
python scanner.py --host 127.0.0.1 --ports 22,80,8000-8002 --json
```

Example JSON output:

```json
{"host": "127.0.0.1", "open_ports": [8000, 8001]}
```

### Exit codes

- `0` — scan completed (even if no ports are open).
- `2` — invalid command-line arguments (argparse).
- `130` — interrupted by Ctrl-C.

## Port specification

`--ports` accepts a comma-separated mix of individual ports and inclusive
ranges. Whitespace is trimmed, entries are de-duplicated, and the final list is
sorted. Valid ports are `1` through `65535`.

- `22` — a single port.
- `8000-8002` — the inclusive range 8000, 8001, 8002.
- `22,80,8000-8002` — a mix.

Empty, malformed, out-of-range, or reversed ranges (e.g. `8002-8000`) are
rejected with exit code `2`.

## Behavior

- Only **open** TCP ports are reported. Closed or unreachable ports are normal
  results and are simply omitted — they are not fatal errors.
- The scan uses a bounded `ThreadPoolExecutor` (default 32 workers) rather than
  spawning one thread per port.
- In `--json` mode, stdout contains exactly one JSON object shaped as
  `{"host": "<target>", "open_ports": [<sorted unique ports>]}` with no
  progress text. Human-readable output is used otherwise.

## Limits

- **TCP only.** UDP is not supported.
- **Single IPv4 host.** No hostnames, CIDR ranges, or IPv6.
- **Authorized systems only.** Use responsibly.

## Tests

Run the unit tests (they only use temporary sockets on `127.0.0.1`):

```
python -m unittest -v
```

The tests cover parser errors, duplicate/range handling, CLI argument
validation, and actual open/closed port detection against temporary sockets
created on loopback. No external hosts, existing services, or broad port
ranges are scanned.
