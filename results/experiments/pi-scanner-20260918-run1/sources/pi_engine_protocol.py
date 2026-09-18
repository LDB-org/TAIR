"""Compile Pi tool schemas to vLLM decision/value frames; execute no tools.

The stdio worker runs on the inference host. Only complete, validated calls
cross back to Pi. Uses the existing engine grammar backend, not a model fork.
"""
import argparse
import hashlib
import json
import math
import re
import sys
import time
import urllib.request

STRING = r'"([^"\\\x00-\x1f]|\\(["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
NUMBER = r'-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?'
META = {'type', 'description', 'title', 'default', '$schema'}


def fields(schema):
    return list(schema.get('properties', {}).items())


def tuple_pattern(parts):
    return r'\[' + ','.join(parts) + r'\]'


def pattern(schema):
    kind = schema.get('type')
    allowed = META | {'properties', 'required', 'additionalProperties'} if kind == 'object' else META
    if kind == 'array':
        allowed |= {'items'}
    if set(schema) - allowed:
        raise ValueError('Unsupported schema keywords: ' + str(set(schema) - allowed))
    if kind == 'string':
        return STRING
    if kind in ('number', 'integer'):
        return NUMBER if kind == 'number' else r'-?(0|[1-9][0-9]*)'
    if kind == 'boolean':
        return '(true|false)'
    if kind == 'array':
        item = pattern(schema['items'])
        return r'\[(' + item + '(,' + item + r')*)?\]'
    if kind == 'object':
        if schema.get('additionalProperties') not in (None, False):
            raise ValueError('Dynamic object keys unsupported')
        required = schema.get('required', [])
        if not set(required) <= set(schema.get('properties', {})):
            raise ValueError('Unknown required field')
        return tuple_pattern([pattern(s) if k in required else '(' + pattern(s) + '|null)'
                              for k, s in fields(schema)])
    raise ValueError('Unsupported schema type: ' + str(kind))


def unpack(schema, value):
    kind = schema['type']
    if kind == 'object':
        props = fields(schema)
        if not isinstance(value, list) or len(value) != len(props):
            raise ValueError('Wrong object tuple length')
        required = schema.get('required', [])
        return {key: unpack(sub, val) for (key, sub), val in zip(props, value)
                if val is not None or key in required}
    if kind == 'array':
        if not isinstance(value, list):
            raise ValueError('Expected array')
        return [unpack(schema['items'], v) for v in value]
    checks = {'string': lambda v: isinstance(v, str),
              'number': lambda v: type(v) in (int, float) and math.isfinite(v),
              'integer': lambda v: type(v) is int,
              'boolean': lambda v: type(v) is bool}
    if not checks[kind](value):
        raise ValueError('Wrong value type: ' + kind)
    if isinstance(value, str):
        value.encode('utf-8')  # Reject unpaired surrogates before dispatch.
    return value


def pack(schema, value):
    if schema['type'] == 'object':
        return [pack(s, value[k]) if k in value else None for k, s in fields(schema)]
    if schema['type'] == 'array':
        return [pack(schema['items'], v) for v in value]
    return value


def layout(schema):
    if schema['type'] == 'object':
        return '[' + ','.join(k + ('?' if k not in schema.get('required', []) else '') + ':' + layout(s)
                              for k, s in fields(schema)) + ']'
    if schema['type'] == 'array':
        return 'array of ' + layout(schema['items'])
    return schema['type']


class Protocol:
    def __init__(self, tools):
        if not 1 <= len(tools) <= 26 or len({t['name'] for t in tools}) != len(tools):
            raise ValueError('Need 1..26 uniquely named tools')
        self.entries = {}
        rules = []
        descriptions = []
        for i, tool in enumerate(tools):
            schema = tool['parameters']
            if schema.get('type') != 'object':
                raise ValueError('Tool arguments must be an object')
            pattern(schema)
            props = fields(schema)
            raw_key = props[-1][0] if props and props[-1][1]['type'] == 'string' and props[-1][0] in schema.get('required', []) else None
            prefix = dict(schema)
            if raw_key:
                prefix['properties'] = dict(props[:-1])
                prefix['required'] = [k for k in schema.get('required', []) if k != raw_key]
            code = chr(65 + i)
            self.entries[code] = (tool, prefix, raw_key)
            rules.append(code + r'\n' + pattern(prefix) + (r'\n[\s\S]*' if raw_key else ''))
            descriptions.append(f'{code} = {tool["name"]}: {tool["description"]}\n'
                                f'Frame: {code} + newline + compact JSON positional tuple {layout(prefix)}'
                                + (f' + newline + RAW {raw_key} string (all remaining text, no escaping or fences)' if raw_key else '')
                                + '\nOriginal parameter descriptions: ' + json.dumps(schema, ensure_ascii=False))
        self.regex = '(' + '|'.join(rules) + ')'
        self.instruction = ('You are a coding agent. Every response MUST be exactly one tool frame below. '
                            'Select the appropriate letter FIRST, then generate its values. Never output prose outside a tool. '
                            'Object keys are supplied by the runtime: encode objects as ordered positional arrays, including nested objects. '
                            'Optional missing values MUST be null. JSON tuples must be compact on ONE physical line. '
                            'Raw final strings preserve all characters. No markdown wrappers. '
                            'Use reply_user only when finished, after checking tool results.\n\n' + '\n\n'.join(descriptions))

    def decode(self, raw, finish_reason):
        if finish_reason != 'stop' or re.fullmatch(self.regex, raw) is None:
            raise ValueError('Incomplete or invalid tool frame')
        tool, prefix, raw_key = self.entries[raw[0]]
        head, separator, tail = raw[2:].partition('\n')
        args = unpack(prefix, json.loads(head))
        if raw_key:
            if not separator:
                raise ValueError('Missing raw value')
            tail.encode('utf-8')
            args[raw_key] = tail
        return {'name': tool['name'], 'arguments': args}

    def encode(self, call):
        code, (tool, prefix, raw_key) = next((c, e) for c, e in self.entries.items() if e[0]['name'] == call['name'])
        frame = code + '\n' + json.dumps(pack(prefix, call['arguments']), ensure_ascii=False, separators=(',', ':'))
        return frame + ('\n' + call['arguments'][raw_key] if raw_key else '')


def infer(request, upstream):
    protocol = Protocol(request['tools'])
    messages = [{'role': 'system', 'content': protocol.instruction + '\n' + request.get('systemPrompt', '')}]
    for msg in request['messages']:
        if msg['role'] == 'assistant':
            messages.extend({'role': 'assistant', 'content': protocol.encode(c)} for c in msg['content'] if c['type'] == 'toolCall')
        elif msg['role'] == 'toolResult':
            messages.append({'role': 'user', 'content': 'TOOL RESULT ' + msg['toolName'] + ':\n' + json.dumps(msg['content'], ensure_ascii=False)})
        elif msg['role'] == 'user':
            text = msg['content'] if isinstance(msg['content'], str) else '\n'.join(c['text'] for c in msg['content'] if c['type'] == 'text')
            messages.append({'role': 'user', 'content': text})
        else:
            raise ValueError('Unsupported message role')
    payload = {'model': '/model', 'messages': messages, 'temperature': 0, 'max_tokens': 4096,
               'structured_outputs': {'regex': protocol.regex}, 'return_token_ids': True,
               'cache_salt': request['session_id'],
               'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}}
    started = time.perf_counter()
    req = urllib.request.Request(upstream + '/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        data = json.load(response)
    choice = data['choices'][0]
    raw = choice['message'].get('content') or ''
    trace = {'seconds': time.perf_counter() - started, 'raw': raw, 'finish_reason': choice['finish_reason'],
             'token_ids': choice.get('token_ids'), 'usage': data.get('usage'), 'metrics': data.get('metrics'),
             'request_id': data.get('id'), 'regex_sha256': hashlib.sha256(protocol.regex.encode()).hexdigest()}
    try:
        return {'call': protocol.decode(raw, choice['finish_reason']), 'trace': trace}
    except (ValueError, UnicodeError) as exc:
        return {'call': None, 'error': str(exc), 'trace': trace}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    try:
        result = infer(json.load(sys.stdin), args.upstream)
    except Exception as exc:
        result = {'call': None, 'error': type(exc).__name__ + ': ' + str(exc)}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
