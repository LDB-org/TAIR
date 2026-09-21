from jsonl_repeat import parse_jsonl

# Basic
assert parse_jsonl('{"a":1}\n{"b":2}') == [{'a': 1}, {'b': 2}]
# Whitespace-only lines skipped
assert parse_jsonl('{"a":1}\n\n   \n{"b":2}') == [{'a': 1}, {'b': 2}]
# CRLF
assert parse_jsonl('{"a":1}\r\n{"b":2}') == [{'a': 1}, {'b': 2}]
# Final line without newline
assert parse_jsonl('{"a":1}\n{"b":2}') == [{'a': 1}, {'b': 2}]
# Unicode
assert parse_jsonl('{"name":"café"}') == [{'name': 'café'}]
# Duplicate keys: last wins
assert parse_jsonl('{"a":1,"a":2}') == [{'a': 2}]
# Malformed raises ValueError
try:
    parse_jsonl('{bad}')
    assert False
except ValueError:
    pass
print('all checks passed')
