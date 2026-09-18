"""CPU-only deterministic protocol example. No model or tool execution."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('protocol', Path(__file__).resolve().parents[1]/'deploy/direct_structural_protocol.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
source = 'def configure(parser):\n    parser.add_argument("--workers", default=10)\n'
allowed = protocol.compact.task_scope(source, 'Set --workers default to 6.')
call = {'name': 'kw', 'arguments': [['--workers', 'default', 6]]}
print(protocol.decode(source, protocol.compact.base.digest(source), call, allowed), end='')
