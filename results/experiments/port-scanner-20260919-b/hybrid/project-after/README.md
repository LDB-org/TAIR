# scanner.py — TCP Connect Port Scanner

A small, dependency-free (standard library only) TCP **connect** port scanner
for a single IPv4 host, written in Python 3.

## Usage

```
python scanner.py --host IPV4 --ports SPEC [--timeout SECONDS] [--workers N] [--json]
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--host` | A single IPv4 literal (e.g. `127.0.0.1`). No hostnames, CIDR, or IPv6. | required |
| `--ports` | Comma-separated mix of individual ports and inclusive ranges, e.g. `22,80,8000-8002`. Whitespace is trimmed; ports are de-duplicated and sorted. Valid ports are `1..65535`. | required |
| `--timeout` | Connection timeout in seconds. Must be finite and greater than zero. | `0.5` |
| `--workers` | Maximum concurrent connection attempts. Integer from `1` through `256`. | `32` |
| `--json` | Emit a single JSON object on stdout. | off |

### Examples

```
# Scan a few ports on localhost
python scanner.py --host 127.0.0.1 --ports 22,80,443

# Scan a range with a custom timeout and worker count
python scanner.py --host 192.168.1.10 --ports 1-1024 --timeout 1 --workers 64

# Machine-readable output
python scanner.py --host 127.0.0.1 --ports 22,80,8000-8002 --json
```

In `--json` mode, stdout is exactly one JSON object shaped like:

```json
{"host": "127.0.0.1", "open_ports": [22, 80, 8000]}
```

using the actual target host and the sorted, unique list of open ports. No
progress text is written to stdout in this mode.

Without `--json`, a readable report is printed listing the open TCP ports.

## Behavior

- Only **reachable (open) TCP ports** are reported. Closed, filtered, or
  unreachable ports are treated as normal results, not fatal errors.
- The scan exits with status `0` after a completed scan even if nothing is
  open.
- Connection attempts are **bounded** by `--workers` using a thread pool; it
  does **not** spawn one thread per port.
- Every socket is closed after use.
- Invalid arguments (bad host, malformed/empty/reversed port entries, invalid
  ports, non-positive timeout, out-of-range workers) cause `argparse` to exit
  with code `2`.
- `Ctrl-C` is handled gracefully without a traceback.
- Importing `scanner` does **not** start a scan or parse CLI arguments.

## Limits

- **TCP only.** UDP is not supported.
- **Single IPv4 host only.** No hostnames, CIDR ranges, or IPv6 addresses.
- Ports are limited to `1..65535`.

## Authorized use only

Port scanning can be intrusive and may be illegal or prohibited on systems you
do not own or are not explicitly authorized to test. **Use this tool only on
systems you own or have written permission to scan.** The author is not
responsible for misuse.

## Tests

Run the unit tests (which only use temporary sockets on `127.0.0.1`):

```
python -m unittest -v
```
