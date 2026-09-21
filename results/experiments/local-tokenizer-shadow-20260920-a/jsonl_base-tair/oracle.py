import os, sys
sys.path.insert(0, os.getcwd())
from jsonl_base import parse_jsonl
assert parse_jsonl('  \r\n{"x":"中文"}\r\n[1,null]\ntrue')==[{'x':'中文'},[1,None],True]
assert parse_jsonl('')==[]
try:parse_jsonl('{bad}')
except ValueError:pass
else:raise AssertionError('malformed JSON accepted')
assert parse_jsonl('{"x":1,"x":2}')==[{"x":2}]
