"""CPU-only check that a deployed xgrammar accepts legal JSON string escapes."""
import importlib.metadata
import json
import xgrammar as xgr


def probe():
    info = xgr.TokenizerInfo([bytes([i]) for i in range(256)], vocab_type=xgr.VocabType.RAW)
    compiler = xgr.GrammarCompiler(info)
    rows, grammars = [], []
    for minimum in [False, True]:
        schema = {'type': 'object', 'properties': {'oldText': {'type': 'string',
                  **({'minLength': 1} if minimum else {})}},
                  'required': ['oldText'], 'additionalProperties': False}
        grammars.append({'schema': schema, 'grammar': str(xgr.Grammar.from_json_schema(json.dumps(schema)))})
        compiled = compiler.compile_json_schema(json.dumps(schema))
        for value in ['plain text', '"port": 8080', 'first\nsecond', r'path\name', '']:
            matcher = xgr.GrammarMatcher(compiled, terminate_without_stop_token=True)
            payload = json.dumps({'oldText': value})
            accepted = matcher.accept_string(payload)
            rows.append({'schema': schema, 'value': value, 'json_payload': payload,
                         'expected_valid': not minimum or len(value) >= 1,
                         'accepted': accepted, 'terminated': matcher.is_terminated()})
    return {'xgrammar_version': importlib.metadata.version('xgrammar'),
            'scope': 'CPU grammar matcher only; no inference request, model loading or service mutation.',
            'rows': rows, 'grammars': grammars,
            'mismatches': sum(r['expected_valid'] != (r['accepted'] and r['terminated']) for r in rows)}


if __name__ == '__main__':
    result = probe()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['mismatches']))
