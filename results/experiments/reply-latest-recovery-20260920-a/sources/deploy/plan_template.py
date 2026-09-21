"""Opt-in prototype: learn a successful write + Python compile plan.

Only this explicitly recognized shape is parameterized. No arbitrary shell
substitution, cached execution results, or edits to embedded source paths.
"""
import json
import shlex


def capture(steps):
    if len(steps) != 2 or [s['name'] for s in steps] != ['write', 'bash']:
        return None
    write, check = [s['arguments'] for s in steps]
    if set(write) != {'path', 'content'} or set(check) != {'command'}:
        return None
    try:
        words = shlex.split(check['command'])
    except ValueError:
        return None
    if words != ['python3', '-m', 'py_compile', write['path']]:
        return None
    return json.dumps(dict(version=1, content=write['content']), ensure_ascii=False, sort_keys=True)


def bind(source, path):
    template = json.loads(source)
    if set(template) != {'version', 'content'} or template['version'] != 1 or not isinstance(template['content'], str):
        raise ValueError('Unsupported plan template')
    if not isinstance(path, str) or not path or '\0' in path:
        raise ValueError('Invalid template destination')
    return [dict(name='write', arguments=dict(path=path, content=template['content'])),
            dict(name='bash', arguments=dict(command=shlex.join(['python3', '-m', 'py_compile', path])))]
