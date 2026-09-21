import os, sys
sys.path.insert(0, os.getcwd())
from jsonl_changed import parse_jsonl
assert parse_jsonl('  \r\n{"x":"中文"}\r\n[1,null]\ntrue')==[{'x':'中文'},[1,None],True]
assert parse_jsonl('')==[]
try:parse_jsonl('{bad}')
except ValueError:pass
else:raise AssertionError('malformed JSON accepted')
for text in ['{"x":1,"x":2}', '{"outer":{"x":1,"x":2}}']:
 try:parse_jsonl(text)
 except ValueError:pass
 else:raise AssertionError('duplicate keys accepted')
